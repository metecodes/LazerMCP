"""Reuse of paid Studio AI drafts and the free-route test for plain boxes.

A provider call is the only part of Studio AI that costs money. Two things avoid it:

* ``simple_box_request`` spots a plain "W×D×H box" prompt, which the local planner
  already drafts as well as a model would, so it is served at $0.
* ``get``/``put`` keep drafts that passed the gate, keyed by model + normalized prompt +
  thickness. Asking the same thing again (a retry, a second visitor, a reload) reuses the
  draft instead of paying again. Only non-BLOCKED drafts are stored.

The cache lives in the Studio data directory (``ai_cache.json``). On serverless hosts
that directory is per instance, so the cache is best effort: a miss only costs the
call it would have cost anyway.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import unicodedata
from typing import Any

from studio_store import read_json, write_json

STORE = "ai_cache.json"
MAX_ENTRIES = 300

_BOX_WORDS = re.compile(r"\b(kutu|kutusu|box|kasa|sandık|sandik|organizer|düzenleyici|duzenleyici)\b", re.I)
_DIMS = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mm|cm)?\s*[x×*]\s*\d+(?:[.,]\d+)?\s*(?:mm|cm)?\s*[x×*]\s*\d+(?:[.,]\d+)?", re.I)
# Words that mean more than a plain box: these go to the model. Stems, so Turkish
# suffixes still match ("çekmeceli", "isimli"); a false hit only costs one model call.
_EXTRA = re.compile(
    r"\b(stand|standı|tutucu|holder|lamba|lamp|ev|house|kuş|kus|bird|robot|araba|car|oyuncak|toy|"
    r"bulmaca|puzzle|saat|clock|logo|resim|çizim|cizim|figür|figur|harf|isim|name|menteşe|mentese|"
    r"hinge|dişli|disli|gear|tekerlek|wheel|çekmece|cekmece|drawer|raf|shelf|kapı|kapi|door|pencere|window)",
    re.I,
)


def ttl_seconds() -> int:
    try:
        days = float(str(os.environ.get("LASERMCP_AI_CACHE_DAYS") or "").strip() or 7)
    except ValueError:
        days = 7
    return max(0, int(days * 86400))


def simple_box_request(prompt: str) -> bool:
    """True for a short plain box with all three sizes given and nothing else asked for."""
    text = str(prompt or "").strip()
    if not text or len(text) > 140 or "\n" in text:
        return False
    return bool(_BOX_WORDS.search(text) and _DIMS.search(text) and not _EXTRA.search(text))


_NUM = r"(\d+(?:[.,]\d+)?)"
_DIMS3 = re.compile(_NUM + r"\s*(?:mm|cm)?\s*[x×*]\s*" + _NUM + r"\s*(?:mm|cm)?\s*[x×*]\s*" + _NUM, re.I)
_LIDS = (
    ("sliding", re.compile(r"(kayar|sürgü|surgu|sliding|slide)", re.I)),
    ("removable", re.compile(r"(çıkarılabilir|cikarilabilir|takılır|removable)", re.I)),
    ("open", re.compile(r"(açık|acik|kapaksız|kapaksiz|open)", re.I)),
    ("finger", re.compile(r"(kapak|lid|closed|kapalı|kapali)", re.I)),
)


def parse_box_request(prompt: str) -> dict[str, Any] | None:
    """Sizes and lid of a plain box prompt, for the parametric box engine.

    The local planner ignores typed sizes ("180x120x70" became 80×80×120), so a plain
    box is built by the same engine as the Box tab. Returns None for anything else.
    """
    text = str(prompt or "")
    if not simple_box_request(text):
        return None
    match = _DIMS3.search(text)
    if not match:
        return None
    x, y, h = (float(v.replace(",", ".")) for v in match.groups())
    if min(x, y, h) <= 0:
        return None
    lid = "open"
    for name, pattern in _LIDS:
        if pattern.search(text):
            lid = name
            break
    unit = "cm" if re.search(r"\d\s*cm\b|\bcm\b", text, re.I) else "mm"
    return {"x": x, "y": y, "h": h, "unit": unit, "lid": lid}


def _normalize(prompt: str) -> str:
    # Turkish dotted capital İ casefolds to "i" + combining dot; drop the dot so
    # "KARTVİZİT" and "kartvizit" share one cache entry.
    text = unicodedata.normalize("NFKC", str(prompt or "")).replace("İ", "i").casefold().replace("̇", "")
    text = text.replace("×", "x").replace("*", "x")
    return re.sub(r"\s+", " ", text).strip()


def cache_key(model: str, prompt: str, thickness: Any) -> str:
    try:
        thick = f"{float(thickness):.2f}" if thickness not in (None, "") else "-"
    except (TypeError, ValueError):
        thick = "-"
    raw = f"{str(model or '').strip().lower()}|{thick}|{_normalize(prompt)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _load() -> dict[str, Any]:
    raw = read_json(STORE, {})
    return raw if isinstance(raw, dict) else {}


def get(key: str) -> dict[str, Any] | None:
    ttl = ttl_seconds()
    if ttl <= 0:
        return None
    row = _load().get(key)
    if not isinstance(row, dict) or not isinstance(row.get("primitives"), list):
        return None
    if time.time() - float(row.get("at") or 0) > ttl:
        return None
    return row


def put(key: str, plan: dict[str, Any]) -> None:
    if ttl_seconds() <= 0 or not isinstance(plan.get("primitives"), list) or not plan["primitives"]:
        return
    store = _load()
    store[key] = {
        "at": time.time(),
        "primitives": plan["primitives"],
        "parameters": plan.get("parameters") if isinstance(plan.get("parameters"), dict) else {},
        "summary": str(plan.get("summary") or "")[:240],
        "model": str(plan.get("model") or ""),
    }
    if len(store) > MAX_ENTRIES:
        newest = sorted(store.items(), key=lambda kv: float((kv[1] or {}).get("at") or 0), reverse=True)
        store = dict(newest[:MAX_ENTRIES])
    try:
        write_json(STORE, store)
    except OSError:
        pass  # a read-only data dir only loses the reuse, never the answer
