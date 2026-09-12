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


_PRODUCT_ALIAS = {
    "payasrobot": "robot_bank",
    "stemtrafficlight": "traffic_light",
    "abox": "product_box",
}

KIT_USE: dict[str, list[str]] = {
    "traffic_light": [
        "Kaide üstündeki 3 şalteri tek tek bas.",
        "Kırmızı şalter yalnız kırmızı LED’i yakmalı.",
        "Sarı şalter yalnız sarı LED’i yakmalı.",
        "Yeşil şalter yalnız yeşil LED’i yakmalı.",
    ],
    "robot_bank": [
        "M3 vidaları sökerek arka para kapağını aç; tekrar kapat.",
        "Göz LED’lerinin takılı ve kablolu olduğunu kontrol et.",
        "Şalteri aç. Para yuvasından bir madeni para at.",
        "Para düşünce LED yanmalı. Yazılım bu adımı PASS saymaz.",
    ],
    "drawing_robot": [
        "Kalemi tak. Motorları çalıştır.",
        "Kol çarpışmadan çizmeli.",
    ],
    "astronaut": [
        "Pili tak. Motoru çalıştır.",
        "Figür takılmadan yürümeli.",
    ],
}


def _product_key(product: str | None) -> str:
    raw = str(product or "").strip()
    key = raw.lower().replace(" ", "_")
    return _PRODUCT_ALIAS.get(key, key)


def use_sheet(product: str | None) -> str:
    steps = KIT_USE.get(_product_key(product))
    if not steps:
        return ""
    lines = [
        "AFTER ASSEMBLY USE:",
        "Software does not light an LED. A human runs these steps.",
    ]
    for i, step in enumerate(steps, start=1):
        lines.append(f"{i}. {step}")
    lines.append("Pass use_test=verified only after the kit actually works.")
    return "\n".join(lines)


def assembly_sheet(
    design_map: dict[str, Any] | None,
    connections: list[Any] | None = None,
    product: str | None = None,
) -> str:
    parts = [p for p in ((design_map or {}).get("parts") or []) if isinstance(p, dict)]
    use = use_sheet(product)
    if not parts and not use:
        return ""
    lines: list[str] = []
    if parts:
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
    if use:
        if lines:
            lines.append("")
        lines.append(use)
    return "\n".join(lines)
