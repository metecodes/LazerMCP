"""Classify true one-piece jobs without weakening mechanical validation."""
from __future__ import annotations

from typing import Any

_ARTWORK_TYPES = {"marking", "text", "path", "icon", "image", "illustration", "line"}
_PUZZLES = {"jigsaw_puzzle", "number_match_puzzle", "classic_jigsaw", "number_match"}


def classify_assembly_mode(built: dict[str, Any], faces: list[dict[str, Any]], connections: list[dict[str, Any]], moving: bool) -> dict[str, Any]:
    params = built.get("parameters") if isinstance(built.get("parameters"), dict) else {}
    requested = str(params.get("assembly_mode") or "auto").strip().lower()
    if requested not in {"auto", "standalone", "mechanical"}:
        return {"mode": "mechanical", "requested": requested, "valid": False, "physical_part_count": 0,
                "reason": "assembly_mode must be auto, standalone or mechanical"}

    preset = str(built.get("preset") or built.get("product") or "").strip().lower()
    if preset == "engraving_layout":
        physical_count = 1
    elif faces:
        physical_count = sum(1 for face in faces if str(face.get("kind") or "").lower() not in _ARTWORK_TYPES)
    else:
        try:
            from semantic_cad import inspect_design
            physical_count = len(inspect_design(built.get("svg_bytes") or b"").get("parts") or [])
        except Exception:
            physical_count = int(built.get("physical_part_count") or 0)

    explicit_connections = bool(connections or params.get("connections") or params.get("mates") or params.get("joints"))
    mechanical_preset = preset in _PUZZLES
    eligible = physical_count == 1 and not explicit_connections and not moving and not mechanical_preset
    if requested == "standalone" and not eligible:
        reason = (f"standalone rejected: physical_parts={physical_count}, connections={explicit_connections}, "
                  f"moving={moving}, mechanical_preset={mechanical_preset}")
        return {"mode": "mechanical", "requested": requested, "valid": False,
                "physical_part_count": physical_count, "reason": reason}
    mode = "standalone" if (requested == "standalone" or (requested == "auto" and eligible)) else "mechanical"
    return {"mode": mode, "requested": requested, "valid": True, "physical_part_count": physical_count,
            "reason": "single physical part with no assembly graph" if mode == "standalone" else "mechanical validation required"}
