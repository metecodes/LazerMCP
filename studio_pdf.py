"""Digital control-print PDF for Studio. Physical fit remains NOT_VERIFIED."""

from __future__ import annotations

import zlib
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _sheet_mm(nesting: dict[str, Any] | None, summary: dict[str, Any] | None) -> tuple[float, float]:
    nest = nesting or {}
    occ = nest.get("occupied_mm") or nest.get("bed_mm")
    if isinstance(occ, (list, tuple)) and len(occ) >= 2:
        return max(float(occ[0]), 40.0), max(float(occ[1]), 40.0)
    summary = summary or {}
    w = float(summary.get("x_outer_mm") or summary.get("width_mm") or 180)
    h = float(summary.get("y_outer_mm") or summary.get("height_mm") or 120)
    return max(w, 40.0), max(h, 40.0)


def control_sheet_png(
    *,
    nesting: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    file_id: str | None = None,
    dpi: int = 72,
) -> bytes:
    """Raster control sheet: nest placements + dimension legend (not a kerf PASS)."""
    nest = nesting or {}
    summary = summary or {}
    sheet_w, sheet_h = _sheet_mm(nest, summary)
    margin = 24.0
    legend_h = 56.0
    scale = dpi / 25.4
    width = max(200, int((sheet_w + margin * 2) * scale))
    height = max(160, int((sheet_h + margin * 2 + legend_h) * scale))
    img = Image.new("RGB", (width, height), (255, 252, 248))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    ox = margin * scale
    oy = margin * scale
    draw.rectangle(
        (ox, oy, ox + sheet_w * scale, oy + sheet_h * scale),
        outline=(40, 48, 56),
        width=2,
    )
    placements = nest.get("placements") or []
    if placements:
        for i, rec in enumerate(placements):
            x = ox + float(rec.get("x") or 0) * scale
            y = oy + float(rec.get("y") or 0) * scale
            w = max(2.0, float(rec.get("w") or 1) * scale)
            h = max(2.0, float(rec.get("h") or 1) * scale)
            color = (225, 20, 0) if i % 2 == 0 else (30, 120, 180)
            draw.rectangle((x, y, x + w, y + h), outline=color, width=2)
            label = str(rec.get("label") or rec.get("id") or f"p{i+1}")[:18]
            draw.text((x + 3, y + 2), label, fill=color, font=font)
    else:
        # Fallback: outer footprint rectangle from summary.
        draw.rectangle(
            (ox + 4, oy + 4, ox + sheet_w * scale - 4, oy + sheet_h * scale - 4),
            outline=(225, 20, 0),
            width=2,
        )

    inner = summary.get("x_inner_mm")
    outer = summary.get("x_outer_mm")
    lines = [
        "LaserMCP kontrol baskısı — dijital; fiziksel PASS yok",
        f"Pafta ≈ {sheet_w:.0f} × {sheet_h:.0f} mm · {dpi} dpi",
    ]
    if inner is not None and summary.get("y_inner_mm") is not None:
        lines.append(
            f"İç {summary.get('x_inner_mm')}×{summary.get('y_inner_mm')}×{summary.get('h_inner_mm')} mm · "
            f"Dış {outer}×{summary.get('y_outer_mm')}×{summary.get('h_outer_mm')} mm"
        )
    if file_id:
        lines.append(f"Dosya: {file_id}")
    lines.append("Kerf / dry-fit / güç: NOT_VERIFIED")
    ty = oy + sheet_h * scale + 8
    for line in lines:
        draw.text((ox, ty), line, fill=(40, 48, 56), font=font)
        ty += 12

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_as_pdf(png_bytes: bytes) -> bytes:
    """Minimal single-page PDF embedding a PNG (no external PDF lib)."""
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    w_px, h_px = img.size
    # 72 dpi PDF user space ≈ 1 px = 1 pt when raster was built at 72 dpi.
    w_pt, h_pt = float(w_px), float(h_px)
    raw = img.tobytes()
    compressed = zlib.compress(raw, 9)

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.2f} {h_pt:.2f}] "
        f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>".encode("ascii")
    )
    add(
        f"<< /Type /XObject /Subtype /Image /Width {w_px} /Height {h_px} "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
        f"/Length {len(compressed)} >>\nstream\n".encode("ascii")
        + compressed
        + b"\nendstream"
    )
    content = f"q\n{w_pt:.2f} 0 0 {h_pt:.2f} 0 0 cm\n/Im0 Do\nQ\n".encode("ascii")
    add(f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def create_studio_pdf(
    *,
    nesting: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    file_id: str | None = None,
) -> dict[str, Any]:
    png = control_sheet_png(nesting=nesting, summary=summary, file_id=file_id)
    pdf = _png_as_pdf(png)
    name = (file_id or "studio-control").rsplit(".", 1)[0] + "-control.pdf"
    return {
        "success": True,
        "pdf_bytes": pdf,
        "pdf_name": name,
        "note": "Digital control print only. Kerf / dry-fit / powered cut remain NOT_VERIFIED.",
        "physical": "NOT_VERIFIED",
    }
