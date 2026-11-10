"""Thin OpenAI / Anthropic chat client for Studio AI — uses workshop llm_keys only."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

from llm_keys import get_raw_key, provider_for_model

log = logging.getLogger("lasermcp.llm")

SYSTEM_PROMPT = """You are LaserMCP CAD planner. Reply with ONLY valid JSON (no markdown):
{"primitives":[...],"parameters":{"thickness":3,"project":"...","what_you_see":"..."},"summary":"..."}
Primitives use millimetres. Allowed types: box, panel, disc, contour, triangle.
Box example: {"type":"box","x":180,"y":120,"h":70,"lid":false,"edges":"ffff"}
Panel example: {"type":"panel","w":100,"h":40,"edges":"eeee","holes":[{"x":50,"y":34,"d":4}],"markings":[{"kind":"text","value":"Name","x":50,"y":20,"height":10,"align":"center","operation":"engrave"}]}
Do not invent screws, shafts, or fasteners without explicit request. Prefer finger-joint box when user asks for a box.
"""

# Studio ids that are not provider ids. Any other allowed id is sent to the provider as written.
_OPENAI_IDS = {"gpt-4o-mini": "gpt-4o-mini", "gpt-4o": "gpt-4o", "gpt-5": "gpt-4o"}
_ANTHROPIC_IDS = {
    "claude-haiku-4.5": "claude-haiku-4-5-20251001",
    "claude-sonnet-4.5": "claude-sonnet-4-5-20250929",
    "claude-opus-4.5": "claude-opus-4-5-20251101",
}
_TOKEN_CAP_HIT = "LLM reply hit the output cap (LASERMCP_LLM_MAX_OUTPUT_TOKENS) before the JSON was complete"


def output_cap() -> int:
    """Most output tokens one request may bill. Output is the expensive side of every price list."""
    try:
        cap = int(str(os.environ.get("LASERMCP_LLM_MAX_OUTPUT_TOKENS") or "").strip() or 2500)
    except ValueError:
        cap = 2500
    return max(256, min(cap, 32000))


def _extract_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("LLM reply was not JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM JSON root must be an object")
    return data


def _error_kind(detail: str) -> str:
    """The provider's short error code. Its message can quote part of the key, so it stays in the log."""
    try:
        err = (json.loads(detail) or {}).get("error") or {}
    except (ValueError, AttributeError):
        return ""
    if not isinstance(err, dict):
        return ""
    kind = str(err.get("code") or err.get("type") or "")
    return kind[:60] if re.fullmatch(r"[A-Za-z0-9_.-]+", kind) else ""


def _http_json(url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float = 45.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        log.warning("LLM HTTP %s from %s: %s", exc.code, url, detail)
        kind = _error_kind(detail)
        raise ValueError(f"LLM HTTP {exc.code}" + (f" ({kind})" if kind else "")) from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"LLM network error: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM response was not an object")
    return payload


def _tokens(usage: Any, in_field: str, out_field: str) -> dict[str, int]:
    row = usage if isinstance(usage, dict) else {}
    return {"input_tokens": int(row.get(in_field) or 0), "output_tokens": int(row.get(out_field) or 0)}


def _openai_chat(api_key: str, model: str, user_text: str) -> tuple[str, dict[str, int]]:
    body: dict[str, Any] = {
        "model": _OPENAI_IDS.get(model, model),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    if model in _OPENAI_IDS:
        body["temperature"] = 0.2
        body["max_tokens"] = output_cap()
    else:
        # Reasoning-era models reject a custom temperature and take the newer cap field.
        body["max_completion_tokens"] = output_cap()
    data = _http_json(
        "https://api.openai.com/v1/chat/completions",
        headers={"authorization": f"Bearer {api_key}"},
        body=body,
    )
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("OpenAI returned no choices")
    first = choices[0] or {}
    if first.get("finish_reason") == "length":
        raise ValueError(_TOKEN_CAP_HIT)
    msg = first.get("message") or {}
    return str(msg.get("content") or ""), _tokens(data.get("usage"), "prompt_tokens", "completion_tokens")


def _anthropic_chat(api_key: str, model: str, user_text: str) -> tuple[str, dict[str, int]]:
    body: dict[str, Any] = {
        "model": _ANTHROPIC_IDS.get(model, model),
        "max_tokens": output_cap(),
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_text}],
    }
    if model in _ANTHROPIC_IDS:
        # Newer Claude models reject sampling parameters, so only the mapped ones get one.
        body["temperature"] = 0.2
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        body=body,
    )
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise ValueError("The model declined this request")
    if stop == "max_tokens":
        raise ValueError(_TOKEN_CAP_HIT)
    blocks = data.get("content") or []
    texts = [str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    if not texts:
        raise ValueError("Anthropic returned no text")
    return "\n".join(texts), _tokens(data.get("usage"), "input_tokens", "output_tokens")


def plan_primitives_with_llm(
    prompt: str,
    *,
    model: str = "gpt-4o-mini",
    thickness: float | None = None,
) -> dict[str, Any]:
    """Call workshop provider key → CAD primitives JSON. Raises ValueError on failure.

    The caller decides whether the request may spend the key (llm_guard.authorize) and
    passes a model from the allowlist.
    """
    provider = provider_for_model(model)
    api_key = get_raw_key(provider)
    if not api_key:
        raise ValueError(f"No {provider} API key configured (Account → LLM or env)")
    user = str(prompt or "").strip()
    if thickness not in (None, ""):
        user += f"\nMaterial thickness_mm={float(thickness)}"
    if provider == "openai":
        content, usage = _openai_chat(api_key, model, user)
    else:
        content, usage = _anthropic_chat(api_key, model, user)
    data = _extract_json(content)
    primitives = data.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        raise ValueError("LLM JSON missing primitives[]")
    parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
    return {
        "success": True,
        "provider": provider,
        "model": model,
        "primitives": primitives,
        "parameters": parameters,
        "summary": str(data.get("summary") or "")[:240],
        "method": "workshop_llm",
        "usage": usage,
    }
