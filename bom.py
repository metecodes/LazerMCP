"""MCP writes the material list. Incoming AIs do not invent hardware."""

from __future__ import annotations

from typing import Any

KIT_BOM: dict[str, list[dict[str, Any]]] = {
    "robot_bank": [
        {"item": "3 mm kavak kontrplak", "qty": 1, "unit": "sheet", "note": "PayasRobot faces + arms + feet"},
        {"item": "LED 5 mm (opsiyonel)", "qty": 2, "unit": "pcs", "note": "göz delikleri"},
        {"item": "M3×10 vida + somun", "qty": 8, "unit": "pcs", "note": "kol / ayak"},
        {"item": "Ahşap tutkalı", "qty": 1, "unit": "job", "note": "parmak eklemleri kuru geçmeden sonra"},
    ],
    "traffic_light": [
        {"item": "3 mm kavak kontrplak", "qty": 1, "unit": "sheet", "note": "kaide + kule"},
        {"item": "5 mm LED", "qty": 3, "unit": "pcs", "note": "kırmızı / sarı / yeşil"},
        {"item": "Direnç 220 Ω", "qty": 3, "unit": "pcs"},
        {"item": "Pil yuvası 3×AA veya USB 5 V", "qty": 1, "unit": "pcs"},
        {"item": "Kablo + makaron", "qty": 1, "unit": "set"},
    ],
    "drawing_robot": [
        {"item": "3 mm kavak kontrplak", "qty": 1, "unit": "sheet", "note": "Ressam robot gövde"},
        {"item": "Servo / DC motor (kitiyle belirtilen)", "qty": 2, "unit": "pcs"},
        {"item": "Kalem tutucu (kit geometrisi)", "qty": 1, "unit": "pcs"},
        {"item": "M3 vida seti", "qty": 1, "unit": "set"},
    ],
    "yacht": [
        {"item": "3 mm kavak kontrplak", "qty": 1, "unit": "sheet", "note": "gövde + güverte"},
        {"item": "Ahşap tutkalı", "qty": 1, "unit": "job"},
    ],
    "astronaut": [
        {"item": "3 mm kavak kontrplak", "qty": 1, "unit": "sheet", "note": "açık şase + figür"},
        {"item": "DC motor (fotoğraftaki sarı tip, ölçü tahmin etme)", "qty": 1, "unit": "pcs"},
        {"item": "M3×10 vida + pul + somun", "qty": 12, "unit": "pcs"},
        {"item": "3×AA pil yuvası", "qty": 1, "unit": "pcs"},
        {"item": "Ø4 pim / mil", "qty": 1, "unit": "pcs", "note": "krank"},
    ],
    "product_box": [
        {"item": "3 mm kavak kontrplak", "qty": 1, "unit": "sheet", "note": "ABox duvar + taban + kapak"},
        {"item": "Ahşap tutkalı", "qty": 1, "unit": "job"},
    ],
}


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def _label(part: dict[str, Any]) -> str:
    return str(part.get("label") or "").lower()


def _area_m2(primitives: list[dict[str, Any]], thickness: float) -> float:
    mm2 = 0.0
    for part in primitives:
        n = max(1, int(part.get("count") or part.get("n") or 1))
        if _kind(part) == "box":
            x = float(part.get("x") or part.get("w") or 80)
            y = float(part.get("y") or part.get("d") or 80)
            h = float(part.get("h") or 80)
            mm2 += n * (2 * x * h + 2 * y * h + x * y)
            continue
        w = float(part.get("w") or part.get("x") or part.get("d") or 0)
        h = float(part.get("h") or part.get("y") or part.get("d") or 0)
        if _kind(part) in {"disc", "disk", "propeller", "pervane"}:
            d = float(part.get("d") or w or 40)
            mm2 += n * 3.1416 * (d / 2) ** 2
        elif w and h:
            mm2 += n * w * h
    return round(mm2 / 1_000_000.0, 4)


def _hardware(primitives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    holes: list[float] = []
    has_prop = False
    has_solar = False
    has_motor = False
    for part in primitives:
        if _kind(part) in {"propeller", "pervane", "blades", "fan"}:
            has_prop = True
            holes.append(float(part.get("hole") or 4))
        if "solar" in _label(part):
            has_solar = True
        if "motor" in _label(part):
            has_motor = True
        for hole in part.get("holes") or []:
            if isinstance(hole, dict) and (hole.get("d") or hole.get("diameter")):
                holes.append(float(hole.get("d") or hole.get("diameter")))
        walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
        for face in walls.values():
            if not isinstance(face, dict):
                continue
            for hole in face.get("holes") or []:
                if isinstance(hole, dict) and (hole.get("d") or hole.get("diameter")):
                    holes.append(float(hole.get("d") or hole.get("diameter")))
    if has_prop or has_motor:
        shaft = holes[0] if holes else 4.0
        out.append({"item": f"Ø{shaft:.0f} mm mil / dowel", "qty": 1, "unit": "pcs", "note": "koaksiyel deliklerle aynı çap"})
        out.append({"item": "DC motor (fotoğraftaki gövde, ölçüyü uydurma)", "qty": 1, "unit": "pcs"})
        out.append({"item": "Motor vida (motor plakası deliklerine göre)", "qty": 2, "unit": "pcs"})
    if has_solar:
        out.append({"item": "Güneş paneli (panel w×h mm)", "qty": 1, "unit": "pcs", "note": "solar etiketi"})
    if any(_kind(p) == "coupon" for p in primitives):
        out.append({"item": "Hurda 3 mm şerit (kupon)", "qty": 1, "unit": "job", "note": "100 mm çubuğu ölç"})
    return out


def build_bom(
    *,
    primitives: list[Any] | None = None,
    product: str | None = None,
    material: dict[str, Any] | None = None,
    nesting: dict[str, Any] | None = None,
    machine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parts = [p for p in (primitives or []) if isinstance(p, dict)]
    mat = material or {"id": "poplar_3mm", "name": "3 mm kavak kontrplak", "thickness": 3.0, "sheet_w": 1500, "sheet_h": 3000}
    sheet_area = (float(mat.get("sheet_w") or 1500) * float(mat.get("sheet_h") or 3000)) / 1_000_000.0
    used = _area_m2(parts, float(mat.get("thickness") or 3))
    if nesting and nesting.get("occupied_mm"):
        occ = nesting["occupied_mm"]
        used = max(used, round((float(occ[0]) * float(occ[1])) / 1_000_000.0, 4))
    sheets = 1
    if sheet_area > 0:
        sheets = max(1, int(used / sheet_area) + (1 if used > sheet_area * 0.92 else 0))
    if nesting and nesting.get("sheets"):
        sheets = max(sheets, int(nesting.get("sheets") or 1))

    lines = list(KIT_BOM.get(str(product or ""), []))
    if not lines:
        lines.append(
            {
                "item": mat.get("name") or "3 mm kavak kontrplak",
                "qty": sheets,
                "unit": "sheet",
                "note": f"~{used} m² kesim alanı, {mat.get('thickness')} mm",
            }
        )
        lines.append({"item": "Ahşap tutkalı", "qty": 1, "unit": "job", "note": "kuru geçme sonrası"})
        lines.extend(_hardware(parts))

    speak = ["MATERIALS (MCP):"]
    for row in lines:
        extra = f" — {row['note']}" if row.get("note") else ""
        speak.append(f"- {row['qty']} {row['unit']} {row['item']}{extra}")
    if machine:
        speak.append(f"Machine: {machine.get('name')} · bed {machine.get('bed_w')}×{machine.get('bed_h')} mm")
    speak.append("Do not substitute thickness. Recalibrate kerf on a new batch.")
    return {
        "product": product or "composed",
        "material_id": mat.get("id"),
        "area_m2": used,
        "sheets": sheets,
        "lines": lines,
        "speak": "\n".join(speak),
        "author": "Laser MCP",
        "note": "MCP wrote this list from the recipe / named kit. Incoming AIs must not invent hardware.",
    }
