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


def _has_markings(primitives: list[dict[str, Any]], text_only: bool = False) -> bool:
    from markings import collect_markings, _kind as marking_kind

    for part in primitives:
        if any(not text_only or marking_kind(m) == "text" for m in collect_markings(part)):
            return True
        walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
        for face in walls.values():
            if isinstance(face, dict) and any(not text_only or marking_kind(m) == "text" for m in collect_markings(face)):
                return True
    return False


def _propellers(primitives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in primitives if _kind(p) in {"propeller", "pervane", "blades", "fan", "cross", "plus"}]


def _requested(text: str, terms: tuple[str, ...]) -> bool:
    """Match affirmative feature clauses, not titles or explicitly absent features."""
    clauses = re.split(r"[,;.\n]|\b(?:ama|ancak|but|whereas)\b", text)
    for clause in clauses:
        if not any(re.search(r"(?<!\w)" + re.escape(term) + r"(?:si|sı|leri|ları|ler|lar|li|lı|sinin|sının)?(?!\w)", clause) for term in terms):
            continue
        if re.search(r"\b(?:yok|yoktur|olmadan|olmayan|olmayacak|bulunmuyor|içermiyor|icermiyor|without|no|not|absent)\b", clause):
            continue
        return True
    return False


def check_what_you_see(primitives: list[Any] | None, what_you_see: str | None) -> list[dict[str, Any]]:
    text = _blob(what_you_see)
    if not text.strip():
        return []
    parts = [p for p in (primitives or []) if isinstance(p, dict)]
    out: list[dict[str, Any]] = []

    if _requested(text, ("pervane", "propeller", "rotor", "yel değirmen", "yel degirmen", "kanatlı", "kanatli")):
        if not _propellers(parts):
            out.append({"status": "FAIL", "note": "what_you_see has a rotor — use type=propeller, not disc"})
        else:
            out.append({"status": "PASS", "note": "what_you_see rotor matches type=propeller"})
        if "4" in text or "dört" in text or "dort" in text or "four" in text:
            blades = max((_propellers(parts) or [{}])[0].get("blades") or 0, 0)
            if _propellers(parts) and int(blades or 0) != 4:
                out.append({"status": "FAIL", "note": "what_you_see says 4 blades — set propeller.blades=4"})

    if _requested(text, ("kapı", "kapi", "door", "pencere", "pencereler", "window", "windows")):
        if not _has_slots(parts):
            out.append({"status": "FAIL", "note": "what_you_see has a door/window — cut slots on the front wall"})
        else:
            out.append({"status": "PASS", "note": "what_you_see opening matches wall slots"})

    wants_text = _requested(text, ("yazı", "yazi", "yazisi", "yazısı", "lettering", "text", "etch text"))
    wants_engraving = _requested(text, ("gravür", "gravur", "engrave", "engraving", "kazıma", "kazima"))
    # Quoted product names and quoted part labels are not lettering instructions.
    if wants_text or wants_engraving:
        if not _has_markings(parts, text_only=wants_text):
            out.append(
                {
                    "status": "FAIL",
                    "note": "what_you_see has lettering — add markings kind=text on the target part",
                }
            )
        else:
            out.append({"status": "PASS", "note": "what_you_see lettering has markings"})
    return out
