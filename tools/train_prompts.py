"""Training requests for the tuned Studio AI model: many varied, realistic prompts.

Deterministic for a seed, so a collection run can be resumed. Never returns a prompt
from the benchmark (tools/ai_eval_prompts.json) — training on the test would make its
score meaningless — nor one a free recipe or the plain box engine already answers.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (Turkish name, English name, typical W×D×H mm, features that make sense for it)
_OBJECTS: list[tuple[str, str, tuple[int, int, int], tuple[str, ...]]] = [
    ("telefon standı", "phone stand", (80, 90, 110), ("cable", "angle", "text")),
    ("tablet standı", "tablet stand", (180, 120, 150), ("cable", "angle")),
    ("kalemlik", "pen holder", (90, 90, 100), ("compartments", "text", "pattern")),
    ("masaüstü düzenleyici", "desk organizer", (240, 140, 100), ("compartments", "drawer", "text")),
    ("kartvizitlik", "business card holder", (100, 50, 45), ("text",)),
    ("peçetelik", "napkin holder", (140, 50, 100), ("pattern", "text")),
    ("kitap desteği", "bookend", (120, 100, 160), ("pattern", "text")),
    ("baharat rafı", "spice rack", (300, 70, 220), ("shelves", "wall")),
    ("duvar rafı", "wall shelf", (400, 120, 150), ("wall", "shelves")),
    ("ayakkabılık rafı", "shoe shelf", (500, 250, 300), ("shelves",)),
    ("anahtar askılığı", "key rack", (220, 30, 80), ("wall", "hooks", "text")),
    ("kulaklık standı", "headphone stand", (120, 100, 240), ("cable",)),
    ("laptop standı", "laptop stand", (260, 220, 90), ("angle", "vents")),
    ("monitör yükseltici", "monitor riser", (450, 200, 90), ("drawer", "compartments")),
    ("çekmeceli kutu", "box with a drawer", (200, 150, 80), ("drawer", "handle")),
    ("bölmeli kutu", "box with dividers", (240, 160, 50), ("compartments", "lid")),
    ("takı kutusu", "jewelry box", (160, 110, 60), ("compartments", "lid", "text")),
    ("çay kutusu", "tea box", (220, 150, 80), ("compartments", "lid", "text")),
    ("vida kutusu", "screw organizer", (260, 180, 40), ("compartments", "lid")),
    ("alet tepsisi", "tool tray", (300, 140, 60), ("compartments", "handle")),
    ("saplı taşıma kasası", "carry caddy with a handle", (320, 160, 200), ("handle", "compartments")),
    ("dosya tepsisi", "paper tray", (320, 240, 60), ("stack",)),
    ("dergilik", "magazine file", (90, 250, 300), ("pattern", "text")),
    ("saksı kılıfı", "planter cover", (130, 130, 120), ("drain", "pattern")),
    ("mumluk", "candle holder", (90, 90, 100), ("pattern", "windows")),
    ("gece lambası kutusu", "night light box", (120, 120, 160), ("pattern", "windows", "cable")),
    ("masa lambası gövdesi", "lamp body", (130, 130, 220), ("pattern", "cable")),
    ("fotoğraf çerçevesi", "photo frame", (170, 20, 220), ("stand", "text")),
    ("kapı isimliği", "door sign", (220, 3, 70), ("holes", "text")),
    ("duvar saati kadranı", "wall clock face", (260, 3, 260), ("numbers", "holes")),
    ("bardak altlığı seti ve tutucusu", "coaster set with holder", (110, 110, 50), ("pattern", "text")),
    ("uzaktan kumanda standı", "remote control stand", (180, 90, 110), ("compartments",)),
    ("şarj istasyonu", "charging station", (220, 120, 120), ("cable", "compartments")),
    ("oyun kartı kutusu", "playing card box", (100, 70, 30), ("lid", "text")),
    ("zar kulesi", "dice tower", (90, 90, 180), ("pattern",)),
    ("kumbara", "coin bank", (110, 110, 120), ("slot", "text")),
    ("kedi evi", "cat house", (350, 350, 350), ("door", "windows")),
    ("oyuncak araba", "toy car", (140, 70, 60), ("wheels",)),
    ("oyuncak kamyon", "toy truck", (200, 80, 90), ("wheels",)),
    ("bebek evi mobilyası masa", "dollhouse table", (80, 50, 40), ()),
    ("bebek evi sandalyesi", "dollhouse chair", (40, 40, 80), ()),
    ("minyatür kitaplık", "miniature bookshelf", (120, 40, 160), ("shelves",)),
    ("Arduino Uno kutusu", "Arduino Uno enclosure", (80, 60, 30), ("ports", "vents", "lid")),
    ("Raspberry Pi kasası", "Raspberry Pi case", (95, 65, 35), ("ports", "vents", "lid")),
    ("ESP32 kutusu", "ESP32 enclosure", (70, 40, 25), ("ports", "lid")),
    ("devre kutusu", "electronics project box", (120, 80, 45), ("ports", "vents", "lid", "holes")),
    ("LCD ekranlı kontrol kutusu", "control box with an LCD window", (120, 90, 50), ("windows", "holes", "lid")),
    ("servo braketi", "servo bracket", (50, 30, 40), ("holes",)),
    ("motor tutucu", "motor mount", (60, 40, 40), ("holes",)),
    ("robot şasisi", "robot chassis", (160, 120, 3), ("holes", "wheels")),
    ("breadboard tabanı", "breadboard base plate", (190, 80, 3), ("holes",)),
    ("güneş paneli standı", "solar panel stand", (120, 80, 90), ("angle",)),
    ("pil yuvası kutusu", "battery holder box", (70, 60, 25), ("lid", "holes")),
    ("hoparlör kutusu", "speaker box", (120, 100, 160), ("holes", "ports")),
    ("sensör kulesi", "sensor tower", (60, 60, 150), ("holes", "windows")),
    ("su roketi fırlatma rampası", "launch ramp", (200, 120, 150), ("angle",)),
    ("basit terazi", "simple balance scale", (240, 80, 180), ("holes",)),
    ("köprü maketi", "bridge model", (400, 80, 100), ()),
    ("rüzgar gülü standı", "pinwheel stand", (90, 90, 220), ("holes",)),
    ("periskop gövdesi", "periscope body", (60, 60, 300), ("windows",)),
]

_FEATURES: dict[str, tuple[list[str], list[str]]] = {
    "cable": (["kablo geçişli", "arkasında kablo deliği olan"], ["with a cable slot", "with a cable hole at the back"]),
    "angle": (["{a} derece eğimli"], ["tilted {a} degrees"]),
    "text": (["üzerinde '{t}' yazan", "ön yüzünde '{t}' kazınmış"], ["engraved with '{t}'", "with '{t}' on the front"]),
    "compartments": (["{n} bölmeli"], ["with {n} compartments"]),
    "drawer": (["çekmeceli", "{d} çekmeceli"], ["with a drawer", "with {d} drawers"]),
    "pattern": (["yanları desenli", "ızgara desenli"], ["with patterned sides", "with a grid cutout pattern"]),
    "shelves": (["{n} katlı", "{n} raflı"], ["with {n} shelves", "{n} tiers"]),
    "wall": (["duvara asılan", "iki vida delikli, duvara monte"], ["wall mounted", "with two screw holes for the wall"]),
    "hooks": (["{n} kancalı"], ["with {n} hooks"]),
    "vents": (["havalandırma delikli"], ["with ventilation slots"]),
    "handle": (["saplı", "tutma yeri olan"], ["with a handle", "with a finger pull"]),
    "lid": (["kapaklı", "sürgülü kapaklı", "çıkarılabilir kapaklı"], ["with a lid", "with a sliding lid", "with a removable lid"]),
    "stack": (["üst üste konabilen", "{d} katlı"], ["stackable", "{d} tiers"]),
    "drain": (["altı delikli", "su tahliye delikli"], ["with drainage holes"]),
    "windows": (["pencereli", "ön yüzünde pencere olan"], ["with windows", "with a front window"]),
    "stand": (["ayaklı", "arkadan destekli"], ["with a stand", "with a back support"]),
    "holes": (["vida delikli", "M3 vida delikleri olan"], ["with screw holes", "with M3 mounting holes"]),
    "numbers": (["rakamları kazınmış"], ["with engraved numbers"]),
    "slot": (["üstünde para yuvası olan"], ["with a coin slot on top"]),
    "door": (["kapı girişli", "yuvarlak girişli"], ["with a door opening", "with a round entrance"]),
    "wheels": (["4 tekerlekli", "dönen tekerlekli"], ["with 4 wheels", "with turning wheels"]),
    "ports": (["USB ve güç girişi açık", "yanında USB-C girişi olan"], ["with USB and power cutouts", "with a USB-C port on the side"]),
}
_TEXTS = ["Atölye", "Mutfak", "Ofis", "STEM", "Ada", "Kerem", "Zeynep", "Lab", "Notlar", "Hoş geldin", "Robot", "Maker"]
_MATERIAL = (["3 mm kontrplaktan", "3 mm MDF", "4 mm kavak kontrplak"], ["from 3 mm plywood", "in 3 mm MDF", "4 mm poplar plywood"])
_OPENERS = (["", "", "", "bana bir ", "bir ", "küçük ", "büyük ", "çocuklar için ", "masaüstü "], ["", "", "", "a ", "small ", "large ", "desktop ", "kid-friendly "])
_ASKS = (["", "", "", " tasarla", " çiz", " yap", " istiyorum", " lazım"], ["", "", "", ", please", " design", " I need one"])


def _size(rng: random.Random, base: tuple[int, int, int], english: bool) -> str:
    w, d, h = (max(3, int(round(v * rng.uniform(0.7, 1.4) / 5.0)) * 5) if v > 3 else v for v in base)
    style = rng.randrange(6)
    if style == 0:
        return f"{w}x{d}x{h} mm"
    if style == 1:
        return f"{w / 10:g}x{d / 10:g}x{h / 10:g} cm"
    if style == 2:
        return (f"{w} mm wide" if english else f"{w} mm genişlik")
    if style == 3:
        return (f"{h} mm tall" if english else f"{h} mm yükseklik")
    return ""


def _feature(rng: random.Random, name: str, english: bool) -> str:
    text = rng.choice(_FEATURES[name][1 if english else 0])
    return text.format(a=rng.choice([15, 20, 30, 45, 60]), t=rng.choice(_TEXTS), n=rng.choice([2, 3, 4, 5, 6]), d=rng.choice([2, 3]))


def _one(rng: random.Random) -> str:
    tr, en, base, features = rng.choice(_OBJECTS)
    english = rng.random() < 0.3
    lang = 1 if english else 0
    picked = rng.sample(features, k=min(len(features), rng.choice([0, 1, 1, 2]))) if features else []
    words = [_feature(rng, f, english) for f in picked]
    size = _size(rng, base, english)
    material = rng.choice(_MATERIAL[lang]) if rng.random() < 0.15 else ""
    name = en if english else tr
    if english:
        body = " ".join(x for x in [name, *words] if x)
        tail = ", ".join(x for x in [size, material] if x)
        text = rng.choice(_OPENERS[1]) + body + (", " + tail if tail else "") + rng.choice(_ASKS[1])
    else:
        lead = ", ".join(words)
        body = " ".join(x for x in [size, material, lead, name] if x)
        text = rng.choice(_OPENERS[0]) + body + rng.choice(_ASKS[0])
    return " ".join(text.split()).strip(" ,")


def _benchmark() -> set[str]:
    import json

    from ai_cache import _normalize

    path = Path(__file__).with_name("ai_eval_prompts.json")
    rows = json.loads(path.read_text(encoding="utf-8")).get("prompts") or []
    return {_normalize(str(r.get("prompt") or "")) for r in rows}


def make_prompts(count: int, seed: int = 1) -> list[dict[str, Any]]:
    """`count` distinct requests that only a model can answer, in a stable order."""
    from ai_cache import _normalize, match_maker, simple_box_request

    rng = random.Random(seed)
    held_out = _benchmark()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    tries = 0
    while len(out) < count and tries < count * 40:
        tries += 1
        prompt = _one(rng)
        key = _normalize(prompt)
        if key in seen or key in held_out or match_maker(prompt) or simple_box_request(prompt):
            continue
        seen.add(key)
        out.append({"id": f"t{seed}-{len(out) + 1:05d}", "prompt": prompt, "thickness": 4.0 if "4 mm" in prompt else 3.0})
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    for row in make_prompts(n):
        sys.stdout.buffer.write((row["prompt"] + "\n").encode("utf-8"))
