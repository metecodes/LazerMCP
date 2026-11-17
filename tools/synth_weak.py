"""Gate-checked training examples for the request types the third model got wrong.

The 2026-11-17 benchmark of the local model (`lasermcp`, third round) left these weak:
electronics boxes with a display window, card holders, holders with compartments, plant pot
covers with drain holes, robot base plates and breadboard bases. The model drew one flat
plate, misread "16x2 LCD" as a 16×2 mm size, or put screw holes inside the window.

Every design here comes from a parametric family with the real module sizes (the same ones
llm_client.request_text adds to a request), runs through the same gate and faithfulness
filter as `train.py collect`, and is kept only when both pass. Prompts of the benchmark set
are never used. The rows land in output/train/synthetic_weak.jsonl; `train.py build` reads
every synthetic*.jsonl next to examples.jsonl.

  .venv/Scripts/python.exe tools/synth_weak.py --count 240
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "output" / "train" / "synthetic_weak.jsonl"
NAMES = ["STEM", "Atölye", "Ada", "Kerem", "Zeynep", "Maker", "Lab", "Ofis", "Robot", "Defne", "Ali"]

# Display modules: (names in a request, window w×h, mounting hole spacing x×y or None).
DISPLAYS = (
    (("16x2 LCD", "1602 LCD", "LCD 16x2"), (72.0, 25.0), (75.0, 31.0)),
    (("0.96 inç OLED", "OLED"), (26.0, 15.0), (23.5, 23.8)),
    (("20x4 LCD",), (77.0, 26.0), (93.0, 55.0)),
)


def _r(v: float) -> float:
    return round(v, 1)


def _size(rng: random.Random, dims: tuple[float, ...]) -> str:
    if rng.random() < 0.35:
        return "x".join(f"{v / 10:g}" for v in dims) + " cm"
    return "x".join(f"{v:g}" for v in dims) + " mm"


def enclosure(rng: random.Random, en: bool) -> tuple[str, list[dict[str, Any]], str] | None:
    """A closed electronics box: display window and its screw holes on the front, extras on the sides."""
    names, (ww, wh), spacing = rng.choice(DISPLAYS)
    display = rng.choice(names)
    spacing_x, spacing_y = spacing if spacing else (ww + 14, wh + 14)
    x = float(rng.choice(range(int(spacing_x + 20), int(spacing_x + 61), 5)))
    h = float(rng.choice(range(int(spacing_y + 24), int(spacing_y + 46), 2)))
    y = float(rng.choice(range(50, 101, 5)))
    cx, cy = x / 2, h / 2
    front: dict[str, Any] = {"slots": [{"x": _r(cx), "y": _r(cy), "w": ww, "h": wh, "purpose": "window"}]}
    front["holes"] = [{"x": _r(cx + sx * spacing_x / 2), "y": _r(cy + sy * spacing_y / 2), "d": 3.2, "purpose": "mount"}
                      for sx in (-1, 1) for sy in (-1, 1)]
    walls: dict[str, Any] = {"front": front}
    extras_tr, extras_en = [], []
    if rng.random() < 0.5:
        walls["left"] = {"slots": [{"x": _r(y / 2), "y": 14.0, "w": 13.0, "h": 11.0, "purpose": "cable"}]}
        extras_tr.append("yanında USB girişi")
        extras_en.append("a USB port on the side")
    if rng.random() < 0.4:
        # Round vent holes: a thin slot reads as a tab slot to the gate and needs a partner tab.
        walls["back"] = {"holes": [{"x": _r(x / 2 + dx), "y": _r(h * 0.6), "d": 5.0, "purpose": "vent"} for dx in (-20, -10, 0, 10, 20)]}
        extras_tr.append("arkası havalandırmalı")
        extras_en.append("vents in the back")
    noun_tr = rng.choice(["kutu", "muhafaza", "kasa"])
    use_tr = rng.choice(["", "sensör ", "sıcaklık göstergesi ", "saat ", "Arduino "])
    use_en = rng.choice(["", "sensor ", "thermometer ", "clock ", "Arduino project "])
    sized = rng.random() < 0.5
    size = _size(rng, (x, y, h)) if sized else ""
    if en:
        prompt = ", ".join(p for p in (f"{use_en}enclosure for a {display} display with a lid", *extras_en, size) if p)
    else:
        lead = f"{display} ekran için ön panelli {noun_tr}" if rng.random() < 0.5 else f"{display} ekranlı {use_tr}{noun_tr}"
        prompt = ", ".join(p for p in (f"{size} {lead}".strip(), "kapaklı", *extras_tr) if p)
    box = {"type": "box", "x": x, "y": y, "h": h, "lid": True, "walls": walls}
    summary = (f"Closed box; front window {ww:g}x{wh:g} mm for the {display} with 4 screw holes." if en
               else f"Kapaklı kutu; önde {display} için {ww:g}x{wh:g} mm pencere ve 4 vida deliği.")
    return prompt, [box], summary


def card_holder(rng: random.Random, en: bool) -> tuple[str, list[dict[str, Any]], str] | None:
    """An open box a card stack stands in, cards showing over the top."""
    cards = rng.choice([("kartvizit", "business card", 90, 55), ("kartvizit", "business card", 85, 55),
                        ("not kağıdı", "sticky note", 76, 76), ("oyun kartı", "playing card", 63, 88)])
    noun_tr, noun_en, cw, ch = cards
    x = float(cw + rng.choice([4, 6, 8]))
    y = float(rng.choice([20, 25, 30, 35, 40]))
    h = float(ch - rng.choice([10, 15, 20]))
    if h < 30:
        h = 30.0
    box = {"type": "box", "x": x, "y": y, "h": h, "lid": False}
    holder_tr = {"kartvizit": "kartvizitlik", "not kağıdı": "not kağıdı tutucu", "oyun kartı": "oyun kartı kutusu"}[noun_tr]
    label = rng.choice(NAMES) if rng.random() < 0.3 else ""
    if label and h - 2 * 6 >= 10 and x >= 60:
        box["walls"] = {"front": {"markings": [{"kind": "text", "value": label, "x": _r(x / 2), "y": _r(h / 2), "height": 8,
                                                 "align": "center", "operation": "engrave"}]}}
    if en:
        prompt = f"{noun_en} holder for {cw}x{ch} mm cards" if rng.random() < 0.6 else f"{noun_en} holder"
        prompt += f", '{label}' engraved on the front" if "walls" in box else ""
        summary = f"Open box {x:g}x{y:g}x{h:g} mm; the cards stand inside and show over the top."
    else:
        prompt = f"{holder_tr}, {cw}x{ch} mm kartlar için" if rng.random() < 0.6 else holder_tr
        prompt += f", önünde '{label}' yazan" if "walls" in box else ""
        summary = f"Üstü açık {x:g}x{y:g}x{h:g} mm kutu; kartlar içinde dik durur, üstten görünür."
    return prompt, [box], summary


def holder(rng: random.Random, en: bool) -> tuple[str, list[dict[str, Any]], str] | None:
    """Compartment holders (remotes, phones, brushes…) as the organizer kit."""
    thing_tr, thing_en, cell_w, depth, height = rng.choice([
        ("kumanda", "remote control", 55, 80, 110), ("telefon", "phone", 85, 70, 100), ("fırça", "brush", 45, 60, 120),
        ("kalem", "pen", 40, 60, 100), ("tornavida", "screwdriver", 35, 50, 110), ("tablet kalemi", "stylus", 35, 50, 90),
    ])
    n = rng.randint(2, 5)
    w = float(n * cell_w + rng.choice([0, 10, 20]))
    d = float(depth + rng.choice([-10, 0, 10]))
    h = float(height + rng.choice([-10, 0, 10, 20]))
    kit = {"type": "organizer", "w": w, "d": d, "h": h, "compartments": n}
    label = rng.choice(NAMES) if rng.random() < 0.25 else ""
    if label:
        kit["text"] = label
    noun_tr = rng.choice(["tutucu", "standı", "düzenleyici"])
    if en:
        prompt = f"{thing_en} {rng.choice(['holder', 'stand', 'caddy'])} for {n} {thing_en}s" + (f", '{label}' engraved on the front" if label else "")
        summary = f"{thing_en.capitalize()} holder with {n} compartments: a floor, four walls and {n - 1} slotted dividers."
    else:
        prompt = rng.choice([f"{thing_tr} {noun_tr}, {n} {thing_tr} için", f"{n} bölmeli {thing_tr} {noun_tr}"]) + (f", önünde '{label}' yazan" if label else "")
        summary = f"{n} bölmeli {thing_tr} {noun_tr}: taban, dört duvar ve dil-yuvayla takılan {n - 1} ara bölme."
    return prompt, [kit], summary


def pot_cover(rng: random.Random, en: bool) -> tuple[str, list[dict[str, Any]], str] | None:
    """An open box with drain holes in the floor."""
    s = float(rng.choice(range(90, 201, 10)))
    h = float(rng.choice(range(80, 181, 10)))
    d = float(rng.choice([6, 8, 10]))
    n = rng.choice([4, 5, 9])
    pts = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
    if n >= 5:
        pts.append((0.5, 0.5))
    if n == 9:
        pts += [(0.5, 0.25), (0.5, 0.75), (0.25, 0.5), (0.75, 0.5)]
    box = {"type": "box", "x": s, "y": s, "h": h, "lid": False,
           "bottom": {"holes": [{"x": _r(s * px), "y": _r(s * py), "d": d, "purpose": "drain"} for px, py in pts]}}
    size = _size(rng, (s, s, h)) if rng.random() < 0.7 else ""
    if en:
        prompt = ", ".join(p for p in (f"plant pot cover with {len(pts)} drain holes in the bottom", size) if p)
        summary = f"Open box with {len(pts)} drain holes of {d:g} mm in the floor."
    else:
        prompt = " ".join(p for p in (size, rng.choice(["saksı kılıfı", "saksılık", "saksı kutusu"]), f"altında {len(pts)} tahliye delikli") if p)
        summary = f"Üstü açık kutu; tabanda {d:g} mm çapında {len(pts)} tahliye deliği."
    return prompt, [box], summary


def robot_base(rng: random.Random, en: bool) -> tuple[str, list[dict[str, Any]], str] | None:
    """A robot base plate: two TT motors at the back, a caster at the front, a cable slot."""
    w = float(rng.choice(range(150, 221, 10)))
    h = float(rng.choice(range(100, 151, 10)))
    mx = float(rng.choice([25, 30, 35]))
    holes = []
    for y in (12.0, h - 12.0):
        holes += [{"x": mx, "y": y, "d": 3.2, "purpose": "mount"}, {"x": mx + 17.5, "y": y, "d": 3.2, "purpose": "mount"}]
    caster = w - 25
    holes += [{"x": caster, "y": _r(h / 2 + dy), "d": 3.2, "purpose": "mount"} for dy in (-12.5, 12.5)]
    slots = [{"x": _r(w / 2), "y": _r(h / 2), "w": 30.0, "h": 10.0, "purpose": "cable"}]
    battery = rng.random() < 0.5
    if battery:
        holes += [{"x": _r(w / 2 + dx), "y": _r(h / 2 + 30), "d": 3.2, "purpose": "mount"} for dx in (-20, 20)]
    plate = {"type": "panel", "w": w, "h": h, "edges": "eeee", "holes": holes, "slots": slots}
    size = f"{w:g}x{h:g} mm" if rng.random() < 0.5 else ""
    if en:
        prompt = ", ".join(p for p in (f"robot chassis plate for 2 TT motors and a caster{' and a battery holder' if battery else ''}", size) if p)
        summary = "Base plate: screw holes for two TT motors and a caster, a cable slot" + (" and battery holder holes." if battery else ".")
    else:
        prompt = ", ".join(p for p in (f"robot şasisi, 2 TT motor ve sarhoş teker için{', pil yatağı delikli' if battery else ''}", size) if p)
        summary = "Taban plakası: iki TT motor ve sarhoş teker için vida delikleri, kablo yuvası" + (" ve pil yatağı delikleri." if battery else ".")
    return prompt, [plate], summary


def board_base(rng: random.Random, en: bool) -> tuple[str, list[dict[str, Any]], str] | None:
    """A base plate for a breadboard or an Arduino Uno, with corner screw holes and an optional name."""
    kind = rng.choice(["half", "full", "uno"])
    bw, bh, noun_tr, noun_en = {"half": (83, 55, "yarım breadboard", "half breadboard"), "full": (165, 55, "breadboard", "full breadboard"),
                                "uno": (69, 54, "Arduino Uno", "Arduino Uno")}[kind]
    m = float(rng.choice([10, 15, 20]))
    w, h = float(bw + 2 * m), float(bh + 2 * m + rng.choice([0, 20]))
    holes = [{"x": x, "y": y, "d": 3.2, "purpose": "mount"} for x in (6.0, w - 6.0) for y in (6.0, h - 6.0)]
    plate: dict[str, Any] = {"type": "panel", "w": w, "h": h, "edges": "eeee", "holes": holes}
    label = rng.choice(NAMES) if (h - bh - 2 * m) >= 20 and rng.random() < 0.7 else ""
    if label:
        plate["markings"] = [{"kind": "text", "value": label, "x": _r(w / 2), "y": _r(h - 12), "height": 8, "align": "center", "operation": "engrave"}]
    if en:
        prompt = f"{noun_en} base plate with 4 screw holes" + (f", '{label}' engraved" if label else "")
        summary = f"Flat base {w:g}x{h:g} mm with 4 corner screw holes" + (" and the name engraved." if label else ".")
    else:
        prompt = f"{noun_tr} tutucu taban, 4 vida delikli" + (f", '{label}' yazan" if label else "")
        summary = f"{w:g}x{h:g} mm düz taban, köşelerde 4 vida deliği" + (" ve kazınmış isim." if label else ".")
    return prompt, [plate], summary


FAMILIES = (enclosure, enclosure, card_holder, holder, holder, pot_cover, robot_base, board_base)


def make(rng: random.Random) -> tuple[str, dict[str, Any]] | None:
    t = rng.choice([3.0, 3.0, 3.0, 4.0])
    en = rng.random() < 0.25
    made = rng.choice(FAMILIES)(rng, en)
    if not made:
        return None
    prompt, primitives, summary = made
    prompt = " ".join(prompt.split())
    plan = {"primitives": primitives, "parameters": {"thickness": t, "project": prompt[:48], "what_you_see": prompt}, "summary": summary}
    return prompt, plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--count", type=int, default=240)
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    os.environ.setdefault("MCP_DATA_DIR", tempfile.mkdtemp(prefix="lasermcp-synth-weak-"))
    import train
    from ai_eval import load_prompts
    from synth_multipart import check

    benchmark = {str(r["prompt"]).casefold() for r in load_prompts()}
    rng = random.Random(args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    kept = tries = 0
    drops: dict[str, int] = {}
    with out.open("w", encoding="utf-8") as fh:
        while kept < args.count and tries < args.count * 4:
            tries += 1
            made = make(rng)
            if not made or made[0] in seen or made[0].casefold() in benchmark:
                continue
            prompt, plan = made
            seen.add(prompt)
            thickness = float(plan["parameters"]["thickness"])
            problems = check(prompt, json.loads(json.dumps(plan)), thickness)
            if problems:
                drops[problems[0][:70]] = drops.get(problems[0][:70], 0) + 1
                continue
            kept += 1
            row = {"prompt_id": f"weak-{kept:05d}", "prompt": prompt, "thickness": thickness, "teacher": "synthetic-weak",
                   "kind": "draft", "user": train.user_text(train.studio_request(prompt), thickness),
                   "assistant": train.answer_json(plan), "parts": len(plan["primitives"])}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if kept % 25 == 0:
                print(f"kept {kept} of {tries}", flush=True)
    print(f"kept {kept} of {tries} -> {out}")
    for why, n in sorted(drops.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {n:4d}  {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
