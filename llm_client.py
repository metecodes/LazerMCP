"""Thin OpenAI / Anthropic chat client for Studio AI — uses workshop llm_keys only."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from llm_keys import get_raw_key, provider_for_model

SYSTEM_PROMPT = """You are LaserMCP CAD planner. Reply with ONLY valid JSON (no markdown):
{"primitives":[...],"parameters":{"thickness":3,"project":"...","what_you_see":"..."},"summary":"..."}
Primitives use millimetres. Allowed types: box, panel, disc, contour, triangle.
Box example: {"type":"box","x":180,"y":120,"h":70,"lid":false,"edges":"ffff"}
Panel example: {"type":"panel","w":100,"h":40,"edges":"eeee","holes":[{"x":50,"y":34,"d":4}],"markings":[{"kind":"text","value":"Name","x":50,"y":20,"height":10,"align":"center","operation":"engrave"}]}
Do not invent screws, shafts, or fasteners without explicit request. Prefer finger-joint box when user asks for a box.
"""


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
        raise ValueError(f"LLM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"LLM network error: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM response was not an object")
    return payload


def _openai_chat(api_key: str, model: str, user_text: str) -> str:
    # Map studio model ids to OpenAI API ids
    api_model = {
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4o": "gpt-4o",
        "gpt-5": "gpt-4o",
    }.get(model, "gpt-4o-mini")
    data = _http_json(
        "https://api.openai.com/v1/chat/completions",
        headers={"authorization": f"Bearer {api_key}"},
        body={
            "model": api_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        },
    )
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("OpenAI returned no choices")
    msg = (choices[0] or {}).get("message") or {}
    return str(msg.get("content") or "")


def _anthropic_chat(api_key: str, model: str, user_text: str) -> str:
    api_model = {
        "claude-haiku-4.5": "claude-haiku-4-5-20251001",
        "claude-sonnet-4.5": "claude-sonnet-4-5-20250929",
        "claude-opus-4.5": "claude-opus-4-5-20251101",
    }.get(model, "claude-haiku-4-5-20251001")
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        body={
            "model": api_model,
            "max_tokens": 2500,
            "temperature": 0.2,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
        },
    )
    blocks = data.get("content") or []
    texts = [str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    if not texts:
        raise ValueError("Anthropic returned no text")
    return "\n".join(texts)


def plan_primitives_with_llm(
    prompt: str,
    *,
    model: str = "gpt-4o-mini",
    thickness: float | None = None,
) -> dict[str, Any]:
    """Call workshop provider key → CAD primitives JSON. Raises ValueError on failure."""
    provider = provider_for_model(model)
    api_key = get_raw_key(provider)
    if not api_key:
        raise ValueError(f"No {provider} API key configured (Account → LLM or env)")
    user = str(prompt or "").strip()
    if thickness not in (None, ""):
        user += f"\nMaterial thickness_mm={float(thickness)}"
    if provider == "openai":
        content = _openai_chat(api_key, model, user)
    else:
        content = _anthropic_chat(api_key, model, user)
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
    }
