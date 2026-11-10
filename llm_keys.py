"""Workshop-owned OpenAI / Anthropic API keys — NOT LaserMCP lzr_ platform keys.

Operators enter provider keys (env or Account → LLM). Raw keys never leave the server
after save; API responses expose only provider + prefix + configured flag.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from typing import Any

from studio_store import now_iso, read_json, write_json

PROVIDERS = ("openai", "anthropic")
STORE_NAME = "llm_keys.json"
WORKSHOP_OWNER = "workshop"


def _secret_material() -> bytes:
    raw = (
        (os.environ.get("LASERMCP_SECRETS_KEY") or "").strip()
        or (os.environ.get("MCP_SESSION_SECRET") or "").strip()
        or "dev-only-llm-key-material"
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _keystream(secret: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(secret + b"|" + nonce + b"|" + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _encrypt(plain: str) -> str:
    data = plain.encode("utf-8")
    nonce = os.urandom(16)
    secret = _secret_material()
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(secret, nonce, len(data))))
    tag = hmac.new(secret, nonce + cipher, hashlib.sha256).digest()[:16]
    blob = nonce + tag + cipher
    return base64.urlsafe_b64encode(blob).decode("ascii")


def _decrypt(token: str) -> str:
    blob = base64.urlsafe_b64decode(str(token).encode("ascii"))
    if len(blob) < 33:
        raise ValueError("corrupt llm key blob")
    nonce, tag, cipher = blob[:16], blob[16:32], blob[32:]
    secret = _secret_material()
    expect = hmac.new(secret, nonce + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expect):
        raise ValueError("llm key integrity check failed")
    plain = bytes(a ^ b for a, b in zip(cipher, _keystream(secret, nonce, len(cipher))))
    return plain.decode("utf-8")


def normalize_provider(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "gpt": "openai",
        "chatgpt": "openai",
        "oai": "openai",
        "claude": "anthropic",
        "sonnet": "anthropic",
        "haiku": "anthropic",
    }
    key = aliases.get(raw, raw)
    if key not in PROVIDERS:
        raise ValueError(f"provider must be openai|anthropic, got {value!r}")
    return key


def _prefix(raw: str) -> str:
    text = str(raw or "").strip()
    if len(text) <= 8:
        return text[:4] + "…" if text else ""
    return text[:7] + "…" + text[-4:]


def _env_key(provider: str) -> str | None:
    env_names = {
        "openai": ("OPENAI_API_KEY", "LASERMCP_OPENAI_API_KEY"),
        "anthropic": ("ANTHROPIC_API_KEY", "LASERMCP_ANTHROPIC_API_KEY"),
    }
    for name in env_names.get(provider, ()):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return None


def _load_store() -> dict[str, Any]:
    raw = read_json(STORE_NAME, {})
    return raw if isinstance(raw, dict) else {}


def _save_store(store: dict[str, Any]) -> None:
    write_json(STORE_NAME, store)


def list_status(*, owner: str = WORKSHOP_OWNER) -> list[dict[str, Any]]:
    """Public status rows — never include raw or ciphertext."""
    store = _load_store()
    owned = store.get(owner) if isinstance(store.get(owner), dict) else {}
    rows: list[dict[str, Any]] = []
    for provider in PROVIDERS:
        env_val = _env_key(provider)
        row = owned.get(provider) if isinstance(owned.get(provider), dict) else {}
        configured = bool(env_val) or bool(row.get("ciphertext"))
        source = "env" if env_val else ("stored" if row.get("ciphertext") else "none")
        prefix = _prefix(env_val) if env_val else str(row.get("prefix") or "")
        rows.append(
            {
                "provider": provider,
                "configured": configured,
                "source": source,
                "prefix": prefix,
                "updated_at": row.get("updated_at") if source == "stored" else None,
            }
        )
    return rows


def any_configured() -> bool:
    return any(r["configured"] for r in list_status())


def get_raw_key(provider: str, *, owner: str = WORKSHOP_OWNER) -> str | None:
    """Server-only. Returns decrypted or env key. Never send to clients."""
    key = normalize_provider(provider)
    env_val = _env_key(key)
    if env_val:
        return env_val
    store = _load_store()
    owned = store.get(owner) if isinstance(store.get(owner), dict) else {}
    row = owned.get(key) if isinstance(owned.get(key), dict) else {}
    cipher = row.get("ciphertext")
    if not cipher:
        return None
    return _decrypt(str(cipher))


def save_key(provider: str, raw_key: str, *, owner: str = WORKSHOP_OWNER, by: str = "") -> dict[str, Any]:
    key = normalize_provider(provider)
    text = str(raw_key or "").strip()
    if len(text) < 12:
        raise ValueError("API key too short")
    if re.search(r"\s", text):
        raise ValueError("API key must not contain whitespace")
    store = _load_store()
    owned = dict(store.get(owner) or {}) if isinstance(store.get(owner), dict) else {}
    owned[key] = {
        "ciphertext": _encrypt(text),
        "prefix": _prefix(text),
        "updated_at": now_iso(),
        "updated_by": str(by or "")[:120],
    }
    store[owner] = owned
    _save_store(store)
    return {
        "success": True,
        "provider": key,
        "configured": True,
        "source": "stored",
        "prefix": _prefix(text),
        "look_again": ["Raw key stored encrypted. It will not be shown again."],
    }


def delete_key(provider: str, *, owner: str = WORKSHOP_OWNER) -> dict[str, Any]:
    key = normalize_provider(provider)
    store = _load_store()
    owned = dict(store.get(owner) or {}) if isinstance(store.get(owner), dict) else {}
    existed = bool(owned.pop(key, None))
    store[owner] = owned
    _save_store(store)
    still = bool(_env_key(key))
    return {
        "success": True,
        "provider": key,
        "deleted_stored": existed,
        "configured": still,
        "source": "env" if still else "none",
        "look_again": (
            ["Stored key removed. Env var still provides a key."]
            if still
            else ["Stored key removed."]
        ),
    }


def provider_for_model(model: str) -> str:
    from ai_cost import MODEL_PRICES

    mid = str(model or "gpt-4o-mini").strip().lower()
    row = MODEL_PRICES.get(mid)
    if row is None:
        # An allowlisted id without a price row still has to reach the right provider.
        return "anthropic" if mid.startswith("claude") else "openai"
    return str(row.get("provider") or "openai")
