"""Automatic nest preview PNG from placements. Not a substitute for the SVG."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw


def nest_preview_png(nesting: dict[str, Any] | None, width: int = 640) -> bytes | None:
    nest = nesting or {}
    placements = nest.get("placements") or []
    occ = nest.get("occupied_mm") or nest.get("bed_mm")
    if not placements or not occ:
        return None
    sheet_w = max(float(occ[0]), 1.0)
    sheet_h = max(float(occ[1]), 1.0)
    scale = width / sheet_w
    height = max(80, int(sheet_h * scale))
    img = Image.new("RGB", (width, height), (255, 252, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(234, 223, 211))
    for i, rec in enumerate(placements):
        x = float(rec.get("x") or 0) * scale
        y = float(rec.get("y") or 0) * scale
        w = max(2.0, float(rec.get("w") or 1) * scale)
        h = max(2.0, float(rec.get("h") or 1) * scale)
        color = (255, 90, 31) if i % 2 == 0 else (20, 184, 166)
        draw.rectangle((x, y, x + w, y + h), outline=color, width=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
