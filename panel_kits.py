"""Multi-part kits: one short primitive that expands into placed, joined panels.

A small model cannot reliably compute the 3D placement of every panel of a bookshelf, and
one wrong coordinate blocks the whole design. A kit asks it only for what it is good at —
which object, which sizes, how many shelves — and this module computes the panels, the
finger joints between touching edges (`parameters.connections`) and the tab-slot joints
for shelves and dividers that meet a panel in its middle.

  {"type":"shelf_unit","w":300,"d":150,"h":400,"shelves":3}
  {"type":"shelf_unit","w":400,"d":120,"h":200,"shelves":1,"top":false,"wall_holes":true}
  {"type":"bench","w":300,"d":120,"h":150,"back_brace":true,"text":"Ada"}
  {"type":"organizer","w":240,"d":120,"h":60,"compartments":3}

Sizes are outer millimetres: w = width (x), d = depth (y), h = height (z). `shelves` counts
every board that carries something, the bottom included. A panel's thickness grows along
its normal (u x v). Shelf units and benches are placed standing up for the Studio's 3D view
(y up, open front towards the viewer); an organizer is seen from above like a box.
"""

from __future__ import annotations

from typing import Any

KIT_TYPES = ("shelf_unit", "bench", "organizer")
X, Y, Z = [1, 0, 0], [0, 1, 0], [0, 0, 1]

GRAMMAR = {
    "shelf_unit": {"type": "shelf_unit", "w": "outer width mm", "d": "outer depth mm", "h": "outer height mm",
                   "shelves": "boards that carry something, bottom included (1-8)", "top": "bool, default true",
                   "wall_holes": "bool: two screw holes in the back panel", "text": "optional engraving on the top"},
    "bench": {"type": "bench", "w": "mm", "d": "mm", "h": "mm", "back_brace": "bool", "text": "optional engraving on the top"},
    "organizer": {"type": "organizer", "w": "mm", "d": "mm", "h": "mm", "compartments": "side-by-side cells (1-8)",
                  "text": "optional engraving on the front"},
    "note": "A kit expands to placed panels with finger and tab-slot joints. Use it for bookshelves, shelf units, wall shelves, "
            "benches, side tables, risers and divided trays instead of placing panels by hand.",
}


def r1(value: float) -> float:
    return round(float(value), 1)


def panel(label: str, w: float, h: float, origin: list[float], u: list[int], v: list[int], **extra: Any) -> dict[str, Any]:
    return {"type": "panel", "label": label, "role": "structural", "w": r1(w), "h": r1(h), "edges": "eeee",
            "placement": {"origin": [r1(c) for c in origin], "u": u, "v": v}, **extra}


def joints(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"id": f"C{i:02d}", "type": "finger_joint", "part_a": a, "part_b": b} for i, (a, b) in enumerate(pairs, 1)]


def find(parts: list[dict[str, Any]], label: str) -> dict[str, Any]:
    return next(p for p in parts if p["label"] == label)


def tab_into(parts: list[dict[str, Any]], tab_part: str, tab_id: str, tab: tuple[float, float, float, float],
             slot_part: str, slot: tuple[float, float, float, float]) -> None:
    """A tab on one panel's outline and the matching slot in the panel it enters."""
    tx, ty, tw, th = tab
    sx, sy, sw, sh = slot
    find(parts, tab_part).setdefault("tabs", []).append({"id": tab_id, "x": r1(tx), "y": r1(ty), "w": r1(tw), "h": r1(th)})
    find(parts, slot_part).setdefault("slots", []).append(
        {"x": r1(sx), "y": r1(sy), "w": r1(sw), "h": r1(sh), "mate": {"part": tab_part, "tab": tab_id}})


def engrave(part: dict[str, Any], text: str) -> None:
    height = max(6.0, min(14.0, r1(part["h"] / 4)))
    part["markings"] = [{"kind": "text", "value": text, "x": r1(part["w"] / 2), "y": r1(part["h"] / 2),
                         "height": height, "align": "center", "operation": "engrave"}]


def screw_holes(part: dict[str, Any], t: float) -> None:
    margin = max(4 * t, 15.0)
    y = r1(part["h"] - margin)
    part["holes"] = [{"x": r1(margin), "y": y, "d": 4, "purpose": "mount"},
                     {"x": r1(part["w"] - margin), "y": y, "d": 4, "purpose": "mount"}]


# --- families ---------------------------------------------------------------------------------
# Every family is built around its INNER volume: x in [0, wi], y in [0, di], z in [0, hi].
# A panel's nominal rectangle lies on a face of that volume and its thickness grows
# OUTWARDS, which is the Boxes.py finger-joint contract (nominal sizes are inner sizes, the
# fingers pass through the neighbour's thickness). Placing a wall's thickness inside the
# volume instead left every tab 1.5 mm short of its slot. W, D, H are the outer sizes the
# user asked for.
NX, NY = [-1, 0, 0], [0, -1, 0]


def _floor(wi: float, di: float, z: float = 0.0, label: str = "bottom") -> dict[str, Any]:
    return panel(label, wi, di, [wi, 0, z], NX, Y)          # thickness below (normal -z)


def _left(di: float, hi: float, label: str = "left") -> dict[str, Any]:
    return panel(label, di, hi, [0, di, 0], NY, Z)           # thickness at x < 0


def _right(wi: float, di: float, hi: float, label: str = "right") -> dict[str, Any]:
    return panel(label, di, hi, [wi, 0, 0], Y, Z)            # thickness at x > wi


def _back(wi: float, di: float, hi: float, label: str = "back") -> dict[str, Any]:
    return panel(label, wi, hi, [wi, di, 0], NX, Z)          # thickness at y > di


def carcass(W: float, D: float, H: float, t: float, middle: int, top: bool = True) -> tuple[list, list]:
    """Bookshelf / cubby / wall shelf: sides, bottom, optional top, back, shelves in between."""
    wi, di, hi = W - 2 * t, D - t, H - (2 * t if top else t)
    parts = [_floor(wi, di), _left(di, hi), _right(wi, di, hi), _back(wi, di, hi)]
    pairs = [("bottom", "left"), ("bottom", "right"), ("back", "bottom"), ("back", "left"), ("back", "right")]
    if top:
        parts.insert(1, panel("top", wi, di, [0, 0, hi], X, Y))   # thickness above
        pairs += [("top", "left"), ("top", "right"), ("back", "top")]
    tab_len = r1(di / 3)
    for i in range(1, middle + 1):
        z = r1(hi * i / (middle + 1))
        label = f"shelf-{i}"
        parts.append(panel(label, wi, di, [0, 0, z], X, Y))
        tab_into(parts, label, "L", (-t / 2, di / 2, t, tab_len), "left", (di / 2, z + t / 2, tab_len, t))
        tab_into(parts, label, "R", (wi + t / 2, di / 2, t, tab_len), "right", (di / 2, z + t / 2, tab_len, t))
    return parts, pairs


def bench(W: float, D: float, H: float, t: float, back: bool) -> tuple[list, list]:
    """Bench / side table / monitor riser / doll-house table: a top on two legs."""
    wi, di, hi = W - 2 * t, D - (t if back else 0), H - t
    parts = [
        panel("top", wi, di, [0, 0, hi], X, Y),
        _left(di, hi, "left-leg"),
        _right(wi, di, hi, "right-leg"),
    ]
    pairs = [("top", "left-leg"), ("top", "right-leg")]
    if back:
        parts.append(_back(wi, di, hi, "back-brace"))
        pairs += [("back-brace", "top"), ("back-brace", "left-leg"), ("back-brace", "right-leg")]
    return parts, pairs


def organizer(W: float, D: float, H: float, t: float, cells: int) -> tuple[list, list]:
    """Open tray of five panels with (cells - 1) dividers held by tabs in the floor and walls."""
    wi, di, hi = W - 2 * t, D - 2 * t, H - t
    parts = [
        _floor(wi, di),
        panel("front", wi, hi, [0, 0, 0], X, Z),                # thickness at y < 0
        _back(wi, di, hi),
        _left(di, hi),
        _right(wi, di, hi),
    ]
    pairs = [("bottom", "front"), ("bottom", "back"), ("bottom", "left"), ("bottom", "right"),
             ("front", "left"), ("front", "right"), ("back", "left"), ("back", "right")]
    lb, lw = r1(di / 3), r1(hi / 3)
    for i in range(1, cells):
        x = r1(wi * i / cells - t / 2)
        label = f"divider-{i}"
        parts.append(panel(label, di, hi, [x, 0, 0], Y, Z))     # thickness from x to x + t
        mid = x + t / 2
        # The floor and the back wall are drawn mirrored in x (their thickness faces out).
        tab_into(parts, label, "B", (di / 2, -t / 2, lb, t), "bottom", (wi - mid, di / 2, t, lb))
        tab_into(parts, label, "F", (-t / 2, hi / 2, t, lw), "front", (mid, hi / 2, t, lw))
        tab_into(parts, label, "K", (di + t / 2, hi / 2, t, lw), "back", (wi - mid, hi / 2, t, lw))
    return parts, pairs


def stand_up(parts: list[dict[str, Any]], depth: float) -> None:
    """Turn a kit built with z = height into the Studio viewer's frame, where y is up.

    The 3D view draws placements as they are and its camera has y up, with +z towards the
    viewer: a standard box is seen looking into its opening. Furniture built with z as
    height therefore lay on its back. This is one rigid quarter turn about x (height
    becomes y, the open front faces the viewer at z = depth), so every joint, tab and slot
    keeps fitting exactly as before; the cut parts do not change at all.
    """
    for part in parts:
        pose = part["placement"]
        x, y, z = pose["origin"]
        pose["origin"] = [r1(x), r1(z), r1(depth - y)]
        for axis in ("u", "v"):
            ax, ay, az = pose[axis]
            pose[axis] = [ax, az, -ay]


# --- expansion --------------------------------------------------------------------------------

def is_kit(part: Any) -> bool:
    return isinstance(part, dict) and str(part.get("type") or "").lower() in KIT_TYPES


def _size(kit: dict[str, Any], key: str, *aliases: str) -> float:
    for name in (key, *aliases):
        if kit.get(name) is not None:
            value = float(kit[name])
            if value <= 0:
                raise ValueError(f"{kit.get('type')}: {name} must be positive")
            return value
    raise ValueError(f"{kit.get('type')}: missing size {key}")


def _count(kit: dict[str, Any], key: str, default: int) -> int:
    value = int(float(kit.get(key) if kit.get(key) is not None else default))
    if not 1 <= value <= 8:
        raise ValueError(f"{kit.get('type')}: {key} must be between 1 and 8")
    return value


def _truthy(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"false", "0", "no", "none", ""}


def expand_kit(kit: dict[str, Any], thickness: float) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """The placed panels and finger-joint pairs of one kit. Raises ValueError on bad input."""
    kind = str(kit.get("type")).lower()
    t = float(thickness)
    W, D, H = _size(kit, "w", "x", "width"), _size(kit, "d", "y", "depth"), _size(kit, "h", "height")
    if min(W, D, H) < 10 * t:
        raise ValueError(f"{kind}: every size must be at least {10 * t:g} mm for {t:g} mm material")
    text = str(kit.get("text") or "").strip()
    if kind == "shelf_unit":
        shelves = _count(kit, "shelves", 1)
        if H / shelves < 8 * t:
            raise ValueError(f"shelf_unit: {shelves} shelves do not fit in {H:g} mm")
        parts, pairs = carcass(W, D, H, t, shelves - 1, _truthy(kit.get("top"), True))
        if _truthy(kit.get("wall_holes"), False):
            screw_holes(find(parts, "back"), t)
        target = "top" if any(p["label"] == "top" for p in parts) else "back"
        stand_up(parts, D - t)
    elif kind == "bench":
        parts, pairs = bench(W, D, H, t, _truthy(kit.get("back_brace"), False))
        target = "top"
        stand_up(parts, D)
    else:
        cells = _count(kit, "compartments", 1)
        if W / cells < 8 * t:
            raise ValueError(f"organizer: {cells} compartments do not fit in {W:g} mm")
        parts, pairs = organizer(W, D, H, t, cells)
        target = "front"
    if text:
        engrave(find(parts, target), text)
    return parts, pairs


def expand_kits(primitives: list[Any] | None, parameters: dict[str, Any] | None) -> tuple[list[Any] | None, dict[str, Any] | None]:
    """Replace every kit primitive with its panels and add their joints to the parameters.

    Inputs are not modified. Designs without a kit come back unchanged.
    """
    if not primitives or not any(is_kit(p) for p in primitives):
        return primitives, parameters
    params = dict(parameters or {})
    thickness = float(params.get("thickness") or 3.0)
    many = sum(1 for p in primitives if is_kit(p)) > 1
    out: list[Any] = []
    pairs: list[tuple[str, str]] = []
    number = 0
    for part in primitives:
        if not is_kit(part):
            out.append(part)
            continue
        number += 1
        panels, kit_pairs = expand_kit(part, thickness)
        if many:  # two kits in one design: keep their labels apart
            prefix = f"k{number}-"
            for p in panels:
                p["label"] = prefix + p["label"]
                for slot in p.get("slots") or []:
                    if isinstance(slot.get("mate"), dict):
                        slot["mate"]["part"] = prefix + slot["mate"]["part"]
            kit_pairs = [(prefix + a, prefix + b) for a, b in kit_pairs]
        out.extend(panels)
        pairs.extend(kit_pairs)
    existing = [c for c in params.get("connections") or [] if isinstance(c, dict)]
    added = joints(pairs)
    for i, row in enumerate(added, len(existing) + 1):
        row["id"] = f"K{i:02d}"
    params["connections"] = existing + added
    return out, params
