"""Cost guards in front of the workshop LLM key.

The key bills a provider on every call, and Studio is open to guests. A Studio AI prompt
reaches the key only when every guard here passes; any other request is served by the
local planner, which costs nothing.

Environment (all optional):
  LASERMCP_LLM_MODELS            comma list of model ids Studio may call
  LASERMCP_LLM_DEFAULT_MODEL     model used when the request names none, or one not allowed
  LASERMCP_AI_DAILY_PER_IP       provider calls per address per 24 h (default 10)
  LASERMCP_AI_DAILY_GLOBAL       provider calls for the whole site per 24 h (default 200)
A limit of 0 means no provider calls at all.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_MODELS = ("gpt-4o-mini", "gpt-4o", "claude-haiku-4.5", "claude-sonnet-4.5")
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
    return _wanted_default() or allowed_models()[0]


def resolve_model(requested: Any = "") -> str:
    """The browser only suggests a model; anything outside the allowlist becomes the default."""
    mid = str(requested or "").strip().lower()
    return mid if mid in allowed_models() else default_model()


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


def access(requested_model: Any = "") -> dict[str, Any]:
    """Would this caller reach the workshop key? Never counts against a limit."""
    from llm_keys import get_raw_key, provider_for_model

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
    if not verdict["allow"]:
        return verdict
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
