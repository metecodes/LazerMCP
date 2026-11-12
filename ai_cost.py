"""Estimate LLM API cost for a prompt before spending. Does not call any provider."""

from __future__ import annotations

import os
import re
from typing import Any

# USD per 1M tokens. Override with LASERMCP_PRICE_<MODEL>_IN / _OUT (dollars per 1M).
# Figures are planning defaults — verify against your provider bill.
MODEL_PRICES: dict[str, dict[str, Any]] = {
    "gpt-4o-mini": {
        "label": "GPT-4o mini",
        "input_per_mtok": 0.15,
        "output_per_mtok": 0.60,
        "provider": "openai",
    },
    "gpt-4o": {
        "label": "GPT-4o",
        "input_per_mtok": 2.50,
        "output_per_mtok": 10.0,
        "provider": "openai",
    },
    "gpt-5": {
        "label": "GPT-5 (estimate)",
        "input_per_mtok": 1.25,
        "output_per_mtok": 10.0,
        "provider": "openai",
    },
    "claude-haiku-4.5": {
        "label": "Claude Haiku 4.5",
        "input_per_mtok": 1.0,
        "output_per_mtok": 5.0,
        "provider": "anthropic",
    },
    "claude-sonnet-4.5": {
        "label": "Claude Sonnet 4.5",
        "input_per_mtok": 3.0,
        "output_per_mtok": 15.0,
        "provider": "anthropic",
    },
    "claude-opus-4.5": {
        "label": "Claude Opus 4.5",
        "input_per_mtok": 15.0,
        "output_per_mtok": 75.0,
        "provider": "anthropic",
    },
    "claude-haiku-5-5": {
        "label": "Claude Haiku 5.5",
        "input_per_mtok": 0.10,
        "output_per_mtok": 0.50,
        "provider": "anthropic",
    },
    "claude-sonnet-5-5": {
        "label": "Claude Sonnet 5.5",
        "input_per_mtok": 2.0,
        "output_per_mtok": 10.0,
        "provider": "anthropic",
    },
    "claude-opus-5-5": {
        "label": "Claude Opus 5.5",
        "input_per_mtok": 4.0,
        "output_per_mtok": 20.0,
        "provider": "anthropic",
    },
    "claude-fable-5-1": {
        "label": "Claude Fable 5.1",
        "input_per_mtok": 10.0,
        "output_per_mtok": 50.0,
        "provider": "anthropic",
    },
    # The workshop's fine-tuned model (LASERMCP_TUNED_MODEL). Fine-tuned small models bill
    # above their base rate; set LASERMCP_PRICE_LASERMCP_TUNED_IN/_OUT to the real figures.
    "lasermcp-tuned": {
        "label": "LaserMCP (eğitilmiş)",
        "input_per_mtok": 0.30,
        "output_per_mtok": 1.20,
        "provider": "openai",
    },
    # Third-party listings (Nov 2026); confirm on the provider's page or override via env.
    "gpt-5.5": {
        "label": "GPT-5.5",
        "input_per_mtok": 5.0,
        "output_per_mtok": 30.0,
        "provider": "openai",
    },
    # Not confirmed on the provider's own price page — set LASERMCP_PRICE_GPT_6_ASTRA_IN/_OUT.
    "gpt-6-astra": {
        "label": "GPT Astra (estimate)",
        "input_per_mtok": 10.0,
        "output_per_mtok": 50.0,
        "provider": "openai",
    },
}

# Extra input tokens typical when the host AI has LaserMCP tools + instructions loaded.
CONTEXT_OVERHEAD = {
    "studio_local": 0,  # plan_laser_job runs in-process — no LLM bill from LaserMCP
    "mcp_thin": 3500,  # tools list + short instructions
    "mcp_full": 12000,  # full CAD grammar + prior turns
}


def estimate_tokens(text: str) -> int:
    """Rough token count without tiktoken: ~4 chars/token for mixed TR/EN."""
    raw = str(text or "")
    if not raw:
        return 0
    # CJK-ish denser; Latin/TR closer to 4 chars
    non_ascii = sum(1 for ch in raw if ord(ch) > 127)
    if non_ascii > len(raw) * 0.3:
        return max(1, int(len(raw) / 2.5))
    words = len(re.findall(r"\S+", raw))
    by_chars = max(1, int(len(raw) / 4))
    by_words = max(1, int(words * 1.3))
    return max(by_chars, by_words)


def _price_row(model: str) -> dict[str, Any]:
    key = str(model or "gpt-4o-mini").strip().lower()
    aliases = {
        "mini": "gpt-4o-mini",
        "4o-mini": "gpt-4o-mini",
        "4o": "gpt-4o",
        "sonnet": "claude-sonnet-4.5",
        "haiku": "claude-haiku-4.5",
        "opus": "claude-opus-4.5",
    }
    key = aliases.get(key, key)
    from llm_keys import own_endpoint

    if own_endpoint(key):
        # Served from the operator's own machine: no provider bills these tokens.
        return {"label": (MODEL_PRICES.get(key) or {}).get("label") or key, "input_per_mtok": 0.0, "output_per_mtok": 0.0, "provider": "local", "id": key}
    row = dict(MODEL_PRICES.get(key) or MODEL_PRICES["gpt-4o-mini"])
    env_key = re.sub(r"[^A-Z0-9]+", "_", key.upper())
    try:
        if os.environ.get(f"LASERMCP_PRICE_{env_key}_IN"):
            row["input_per_mtok"] = float(os.environ[f"LASERMCP_PRICE_{env_key}_IN"])
        if os.environ.get(f"LASERMCP_PRICE_{env_key}_OUT"):
            row["output_per_mtok"] = float(os.environ[f"LASERMCP_PRICE_{env_key}_OUT"])
    except ValueError:
        pass
    row["id"] = key if key in MODEL_PRICES else "gpt-4o-mini"
    return row


def usage_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """USD for the token counts a provider reported for one finished call.

    Anthropic reports prompt-cache reads/writes apart from input_tokens: reads bill at
    0.1× and 5-minute writes at 1.25× the input rate.
    """
    prices = _price_row(model)
    rate_in = float(prices["input_per_mtok"])
    usd = (
        int(input_tokens or 0) * rate_in
        + int(cache_read_tokens or 0) * rate_in * 0.1
        + int(cache_write_tokens or 0) * rate_in * 1.25
        + int(output_tokens or 0) * float(prices["output_per_mtok"])
    )
    return round(usd / 1_000_000.0, 6)


def estimate_prompt_cost(
    prompt: str,
    *,
    model: str = "gpt-4o-mini",
    mode: str = "mcp_thin",
    expected_output_tokens: int | None = None,
    photo: bool = False,
    compare_models: bool = True,
) -> dict[str, Any]:
    """Return a dry-run cost quote. Never invents a real charge."""
    text = str(prompt or "").strip()
    prompt_tokens = estimate_tokens(text)
    overhead = int(CONTEXT_OVERHEAD.get(str(mode), CONTEXT_OVERHEAD["mcp_thin"]))
    # Vision / photo adds image tokens (conservative flat pad)
    image_tokens = 800 if photo else 0
    # CAD replies with JSON primitives + narration
    out_tokens = int(expected_output_tokens) if expected_output_tokens not in (None, "") else max(400, min(2500, prompt_tokens * 2 + 300))
    if photo:
        out_tokens = max(out_tokens, 800)

    inp = prompt_tokens + overhead + image_tokens
    prices = _price_row(model)
    in_rate = float(prices["input_per_mtok"])
    out_rate = float(prices["output_per_mtok"])
    input_usd = (inp / 1_000_000.0) * in_rate
    output_usd = (out_tokens / 1_000_000.0) * out_rate
    total = input_usd + output_usd

    local = str(mode) == "studio_local"
    # Local studio planner never hits a provider — quote $0 even if tokens are counted for size.
    bill_in = 0.0 if local else input_usd
    bill_out = 0.0 if local else output_usd
    bill_total = 0.0 if local else total
    result = {
        "success": True,
        "billable_llm": not local,
        "mode": mode,
        "model": prices["id"],
        "model_label": prices["label"],
        "provider": prices["provider"],
        "prompt_chars": len(text),
        "tokens": {
            "prompt": prompt_tokens,
            "context_overhead": overhead,
            "image": image_tokens,
            "input_total": inp,
            "output_estimate": out_tokens,
        },
        "usd": {
            "input": round(bill_in, 6),
            "output": round(bill_out, 6),
            "total": round(bill_total, 6),
            "per_100_runs": round(bill_total * 100, 4),
            "hypothetical_if_billed": round(total, 6),
        },
        "platform": {
            "studio_parametric_usd": 0.0,
            "studio_ai_local_planner_usd": 0.0,
            "note": (
                "Stüdyo parametrik kutu ve Stüdyo AI (plan_laser_job) LaserMCP içinde LLM çağırmaz → $0 API. "
                "ChatGPT/Claude MCP ile bağlanınca maliyet o sağlayıcıya gider; tablo onun için."
            ),
        },
        "assumptions": [
            "Token count is approximate (~4 chars/token); not a provider invoice.",
            f"Context overhead mode={mode}: {overhead} tokens.",
            "Output size guessed from prompt length; long CAD JSON can cost more.",
            "Prices are defaults — set LASERMCP_PRICE_<MODEL>_IN/OUT to match your contract.",
        ],
        "look_again": [
            "Bu bir ön maliyet tahmini. Gerçek fatura OpenAI/Anthropic/ChatGPT aboneliğinden gelir.",
            "Parametrik kutu değişikliği API anahtarı harcamaz.",
        ],
    }
    if compare_models:
        result["try"] = {
            mid: _quick(text, mid, mode, photo)
            for mid in ("claude-haiku-5-5", "gpt-4o-mini", "claude-sonnet-5-5", "gpt-4o")
        }
    return result


def _quick(prompt: str, model: str, mode: str, photo: bool) -> dict[str, float]:
    row = estimate_prompt_cost(prompt, model=model, mode=mode, photo=photo, compare_models=False)
    return {"total_usd": row["usd"]["total"], "input_tokens": row["tokens"]["input_total"]}


def list_models() -> list[dict[str, Any]]:
    return [
        {
            "id": mid,
            "label": row["label"],
            "provider": row["provider"],
            "input_per_mtok_usd": row["input_per_mtok"],
            "output_per_mtok_usd": row["output_per_mtok"],
        }
        for mid, row in MODEL_PRICES.items()
    ]
