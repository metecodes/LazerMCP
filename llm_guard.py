"""Cost guards in front of the workshop LLM key.

The key bills a provider on every call, and Studio is open to guests. A Studio AI prompt
reaches the key only when every guard here passes; any other request is served by the
local planner, which costs nothing.

Environment (all optional):
  LASERMCP_LLM_MODELS            comma list of model ids Studio may call
  LASERMCP_LLM_DEFAULT_MODEL     model used when the request names none, or one not allowed
  LASERMCP_AI_DAILY_PER_IP       provider calls per address per 24 h (default 10)
  LASERMCP_AI_DAILY_GLOBAL       provider calls for the whole site per 24 h (default 200)
  LASERMCP_LLM_REPAIR_MODEL      allowed model for the one automatic repair after a BLOCKED draft
  LASERMCP_AI_AUTO_REPAIR        0 turns automatic repair off (default on; it counts against the caps)
  LASERMCP_AI_REPAIR_ATTEMPTS    paid repair tries per BLOCKED draft, 0-3 (default 2; the 2nd thinks harder)
A limit of 0 means no provider calls at all.
"""

from __future__ import annotations

import os
from typing import Any

# Cheapest capable first: default_model() picks the first one whose provider has a key.
DEFAULT_MODELS = ("claude-haiku-5-5", "gpt-4o-mini", "claude-sonnet-5-5", "gpt-4o", "claude-haiku-4.5", "claude-sonnet-4.5")
DAY_SEC = 86400
_BLOCKED_STATES = {"pending", "denied", "trial_expired"}


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(str(os.environ.get(name) or "").strip() or default))
    except ValueError:
        return default


def daily_per_ip() -> int:
    return _int_env("LASERMCP_AI_DAILY_PER_IP", 10)


def daily_global() -> int:
    return _int_env("LASERMCP_AI_DAILY_GLOBAL", 200)


def _wanted_default() -> str:
    return str(os.environ.get("LASERMCP_LLM_DEFAULT_MODEL") or "").strip().lower()


def allowed_models() -> list[str]:
    raw = str(os.environ.get("LASERMCP_LLM_MODELS") or "")
    ids = [part.strip().lower() for part in raw.split(",") if part.strip()] or list(DEFAULT_MODELS)
    default = _wanted_default()
    if default and default not in ids:
        ids.insert(0, default)
    return list(dict.fromkeys(ids))


def default_model() -> str:
    """The operator's choice, else the first allowed model whose provider has a key.

    DEFAULT_MODELS is ordered cheapest-capable first, so an install with only an
    Anthropic key drafts on Claude Haiku 5.5 instead of falling back to the local planner.
    """
    wanted = _wanted_default()
    if wanted:
        return wanted
    models = allowed_models()
    try:
        from llm_keys import get_raw_key, provider_for_model

        for mid in models:
            if get_raw_key(provider_for_model(mid)):
                return mid
    except Exception:
        pass
    return models[0]


def repair_model(draft_model: str) -> str:
    """Model for the single automatic repair turn after a BLOCKED draft.

    LASERMCP_LLM_REPAIR_MODEL may name a stronger allowed model; by default the draft
    model repairs its own work (no extra price tier).
    """
    wanted = str(os.environ.get("LASERMCP_LLM_REPAIR_MODEL") or "").strip().lower()
    if wanted and wanted in allowed_models():
        return wanted
    from ai_cost import MODEL_PRICES

    # The operator sets this env, so any priced model is trusted for the repair turn.
    return wanted if wanted and wanted in MODEL_PRICES else draft_model


def repair_attempts() -> int:
    """Paid repair tries after a BLOCKED draft (default 2, at most 3). Each passes the caps."""
    return max(0, min(3, _int_env("LASERMCP_AI_REPAIR_ATTEMPTS", 2)))


def auto_repair_enabled() -> bool:
    return str(os.environ.get("LASERMCP_AI_AUTO_REPAIR") or "1").strip().lower() not in {"0", "false", "no", "off"}


def resolve_model(requested: Any = "") -> str:
    """The browser only suggests a model; anything outside the allowlist becomes the default."""
    mid = str(requested or "").strip().lower()
    if mid in allowed_models():
        return mid
    if mid and _is_admin_caller():
        # Admins may try any priced model (e.g. gpt-5.5, gpt-6-astra) without exposing
        # its cost to every user through the allowlist.
        from ai_cost import MODEL_PRICES

        if mid in MODEL_PRICES:
            return mid
    return default_model()


def _is_admin_caller() -> bool:
    try:
        from keys import current_auth
        from supabase_auth import is_admin

        caller = current_auth.get() or {}
        return caller.get("role") == "admin" or is_admin(caller)
    except Exception:
        return False


def _caller_state() -> tuple[dict[str, Any], str]:
    """(caller, "") when the caller may spend the key, otherwise (caller, reason)."""
    from keys import auth_required, current_auth

    caller = current_auth.get() or {}
    if not caller:
        # A single-user install without accounts has nobody to sign in as.
        return caller, "" if not auth_required() else "signin"
    if caller.get("provider") == "google":
        from supabase_auth import account_access_state, user_by_id

        try:
            # The session keeps the review state from sign-in; an admin may have changed it since.
            fresh = user_by_id(str(caller.get("id") or ""))
        except Exception:
            fresh = None
        state = account_access_state(fresh or caller)
        return caller, "" if state in {"approved", "trial"} else "pending"
    state = str(caller.get("approval_status") or "approved").lower()
    return caller, "pending" if state in _BLOCKED_STATES else ""


def _note(reason: str) -> str:
    if reason == "signin":
        return "Sign in with an approved account to use the AI model."
    if reason == "pending":
        return "The AI model opens once your account is approved."
    if reason == "ip_limit":
        return f"Daily AI limit reached ({daily_per_ip()} requests per day from one address). It frees up within 24 hours."
    if reason == "global_limit":
        return "The AI model reached today's site-wide limit. Try again tomorrow."
    return ""


def own_key_access(requested_model: Any = "") -> dict[str, Any] | None:
    """The caller's own provider key, if they stored one and it serves the wanted model.

    With an own key the bill is theirs, so any priced model is open (GPT-6 Astra included)
    and the site's daily caps do not apply. An empty or unpriced request falls to the
    provider's default for own keys. Returns None when the caller has no usable own key.
    """
    from ai_cost import MODEL_PRICES
    from llm_keys import OWN_KEY_DEFAULT_MODEL, provider_for_model, user_providers

    caller, reason = _caller_state()
    user_id = str(caller.get("id") or "")
    if reason or not user_id:
        return None
    try:
        mine = user_providers(user_id)
    except Exception:
        return None
    if not mine:
        return None
    mid = str(requested_model or "").strip().lower()
    if mid in MODEL_PRICES and provider_for_model(mid) in mine:
        model = mid
    elif mid in MODEL_PRICES or mid in allowed_models():
        return None  # they picked a model of a provider they hold no key for: workshop path
    else:
        model = OWN_KEY_DEFAULT_MODEL[mine[0]]
    return {
        "allow": True,
        "reason": "",
        "note": "",
        "model": model,
        "provider": provider_for_model(model),
        "daily_per_ip": None,
        "own_key": True,
        "key_owner": user_id,
    }


def access(requested_model: Any = "") -> dict[str, Any]:
    """Would this caller reach a provider key? Never counts against a limit."""
    from llm_keys import get_raw_key, provider_for_model

    own = own_key_access(requested_model)
    if own:
        return own
    model = resolve_model(requested_model)
    provider = provider_for_model(model)
    reason = ""
    if not get_raw_key(provider):
        reason = "no_key"
    else:
        reason = _caller_state()[1]
    if not reason and (daily_per_ip() <= 0 or daily_global() <= 0):
        reason = "global_limit"
    return {
        "allow": not reason,
        "reason": reason,
        "note": _note(reason),
        "model": model,
        "provider": provider,
        "daily_per_ip": daily_per_ip(),
    }


def authorize(requested_model: Any = "", *, client_ip: str = "") -> dict[str, Any]:
    """access() plus one counted call. Call it once, right before the provider request."""
    from persist.rate_limit import check

    verdict = access(requested_model)
    if not verdict["allow"] or verdict.get("own_key"):
        return verdict  # refused, or the caller's own key: their bill, no site caps
    caller = _caller_state()[0]
    who = str(client_ip or "").strip() or "caller:" + str(caller.get("organization_id") or caller.get("id") or "anon")
    reason = ""
    if not check("studio-ai-address", who, limit=daily_per_ip(), window_sec=DAY_SEC, shared=True):
        reason = "ip_limit"
    elif not check("studio-ai-site", "all", limit=daily_global(), window_sec=DAY_SEC, shared=True):
        reason = "global_limit"
    if reason:
        verdict.update({"allow": False, "reason": reason, "note": _note(reason)})
    return verdict
