"""Compare what_you_see text to the recipe. Do not invent parts."""

from __future__ import annotations

import re
from typing import Any


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _has_slots(primitives: list[dict[str, Any]]) -> bool:
    for part in primitives:
        if part.get("slots") or part.get("rect_holes"):
            return True
        walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
        for face in walls.values():
            if isinstance(face, dict) and (face.get("slots") or face.get("rect_holes")):
                return True
    return False


def _has_markings(primitives: list[dict[str, Any]]) -> bool:
    from markings import collect_markings

    for part in primitives:
        if collect_markings(part):
            return True
        walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
        for face in walls.values():
            if isinstance(face, dict) and collect_markings(face):
                return True
    return False


def _propellers(primitives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in primitives if _kind(p) in {"propeller", "pervane", "blades", "fan", "cross", "plus"}]


def check_what_you_see(primitives: list[Any] | None, what_you_see: str | None) -> list[dict[str, Any]]:
    text = _blob(what_you_see)
    if not text.strip():
        return []
    parts = [p for p in (primitives or []) if isinstance(p, dict)]
    out: list[dict[str, Any]] = []

    if any(k in text for k in ("pervane", "propeller", "rotor", "yel değirmen", "yel degirmen", "kanatlı", "kanatli")):
        if not _propellers(parts):
            out.append({"status": "FAIL", "note": "what_you_see has a rotor — use type=propeller, not disc"})
        else:
            out.append({"status": "PASS", "note": "what_you_see rotor matches type=propeller"})
        if "4" in text or "dört" in text or "dort" in text or "four" in text:
            blades = max((_propellers(parts) or [{}])[0].get("blades") or 0, 0)
            if _propellers(parts) and int(blades or 0) != 4:
                out.append({"status": "FAIL", "note": "what_you_see says 4 blades — set propeller.blades=4"})

    if any(k in text for k in ("kapı", "kapi", "door", "pencere", "window")):
        if not _has_slots(parts):
            out.append({"status": "FAIL", "note": "what_you_see has a door/window — cut slots on the front wall"})
        else:
            out.append({"status": "PASS", "note": "what_you_see opening matches wall slots"})

    wants_text = any(k in text for k in ("yazı", "yazi", "yazisi", "yazısı", "gravür", "gravur", "engrave", "etch text"))
    quoted = re.findall(r"[\"“”']([^\"“”']{1,40})[\"“”']", str(what_you_see or ""))
    if wants_text or quoted:
        if not _has_markings(parts):
            out.append(
                {
                    "status": "FAIL",
                    "note": "what_you_see has lettering — add markings kind=text on the target part",
                }
            )
        else:
            out.append({"status": "PASS", "note": "what_you_see lettering has markings"})
    return out
