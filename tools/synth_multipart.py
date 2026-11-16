"""Gate-checked multi-part training examples, generated from parametric families.

The teacher models never drew a multi-part object that passed the gate (shelves, benches,
organizers with dividers): in 1927 requests every kept draft was one box or one flat panel.
The grammar can express them — explicitly placed panels, `parameters.connections` finger
joints between touching edges, and tab-slot joints for shelves and dividers that meet a
panel in the middle — but a small model gets the panel coordinates wrong. So the designs here use the
kit primitives of panel_kits.py (shelf_unit, bench, organizer): the model picks the object,
the sizes and the counts, the compiler places and joins the panels. Each design runs
through the same gate and faithfulness filter as `train.py collect`; only passing ones are
kept. The rows land in output/train/synthetic.jsonl; `train.py build` reads them
next to examples.jsonl.

  .venv/Scripts/python.exe tools/synth_multipart.py --count 300
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "output" / "train" / "synthetic.jsonl"
NAMES = ["STEM", "Atölye", "Ada", "Kerem", "Zeynep", "Maker", "Lab", "Notlar", "Ofis", "Robot"]
MATERIALS = {3.0: ["", "3 mm kontrplaktan ", "3 mm MDF ", "from 3 mm plywood "], 4.0: ["4 mm kavak kontrplak ", "4 mm poplar plywood "]}


from panel_kits import expand_kits  # noqa: E402


# --- requests -----------------------------------------------------------------------------------

def size_phrase(rng: random.Random, W: float, D: float, H: float, en: bool) -> str:
    cm = rng.random() < 0.4
    fmt = (lambda v: f"{v / 10:g}") if cm else (lambda v: f"{v:g}")
    unit = "cm" if cm else "mm"
    return f"{fmt(W)}x{fmt(D)}x{fmt(H)} {unit}"


def make(rng: random.Random) -> tuple[str, dict[str, Any]] | None:
    t = rng.choice([3.0, 3.0, 3.0, 4.0])
    en = rng.random() < 0.3
    material = rng.choice([m for m in MATERIALS[t] if not m or (("from" in m or "poplar" in m) == en)])
    family = rng.choice(["bookshelf", "bookshelf", "wall_shelf", "cubby", "bench", "riser", "doll_table", "organizer", "organizer", "pen_organizer"])
    name = rng.choice(NAMES) if rng.random() < 0.25 else ""
    sized = rng.random() < 0.65  # the rest state no size: the model must pick a sensible one
    kit: dict[str, Any] = {}

    def phrase(noun: str, detail_tr: str = "", detail_en: str = "") -> str:
        size = size_phrase(rng, kit["w"], kit["d"], kit["h"], en) if sized else ""
        if en:
            return ", ".join(x for x in (f"{noun}{detail_en}", size, material.strip()) if x)
        return " ".join(x for x in (size, material.strip(), f"{detail_tr}{noun}") if x)

    if family in ("bookshelf", "cubby"):
        W, D, H = rng.choice(range(200, 501, 10)), rng.choice(range(100, 251, 10)), rng.choice(range(250, 701, 10))
        if family == "cubby":
            H = rng.choice(range(150, 301, 10))
        levels = rng.randint(2, 5) if family == "bookshelf" else 1
        kit.update({"type": "shelf_unit", "w": W, "d": D, "h": H, "shelves": levels})
        if family == "bookshelf":
            noun_tr, noun_en = rng.choice([("kitaplık", "bookshelf"), ("raf ünitesi", "shelf unit"), ("ayakkabılık", "shoe rack"), ("masaüstü kitaplık", "desktop bookshelf")])
            prompt = phrase(noun_en if en else noun_tr, f"{levels} raflı ", f" with {levels} shelves")
            summary = f"{levels}-shelf {noun_en}; the middle shelves sit in tab slots." if en else f"{levels} raflı {noun_tr}: yan paneller, taban, üst, arka ve dil-yuvayla takılan ara raflar."
        else:
            prompt = phrase("open front cubby" if en else "önü açık dolap gözü")
            summary = "Open-front cubby: bottom, top, two sides and a back." if en else "Önü açık dolap gözü: taban, üst, iki yan ve arka panel."
    elif family == "wall_shelf":
        W, D, H = rng.choice(range(200, 601, 10)), rng.choice(range(80, 201, 10)), rng.choice(range(120, 301, 10))
        kit.update({"type": "shelf_unit", "w": W, "d": D, "h": H, "shelves": 1, "top": False, "wall_holes": True})
        prompt = phrase("wall shelf with two screw holes for the wall" if en else "duvara monte, vida delikli duvar rafı")
        summary = "Wall shelf: back with two screw holes, a bottom and two sides." if en else "Duvar rafı: arka panel (2 vida deliği), taban ve iki yan panel."
    elif family in ("bench", "riser", "doll_table"):
        if family == "bench":
            W, D, H = rng.choice(range(250, 601, 10)), rng.choice(range(100, 251, 10)), rng.choice(range(120, 351, 10))
            noun_tr, noun_en = rng.choice([("sehpa", "side table"), ("bank", "bench"), ("tabure", "low stool")])
        elif family == "riser":
            W, D, H = rng.choice(range(300, 601, 10)), rng.choice(range(150, 261, 10)), rng.choice(range(60, 141, 5))
            noun_tr, noun_en = rng.choice([("monitör yükseltici", "monitor riser"), ("laptop yükseltici", "laptop riser")])
        else:
            W, D, H = rng.choice(range(60, 151, 5)), rng.choice(range(40, 101, 5)), rng.choice(range(40, 91, 5))
            noun_tr, noun_en = "bebek evi masası", "doll house table"
        back = rng.random() < 0.4
        kit.update({"type": "bench", "w": W, "d": D, "h": H, "back_brace": back})
        prompt = phrase(noun_en if en else noun_tr, "arka destekli " if back else "", " with a back brace" if back else "")
        summary = (f"{noun_en}: a top on two legs" + (" with a back brace." if back else ".")) if en else (f"{noun_tr}: üst tabla, iki ayak" + (" ve arka bağlantı paneli." if back else "."))
    else:
        if family == "pen_organizer":
            W, D, H = rng.choice(range(120, 241, 10)), rng.choice(range(60, 121, 10)), rng.choice(range(70, 121, 10))
            noun_tr, noun_en = "kalemlik", "pen holder"
        else:
            W, D, H = rng.choice(range(150, 401, 10)), rng.choice(range(100, 251, 10)), rng.choice(range(40, 121, 10))
            noun_tr, noun_en = rng.choice([("masaüstü düzenleyici", "desk organizer"), ("çekmece içi düzenleyici", "drawer organizer"), ("alet tepsisi", "tool tray")])
        cells = rng.randint(2, 5)
        if (W / cells) < 30 + t:
            return None
        kit.update({"type": "organizer", "w": W, "d": D, "h": H, "compartments": cells})
        prompt = phrase(noun_en if en else noun_tr, f"{cells} bölmeli ", f" with {cells} compartments")
        summary = f"{noun_en} with {cells} compartments: a floor, four walls and {cells - 1} slotted dividers." if en else f"{cells} bölmeli {noun_tr}: taban, dört duvar ve dil-yuvayla takılan {cells - 1} ara bölme."
    if name and family != "wall_shelf":
        kit["text"] = name
        where_en, where_tr = ("on the front", "önünde") if kit["type"] == "organizer" else ("on top", "üstünde")
        prompt += f" with '{name}' engraved {where_en}" if en else f", {where_tr} '{name}' yazan"
    prompt = " ".join(prompt.split())
    plan = {"primitives": [kit], "parameters": {"thickness": t, "project": prompt[:48], "what_you_see": prompt}, "summary": summary}
    return prompt, plan


def check(prompt: str, plan: dict[str, Any], thickness: float) -> list[str]:
    """The same gate and faithfulness filter `train.py collect` applies."""
    import workshop
    import train

    drafts = workshop._PaidDrafts(thickness=thickness, parameters={"project": prompt[:48], "what_you_see": prompt, "thickness": thickness}, base="")
    result = drafts.design(plan)
    if workshop._draft_blocked(result):
        return ["blocked: " + n for n in workshop._gate_issues(result)[:3]] or ["blocked"]
    return ["quality: " + p for p in train.quality_problems(prompt, plan["primitives"])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    os.environ.setdefault("MCP_DATA_DIR", tempfile.mkdtemp(prefix="lasermcp-synth-"))
    import train

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
            if not made or made[0] in seen:
                continue
            prompt, plan = made
            seen.add(prompt)
            thickness = float(plan["parameters"]["thickness"])
            problems = check(prompt, plan, thickness)
            if problems:
                drops[problems[0][:70]] = drops.get(problems[0][:70], 0) + 1
                continue
            kept += 1
            row = {"prompt_id": f"syn-{kept:05d}", "prompt": prompt, "thickness": thickness, "teacher": "synthetic",
                   "kind": "draft", "user": train.user_text(train.studio_request(prompt), thickness),
                   "assistant": train.answer_json(plan), "parts": len(expand_kits(plan["primitives"], plan["parameters"])[0])}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if kept % 25 == 0:
                print(f"kept {kept} of {tries}", flush=True)
    print(f"kept {kept} of {tries} -> {out}")
    for why, n in sorted(drops.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {n:4d}  {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
