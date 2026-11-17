"""Draw the synthetic part of the image benchmark: pictures whose right answer is known.

  .venv/Scripts/python.exe tools/vision_eval/make_synthetic.py

Three kinds, each drawn from a real design that passes the gate:
  render    - a shaded 3D view of the assembled panels (no sizes on it: proportions only)
  sketch    - a wobbly pencil-style drawing with the sizes written on it
  cut_sheet - the flat cutting layout from the design's own DXF

Real photos are not made here; add them by hand (see vision_eval.py). The rows this script
writes replace the earlier synthetic rows in images.json and keep every hand-added row.
Same seed, same pictures: the set is reproducible.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"
MANIFEST = HERE / "images.json"
FONT = ROOT / "fonts" / "Arimo-Regular.ttf"
PREFIXES = ("render-", "sketch-", "cut-syn-")

# (id, about, primitives, min_panels, max_panels, types, size_mm or None, text)
RENDERS = [
    ("render-shelf-01", "3 raflı kitaplık (taban dahil), üstü kapalı, arkalıklı",
     [{"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 3}], 6, 8, ["shelf_unit"]),
    ("render-wallshelf-01", "üstü açık duvar rafı, arkada iki vida deliği",
     [{"type": "shelf_unit", "w": 400, "d": 120, "h": 200, "shelves": 1, "top": False, "wall_holes": True}], 3, 5, ["shelf_unit"]),
    ("render-bench-01", "iki ayaklı küçük sehpa, arkada destek levhası",
     [{"type": "bench", "w": 300, "d": 120, "h": 150, "back_brace": True}], 3, 5, ["bench"]),
    ("render-organizer-01", "3 bölmeli masaüstü düzenleyici tepsi",
     [{"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 3}], 6, 8, ["organizer"]),
    ("render-box-01", "kapaklı dikdörtgen kutu",
     [{"type": "box", "x": 120, "y": 80, "h": 60, "lid": True}], 5, 7, []),
    ("render-box-02", "üstü açık küp kutu",
     [{"type": "box", "x": 100, "y": 100, "h": 100}], 4, 6, []),
]

# Sketches carry their sizes. kind of drawing: outline + inner lines.
SKETCHES = [
    ("sketch-shelf-01", "kitaplık çizimi, 4 raf, ölçüler yazılı", {"w": 400, "d": 200, "h": 600, "shelves": 3, "title": "kitaplık"},
     [{"type": "shelf_unit", "w": 400, "d": 200, "h": 600, "shelves": 4}], 6, 10, ["shelf_unit"], [400, 200, 600], ""),
    ("sketch-box-01", "kapaklı kutu çizimi, ölçüler yazılı", {"w": 150, "d": 100, "h": 80, "lid": True, "title": "kapaklı kutu"},
     [{"type": "box", "x": 150, "y": 100, "h": 80, "lid": True}], 5, 7, [], [150, 100, 80], ""),
    ("sketch-organizer-01", "4 bölmeli düzenleyici çizimi, ölçüler yazılı", {"w": 300, "d": 100, "h": 80, "dividers": 3},
     [{"type": "organizer", "w": 300, "d": 100, "h": 80, "compartments": 4}], 6, 10, ["organizer"], [300, 100, 80], ""),
    ("sketch-bench-01", "sehpa çizimi: üst tabla ve iki ayak, ölçüler yazılı", {"w": 350, "d": 200, "h": 250, "legs": True, "title": "sehpa"},
     [{"type": "bench", "w": 350, "d": 200, "h": 250}], 3, 5, ["bench"], [350, 200, 250], ""),
    ("sketch-holder-01", "üstü açık kalemlik çizimi, ölçüler yazılı", {"w": 80, "d": 80, "h": 100},
     [{"type": "box", "x": 80, "y": 80, "h": 100}], 4, 6, [], [80, 80, 100], ""),
    ("sketch-plaque-01", "üzerinde ADA yazan isim levhası çizimi", {"w": 200, "h": 80, "flat": True, "text": "ADA"},
     [{"type": "panel", "w": 200, "h": 80, "edges": "eeee", "markings": [{"kind": "text", "value": "ADA", "x": 100, "y": 40, "height": 30, "align": "center", "operation": "engrave"}]}],
     1, 2, [], None, "ADA"),
]

CUTS = [
    ("cut-syn-box-01", "kapaklı kutunun kesim planı (6 parça, parmak geçmeli)",
     [{"type": "box", "x": 120, "y": 80, "h": 60, "lid": True}], 5, 7, []),
    ("cut-syn-organizer-01", "3 bölmeli düzenleyicinin kesim planı",
     [{"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 3}], 6, 8, ["organizer"]),
    ("cut-syn-shelf-01", "2 raflı kitaplığın kesim planı",
     [{"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 2}], 5, 7, ["shelf_unit"]),
]


def build(primitives: list[dict[str, Any]]) -> dict[str, Any]:
    import payas_cad

    built = payas_cad.create_design(primitives=primitives, parameters={"thickness": 3})
    if built.get("final_status") != "PROTOTYPE READY":
        raise SystemExit(f"a benchmark design must pass the gate: {primitives}")
    return built


# --- render ----------------------------------------------------------------------------------
def world_polygons(built: dict[str, Any]) -> list[list[tuple[float, float, float]]]:
    from assembly_result import panels_for_viewer

    polys = []
    for panel in panels_for_viewer(built["assembly_result"])["panels"]:
        m = panel["transform"]["matrix"]
        pts = []
        for x, y in panel["outline_local_mm"]:
            pts.append(tuple(m[r][0] * x + m[r][1] * y + m[r][3] for r in range(3)))
        polys.append(pts)
    return polys


def draw_render(built: dict[str, Any], path: Path, z_up: bool) -> None:
    from PIL import Image, ImageDraw

    polys = world_polygons(built)
    if z_up:  # boxes and trays come in z-up (the Studio looks into their opening); turn them into the viewer's y-up frame, front towards us
        polys = [[(x, z, -y) for x, y, z in poly] for poly in polys]
    yaw, pitch = math.radians(35), math.radians(22)

    def cam(p):
        x, y, z = p
        x1 = x * math.cos(yaw) + z * math.sin(yaw)
        z1 = -x * math.sin(yaw) + z * math.cos(yaw)
        y2 = y * math.cos(pitch) - z1 * math.sin(pitch)
        z2 = y * math.sin(pitch) + z1 * math.cos(pitch)
        return x1, y2, z2

    flat = [[cam(p) for p in poly] for poly in polys]
    xs = [p[0] for poly in flat for p in poly]
    ys = [p[1] for poly in flat for p in poly]
    size, pad = 900, 70
    scale = (size - 2 * pad) / max(max(xs) - min(xs), max(ys) - min(ys))
    ox = (size - (max(xs) - min(xs)) * scale) / 2
    oy = (size - (max(ys) - min(ys)) * scale) / 2

    def screen(p):
        return ox + (p[0] - min(xs)) * scale, size - (oy + (p[1] - min(ys)) * scale)

    img = Image.new("RGB", (size, size), (238, 238, 236))
    draw = ImageDraw.Draw(img)
    light = (0.35, 0.8, 0.5)
    for poly in sorted(flat, key=lambda q: sum(p[2] for p in q) / len(q)):
        a, b, c = poly[0], poly[len(poly) // 3], poly[2 * len(poly) // 3]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        ln = math.sqrt(sum(k * k for k in n)) or 1
        shade = 0.55 + 0.45 * abs(sum(n[i] / ln * light[i] for i in range(3)))
        fill = tuple(int(c * shade) for c in (205, 160, 105))
        pts = [screen(p) for p in poly]
        draw.polygon(pts, fill=fill, outline=(92, 66, 40))
    img.save(path, optimize=True)


# --- sketch ----------------------------------------------------------------------------------
def draw_sketch(spec: dict[str, Any], path: Path, rng: random.Random) -> None:
    from PIL import Image, ImageDraw, ImageFont

    size = 900
    img = Image.new("RGB", (size, size), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), 30)
    small = ImageFont.truetype(str(FONT), 26)
    ink = (40, 40, 60)

    def line(a, b, width=3):
        # A pencil line: a few wobbling segments, drawn twice.
        for _ in range(2):
            pts = []
            for i in range(9):
                t = i / 8
                pts.append((a[0] + (b[0] - a[0]) * t + rng.uniform(-1.6, 1.6), a[1] + (b[1] - a[1]) * t + rng.uniform(-1.6, 1.6)))
            draw.line(pts, fill=ink, width=width, joint="curve")

    w, h = float(spec["w"]), float(spec["h"])
    d = float(spec.get("d") or 0)
    if spec.get("flat"):
        s = 560 / w
        x0, y0 = 170, 450 - h * s / 2
        x1, y1 = x0 + w * s, y0 + h * s
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            line(a, b)
        big = ImageFont.truetype(str(FONT), int(h * s * 0.5))
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), spec["text"], font=big, fill=ink, anchor="mm")
        draw.text(((x0 + x1) / 2, y1 + 50), f"{w:g} mm", font=font, fill=ink, anchor="mm")
        draw.text((x0 - 30, (y0 + y1) / 2), f"{h:g} mm", font=font, fill=ink, anchor="rm")
        draw.text((x0, 120), "isim levhası, 3 mm kontrplak", font=small, fill=ink)
        img.save(path, optimize=True)
        return

    # Oblique view: front face square-on, depth going up and right at 35 degrees.
    k = 0.5
    s = 520 / max(w + d * k * math.cos(math.radians(35)), h + d * k * math.sin(math.radians(35)))
    dx, dy = d * k * s * math.cos(math.radians(35)), -d * k * s * math.sin(math.radians(35))
    x0 = (size - (w * s + dx)) / 2
    y1 = (size + (h * s - dy)) / 2 + 20
    y0 = y1 - h * s
    x1 = x0 + w * s
    F = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    B = [(x + dx, y + dy) for x, y in F]
    if spec.get("legs"):  # a table top on two legs, front edge open
        top = h * s * 0.12
        line(F[0], F[1]); line(F[0], (x0, y0 + top)); line(F[1], (x1, y0 + top)); line((x0, y0 + top), (x1, y0 + top))
        line(F[0], B[0]); line(F[1], B[1]); line(B[0], B[1]); line(B[1], (B[1][0], B[1][1] + top))
        leg = w * s * 0.06
        for xa in (x0, x1 - leg):
            line((xa, y0 + top), (xa, y1)); line((xa + leg, y0 + top), (xa + leg, y1)); line((xa, y1), (xa + leg, y1))
        line((x1, y0 + top), (x1 + dx, y0 + top + dy)); line((x1 + dx, y0 + top + dy), (x1 + dx, y1 + dy))
    else:
        for i in range(4):
            line(F[i], F[(i + 1) % 4])
        line(F[0], B[0]); line(F[1], B[1]); line(F[2], B[2]); line(B[0], B[1]); line(B[1], B[2])
        for i in range(1, int(spec.get("shelves") or 0) + 1):
            y = y1 - (y1 - y0) * i / (int(spec["shelves"]) + 1)
            line((x0, y), (x1, y), 2); line((x0, y), (x0 + dx * 0.6, y + dy * 0.6), 2)
        for i in range(1, int(spec.get("dividers") or 0) + 1):
            x = x0 + (x1 - x0) * i / (int(spec["dividers"]) + 1)
            line((x, y0), (x, y1), 2); line((x, y0), (x + dx, y0 + dy), 2)
        if spec.get("lid"):
            lift = 34
            Lf = [(x0, y0 - lift), (x1, y0 - lift)]
            line(Lf[0], Lf[1]); line(Lf[0], (Lf[0][0] + dx, Lf[0][1] + dy)); line(Lf[1], (Lf[1][0] + dx, Lf[1][1] + dy))
            line((Lf[0][0] + dx, Lf[0][1] + dy), (Lf[1][0] + dx, Lf[1][1] + dy))
            line((x0, y0 - lift), (x0, y0 - lift + 10)); line((x1, y0 - lift), (x1, y0 - lift + 10))
            draw.text((x1 + dx + 20, y0 - lift + dy / 2), "kapak", font=small, fill=ink, anchor="lm")
    # Size labels with little arrows.
    draw.text(((x0 + x1) / 2, y1 + 45), f"{w:g}", font=font, fill=ink, anchor="mm")
    line((x0, y1 + 20), (x1, y1 + 20), 2)
    draw.text((x0 - 25, (y0 + y1) / 2), f"{h:g}", font=font, fill=ink, anchor="rm")
    line((x0 - 12, y0), (x0 - 12, y1), 2)
    draw.text((x1 + dx / 2 + 28, y1 + dy / 2 + 8), f"{d:g}", font=font, fill=ink, anchor="lm")
    draw.text((60, 60), "ölçüler mm", font=small, fill=ink)
    if spec.get("title"):
        draw.text((60, 100), spec["title"], font=font, fill=ink)
    img.save(path, optimize=True)


# --- cut sheet -------------------------------------------------------------------------------
def dxf_polylines(path: Path) -> list[list[tuple[float, float]]]:
    lines = [s.strip() for s in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    out, cur, x = [], None, None
    for i in range(0, len(lines) - 1, 2):
        code, value = lines[i], lines[i + 1]
        if code == "0":
            if value == "POLYLINE":
                cur = []
                out.append(cur)
            elif value == "SEQEND":
                cur = None
        elif cur is not None:
            if code == "10":
                x = float(value)
            elif code == "20" and x is not None:
                cur.append((x, float(value)))
                x = None
    return [p for p in out if len(p) > 1]


def find_output(name: str) -> Path:
    for base in (os.environ.get("MCP_OUTPUT_DIR"), os.environ.get("MCP_DATA_DIR"), str(ROOT / "output")):
        if base:
            hits = list(Path(base).rglob(name))
            if hits:
                return hits[0]
    raise SystemExit(f"{name} was not written")


def draw_cut(built: dict[str, Any], path: Path) -> None:
    from PIL import Image, ImageDraw

    polys = dxf_polylines(find_output(built["dxf_id"]))
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    width = 1200
    pad = 40
    scale = (width - 2 * pad) / (max(xs) - min(xs))
    height = int((max(ys) - min(ys)) * scale + 2 * pad)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for poly in polys:
        pts = [(pad + (x - min(xs)) * scale, height - (pad + (y - min(ys)) * scale)) for x, y in poly]
        draw.line(pts, fill=(200, 0, 0), width=2)
    img.save(path, optimize=True)


def row(id_, kind, about, file, lo, hi, types, size=None, text=""):
    out = {"id": id_, "file": file, "kind": kind, "about": about, "min_panels": lo, "max_panels": hi}
    if types:
        out["types"] = types
    if size:
        out["size_mm"] = size
    if text:
        out["text"] = text
    out["synthetic"] = True
    return out


def main() -> int:
    os.environ.setdefault("MCP_DATA_DIR", tempfile.mkdtemp(prefix="lasermcp-synimg-"))
    IMAGES.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    rows = []
    for id_, about, prims, lo, hi, types in RENDERS:
        built = build(prims)
        draw_render(built, IMAGES / f"{id_}.png", z_up=prims[0]["type"] in ("box", "organizer"))
        rows.append(row(id_, "render", about, f"{id_}.png", lo, hi, types))
    for id_, about, spec, prims, lo, hi, types, size, text in SKETCHES:
        build(prims)  # the answer must itself be buildable
        draw_sketch(spec, IMAGES / f"{id_}.png", rng)
        rows.append(row(id_, "sketch", about, f"{id_}.png", lo, hi, types, size, text))
    for id_, about, prims, lo, hi, types in CUTS:
        built = build(prims)
        draw_cut(built, IMAGES / f"{id_}.png")
        rows.append(row(id_, "cut_sheet", about, f"{id_}.png", lo, hi, types))
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    kept = [r for r in data["images"] if not str(r.get("id", "")).startswith(PREFIXES)]
    data["images"] = kept + rows
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} synthetic images, {len(kept)} hand-added kept -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
