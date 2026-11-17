"""Look at a picture with a local vision model and write it down as a maker's request.

The workshop's own fine-tuned model ("lasermcp-tuned") reads text only. To build what a
picture shows, a small vision model on the same machine looks first and answers in words:
what the object is, the sizes written on it, how many shelves or compartments, any text.
That sentence then goes to the tuned model exactly like a typed request, so the gate,
the repair turn and every free recipe work as they do for text.

A logo, figure or photo of a flat motif is "art": the Studio keeps tracing it as before.

  LASERMCP_VISION_MODEL      the vision model's name on the server (qwen3-vl:4b-instruct: no hidden
                             reasoning, so it answers in seconds); unset = off
  LASERMCP_VISION_BASE_URL   its OpenAI-compatible address; default LASERMCP_TUNED_BASE_URL
  LASERMCP_LOCAL_API_KEY     the tunnel key, shared with the tuned model

Nothing here pays a provider. The picture never leaves the operator's own machine.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

KINDS = ("object", "sign", "art")
MAX_SIDE = 1024

LOOK_PROMPT = """You see one picture of something a person wants to make from flat sheet material (plywood or acrylic) on a laser cutter.
Answer with JSON only, no other words:
{"kind": "object|sign|art", "what": "...", "request": "...", "sizes_mm": [w, d, h] or null, "parts": n, "text": "..."}
kind:
  object = a 3D thing built from several flat panels: box, bookshelf, shelf, tray or organizer, table, bench, stand, house.
    A cutting layout (several flat outlines with zig-zag finger edges side by side) is also object: count the outlines and say what they build. Six rectangles = a closed box with lid; five = an open box; a large one with slots plus several equal ones = a shelf or a divided tray.
  sign = one flat plate, maybe with letters or simple holes: name plate, tag, coaster, plaque.
  art = a logo, drawing, figure, animal, silhouette or photo motif to be cut or engraved as it looks.
what: what it is, in Turkish, two to five words.
request: one short Turkish sentence a maker would type to order it: the object, its outer size as W x D x H mm, then only what you can see: number of shelves (count the bottom board too), number of compartments, a lid or an open top, and text to engrave. Never mention a feature that is not there (no "0 holes", no legs a tray does not have). Copy every number written in the picture exactly. When no number is written, guess sensible sizes for the object.
sizes_mm: width, depth, height in mm as numbers (a flat plate: width, height, and 3 as depth); null for art.
parts: how many flat panels you count or expect.
text: letters written on the object itself to engrave, copied exactly; empty when there are none (size labels and titles beside the drawing are not engraving)."""


def vision_model() -> str:
    return str(os.environ.get("LASERMCP_VISION_MODEL") or "").strip()


def vision_base_url() -> str:
    raw = os.environ.get("LASERMCP_VISION_BASE_URL") or os.environ.get("LASERMCP_TUNED_BASE_URL") or ""
    return str(raw).strip().rstrip("/")


def ready() -> bool:
    return bool(vision_model() and vision_base_url())


def shrink(data_b64: str, media: str) -> tuple[str, str]:
    """A picture no larger than MAX_SIDE on its long side, as JPEG. Small pictures pass as they are."""
    raw = base64.b64decode(data_b64)
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        if max(img.size) <= MAX_SIDE and media in {"image/png", "image/jpeg"} and len(raw) <= 1_500_000:
            return data_b64, media
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85)
        return base64.b64encode(out.getvalue()).decode("ascii"), "image/jpeg"
    except Exception:
        return data_b64, media


def _number(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if 0 < num < 5000 else None


def parse(content: str) -> dict[str, Any]:
    """The model's answer as a clean dict. Raises ValueError when it is not usable."""
    raw = str(content or "")
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("the vision model did not answer with JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("the vision model's JSON is not an object")
    kind = str(data.get("kind") or "").strip().lower()
    if kind not in KINDS:
        kind = "object"
    sizes = data.get("sizes_mm")
    sizes = [_number(v) for v in sizes] if isinstance(sizes, list) else []
    sizes = [v for v in sizes if v is not None][:3]
    request = " ".join(str(data.get("request") or "").split())
    what = " ".join(str(data.get("what") or "").split())[:80]
    if not request and kind != "art":
        raise ValueError("the vision model gave no request")
    try:
        parts = max(0, min(int(float(data.get("parts") or 0)), 60))
    except (TypeError, ValueError):
        parts = 0
    return {"kind": kind, "what": what, "request": request[:400], "sizes_mm": sizes,
            "parts": parts, "text": str(data.get("text") or "").strip()[:60]}


# Clauses a small vision model adds about things that are NOT there ("0 delik", "yazı yazma",
# "metin yok"). The planner reads every clause as a wish, so they are dropped.
_ABSENT = re.compile(r"(^|\s)(0|sıfır)\s|\byok\b|yazı yazma|metin yazma|yazısız|\bnone\b|\bno\s", re.I)


def tidy(request: str, text: str = "") -> str:
    """The request without clauses about absent features or a bare copy of the engraving text."""
    clauses = [c.strip() for c in str(request or "").split(",")]
    keep = [c for c in clauses if c and not _ABSENT.search(c) and not (text and c.strip(" '\"").casefold() == text.casefold())]
    return ", ".join(keep)


def to_request(seen: dict[str, Any], user_text: str = "") -> str:
    """The sentence the tuned model receives: the person's own words win, the picture fills in."""
    text = str(seen.get("text") or "").strip()
    request = tidy(seen.get("request") or seen.get("what") or "", text)
    sizes = seen.get("sizes_mm") or []
    if len(sizes) == 3 and not re.search(r"\d+\s*[x×*]\s*\d+", request):
        request += f", {sizes[0]:g}x{sizes[1]:g}x{sizes[2]:g} mm"
    if text and f"'{text}'".casefold() not in request.casefold():
        # Said the way people order engraving, so the planner draws it inside the part.
        request += f", üstünde '{text}' yazsın"
    user_text = " ".join(str(user_text or "").split())
    if user_text:
        return f"{user_text}. Görselde: {request}"
    return request


def look(image_b64: str, media: str = "image/jpeg", user_text: str = "", *, timeout: float = 240.0) -> dict[str, Any]:
    """Ask the vision model about one picture. Raises ValueError with a short reason on failure."""
    if not ready():
        raise ValueError("no vision model is configured (LASERMCP_VISION_MODEL)")
    from llm_keys import get_raw_key

    data, media = shrink(image_b64, media)
    ask = LOOK_PROMPT + (f"\nThe person also wrote: {user_text.strip()[:300]}" if str(user_text or "").strip() else "")
    body = {
        "model": vision_model(),
        "temperature": 0.1,
        "max_tokens": 600,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": ask},
            {"type": "image_url", "image_url": {"url": f"data:{media};base64,{data}"}},
        ]}],
    }
    req = urllib.request.Request(
        vision_base_url() + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "authorization": f"Bearer {get_raw_key('local')}"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"vision model HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ValueError("the vision model is not reachable") from exc
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("the vision model's reply has no message") from exc
    seen = parse(content)
    seen["seconds"] = round(time.time() - started, 1)
    seen["model"] = vision_model()
    return seen
