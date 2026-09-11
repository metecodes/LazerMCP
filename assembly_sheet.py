"""Human assembly order from the design map. Not a new MCP tool."""

from __future__ import annotations

from typing import Any

_ORDER = (
    "floor",
    "wall",
    "gable",
    "panel",
    "disc",
    "propeller",
    "contour",
    "other",
)


def _rank(part: dict[str, Any]) -> tuple[int, str]:
    kind = str(part.get("kind") or part.get("role") or "other")
    name = str(part.get("name") or part.get("label") or kind)
    try:
        idx = _ORDER.index(kind if kind in _ORDER else "other")
    except ValueError:
        idx = len(_ORDER)
    wall_pref = {"bottom": 0, "front": 1, "back": 2, "left": 3, "right": 4, "lid": 5}
    return (idx, str(wall_pref.get(name, 20)) + name)


def assembly_sheet(design_map: dict[str, Any] | None, connections: list[Any] | None = None) -> str:
    parts = [p for p in ((design_map or {}).get("parts") or []) if isinstance(p, dict)]
    if not parts:
        return ""
    ordered = sorted(parts, key=_rank)
    lines = ["ASSEMBLY SHEET:", "Dry-fit before glue. Finger joints are Boxes.py f/F."]
    for i, part in enumerate(ordered, start=1):
        name = part.get("name") or part.get("label") or part.get("id") or f"P{i:02d}"
        kind = part.get("kind") or ""
        role = part.get("role") or ""
        extra = f" ({kind}" + (f", {role}" if role and role != kind else "") + ")"
        lines.append(f"{i}. {name}{extra}")
    n = len(connections or [])
    if n:
        lines.append(f"Connections recorded: {n}")
    lines.append("Do not flip or rotate parts.")
    return "\n".join(lines)
