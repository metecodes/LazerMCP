"""Boxes.py toolbox: the incoming AI composes parts; we do not add a kit per product."""

from __future__ import annotations

from typing import Any

import boxes_adapter  # noqa: F401  # sys.path for vendor Boxes.py

from boxes import Boxes
from boxes import edges
from boxes_adapter import PAYAS_DEFAULTS, _svg_metrics

ASSEMBLY_TYPES = frozenset(
    {
        "box",
        "panel",
        "wall",
        "rect",
        "disc",
        "disk",
        "circle",
        "washer",
        "spacer",
        "triangle",
        "gable",
        "roof",
        "roof_panel",
        "polygon",
    }
)

GRAMMAR = {
    "edges": (
        "rectangularWall edges are bottom,right,top,left. "
        "e=straight, f=male fingers, F=female finger holes."
    ),
    "box": {
        "type": "box",
        "x": "inner width mm",
        "y": "inner depth mm",
        "h": "inner height mm",
        "bottom": True,
        "lid": False,
        "top": "e",
        "walls": {
            "front": {
                "holes": [{"x": 40, "y": 90, "d": 4}],
                "slots": [{"x": 40, "y": 40, "w": 20, "h": 28}],
            }
        },
    },
    "panel": {
        "type": "panel",
        "w": 80,
        "h": 120,
        "edges": "eFeF",
        "count": 1,
        "holes": [{"x": 40, "y": 60, "d": 4}],
        "slots": [{"x": 40, "y": 40, "w": 10, "h": 3}],
        "finger_holes": [{"x": 1.5, "y": 1.5, "length": 80, "angle": 0}],
    },
    "disc": {"type": "disc", "d": 50, "hole": 4, "count": 1},
    "triangle": {"type": "triangle", "w": 80, "h": 28, "edges": "eee", "count": 2},
    "coords": "x,y are mm from the bottom-left of that part (inner face).",
    "never": "Never request a new MCP tool. Never hand-write SVG. Call create_design with primitives.",
}

_EDGE_OK = set("eEfFhH")
_MAX_PARTS = 48


def _num(value: Any, default: float | None = None) -> float:
    if value is None or value == "":
        if default is None:
            raise ValueError("missing number")
        return float(default)
    return float(value)


def _int(value: Any, default: int = 1, lo: int = 1, hi: int = 20) -> int:
    n = int(value if value is not None else default)
    return max(lo, min(hi, n))


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def is_assembly(primitives: list[Any] | None) -> bool:
    if not primitives:
        return False
    for item in primitives:
        if isinstance(item, dict) and _kind(item) in ASSEMBLY_TYPES:
            return True
    return False


def _edges4(raw: Any, default: str = "eeee") -> str:
    text = "".join(str(raw or default).strip() or default)
    if len(text) != 4:
        raise ValueError(f"panel edges must be 4 letters (bottom,right,top,left), got {text!r}")
    bad = [c for c in text if c not in _EDGE_OK]
    if bad:
        raise ValueError(f"unknown edge {bad}. Use e, f, F (h allowed).")
    return text


def _edges3(raw: Any, default: str = "eee") -> str:
    text = "".join(str(raw or default).strip() or default)
    if len(text) not in {2, 3}:
        raise ValueError(f"triangle edges must be 2 or 3 letters, got {text!r}")
    bad = [c for c in text if c not in _EDGE_OK]
    if bad:
        raise ValueError(f"unknown edge {bad}. Use e, f, F (h allowed).")
    return text


def _features(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "holes": list(part.get("holes") or []),
        "slots": list(part.get("slots") or part.get("rect_holes") or []),
        "finger_holes": list(part.get("finger_holes") or part.get("fingerHoles") or []),
    }


class PayasToolbox(Boxes):
    """Compose rectangularWall / disc / triangle from a JSON recipe. Not a named product."""

    ui_group = "Unlisted"
    webinterface = False

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings)
        self.parts_spec: list[dict[str, Any]] = []

    def render(self) -> None:
        drawn = 0
        for part in self.parts_spec:
            if not isinstance(part, dict):
                continue
            n = self._render_part(part)
            drawn += n
            if drawn > _MAX_PARTS:
                raise ValueError(f"too many parts (max {_MAX_PARTS})")
        if drawn < 1:
            raise ValueError("primitives produced no parts")

    def _callback(self, feats: dict[str, Any]):
        def _cb() -> None:
            for hole in feats.get("holes") or []:
                if not isinstance(hole, dict):
                    continue
                x = _num(hole.get("x") or hole.get("cx"), 0)
                y = _num(hole.get("y") or hole.get("cy"), 0)
                d = hole.get("d") or hole.get("diameter")
                r = hole.get("r") or hole.get("radius")
                if d:
                    self.hole(x, y, d=float(d))
                elif r:
                    self.hole(x, y, r=float(r))
            for slot in feats.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                x = _num(slot.get("x") or slot.get("cx"), 0)
                y = _num(slot.get("y") or slot.get("cy"), 0)
                w = _num(slot.get("w") or slot.get("dx") or slot.get("width"), 0)
                h = _num(slot.get("h") or slot.get("dy") or slot.get("height"), 0)
                if w <= 0 or h <= 0:
                    continue
                r = float(slot.get("r") or 0)
                self.rectangularHole(x, y, w, h, r=r, center_x=True, center_y=True)
            for row in feats.get("finger_holes") or []:
                if not isinstance(row, dict):
                    continue
                x = _num(row.get("x"), 0)
                y = _num(row.get("y"), 0)
                length = _num(row.get("length") or row.get("l"), 0)
                angle = _num(row.get("angle") or row.get("a"), 0)
                if length <= 0:
                    continue
                self.fingerHolesAt(x, y, length, angle)

        return _cb

    def _wall_cb(self, feats: dict[str, Any]):
        cb = self._callback(feats)
        holes = feats.get("holes") or feats.get("slots") or feats.get("finger_holes")
        if not holes:
            return None
        return [cb]

    def _render_part(self, part: dict[str, Any]) -> int:
        kind = _kind(part)
        count = _int(part.get("count") or part.get("n"), 1)
        label = str(part.get("label") or kind or "")
        if kind in {"box"}:
            self._box(part)
            return 4 + int(bool(part.get("bottom", True))) + int(bool(part.get("lid")))
        if kind in {"panel", "wall", "rect", "roof", "roof_panel"}:
            w = _num(part.get("w") or part.get("x") or part.get("width"), 80)
            h = _num(part.get("h") or part.get("y") or part.get("height") or part.get("length"), 80)
            edge = _edges4(part.get("edges") or part.get("edge"), "eeee")
            cb = self._wall_cb(_features(part))
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.rectangularWall(w, h, edge, callback=cb, move="up", label=name)
            return count
        if kind in {"disc", "disk", "circle", "washer", "spacer"}:
            d = _num(part.get("d") or part.get("diameter") or part.get("w"), 40)
            hole = _num(part.get("hole") or part.get("shaft") or part.get("d_hole"), 0 if kind in {"disc", "disk", "circle"} else 4)
            if kind in {"washer", "spacer"} and hole <= 0:
                hole = max(3.0, float(self.thickness) + 0.2)
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.parts.disc(d, hole=hole, move="up", label=name)
            return count
        if kind in {"triangle", "gable"}:
            w = _num(part.get("w") or part.get("x") or part.get("width"), 80)
            h = _num(part.get("h") or part.get("y") or part.get("rise") or part.get("height"), 30)
            edge = _edges3(part.get("edges") or part.get("edge"), "eee")
            cb = self._wall_cb(_features(part))
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.rectangularTriangle(w, h, edge, callback=cb, move="up", label=name)
            return count
        if kind == "polygon":
            borders = part.get("borders") or part.get("sides")
            if not isinstance(borders, list) or len(borders) < 4:
                raise ValueError("polygon needs borders: [length, angle, length, angle, ...]")
            edge = str(part.get("edge") or part.get("edges") or "e")
            if any(c not in _EDGE_OK for c in edge):
                raise ValueError("polygon edge must be e/f/F")
            cb = self._wall_cb(_features(part))
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.polygonWall(list(borders), edge=edge, callback=cb, move="up", label=name)
            return count
        raise ValueError(
            f"Unknown primitive type {kind!r}. Assembly types: "
            + ", ".join(sorted(ASSEMBLY_TYPES))
        )

    def _box(self, part: dict[str, Any]) -> None:
        x = _num(part.get("x") or part.get("w") or part.get("width"), 80)
        y = _num(part.get("y") or part.get("d") or part.get("depth"), 80)
        h = _num(part.get("h") or part.get("height"), 80)
        if min(x, y, h) < 8:
            raise ValueError("box x, y, h must be at least 8 mm inner")
        top = str(part.get("top") or "e")[:1]
        if top not in _EDGE_OK:
            top = "e"
        bottom_on = bool(part.get("bottom", True))
        lid_on = bool(part.get("lid", False))
        b = "F" if bottom_on else "e"
        walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
        ignore = [1, 6] if bottom_on else []

        def wall(name: str) -> dict[str, Any]:
            raw = walls.get(name) if isinstance(walls.get(name), dict) else {}
            return _features(raw)

        self.rectangularWall(
            x, h, f"{b}F{top}F", ignore_widths=ignore,
            callback=self._wall_cb(wall("front")), move="up", label="front",
        )
        self.rectangularWall(
            x, h, f"{b}F{top}F", ignore_widths=ignore,
            callback=self._wall_cb(wall("back")), move="up", label="back",
        )
        if bottom_on:
            self.rectangularWall(
                x, y, "ffff", callback=self._wall_cb(wall("bottom")), move="up", label="bottom",
            )
        self.rectangularWall(
            y, h, f"{b}f{top}f", ignore_widths=ignore,
            callback=self._wall_cb(wall("left")), move="up", label="left",
        )
        self.rectangularWall(
            y, h, f"{b}f{top}f", ignore_widths=ignore,
            callback=self._wall_cb(wall("right")), move="up", label="right",
        )
        if lid_on:
            self.rectangularWall(
                x, y, "ffff" if top in "fF" else "eeee",
                callback=self._wall_cb(wall("top") or wall("lid")),
                move="up",
                label="lid",
            )


def compile_toolbox(primitives: list[Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    if not primitives:
        raise ValueError("primitives is empty")
    parts = [p for p in primitives if isinstance(p, dict) and _kind(p) in ASSEMBLY_TYPES]
    if not parts:
        raise ValueError("no assembly primitives (box, panel, disc, triangle, polygon)")
    params = parameters or {}
    thickness = float(params.get("thickness") or PAYAS_DEFAULTS["thickness"])
    box = PayasToolbox()
    box.parseArgs(
        [
            f"--thickness={thickness}",
            f"--burn={PAYAS_DEFAULTS['burn']}",
            "--format=svg",
            "--labels=0",
            "--reference=0",
            "--tabs=0",
            "--qr_code=0",
        ]
    )
    box.parts_spec = parts
    box.open()
    box.render()
    data = box.close()
    svg_bytes = data.getvalue() if hasattr(data, "getvalue") else data.read()
    metrics = _svg_metrics(svg_bytes.decode("utf-8", errors="replace"))
    return {
        "svg_bytes": svg_bytes,
        "width_mm": metrics.get("width_mm"),
        "height_mm": metrics.get("height_mm"),
        "count": len(parts),
        "card_w": None,
        "card_h": None,
        "preset": "toolbox",
        "parts": [str(p.get("label") or _kind(p)) for p in parts],
        "path_count": metrics.get("path_count"),
    }
