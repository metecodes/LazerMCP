"""Landing wow: three stored kit images → real cut SVG. No uploads."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from boxes_adapter import ROOT

DEMO_DIR = ROOT / "web" / "demo"
NS = "{http://www.w3.org/2000/svg}"

KITS: list[dict[str, Any]] = [
    {
        "id": "house-pencil-holder", "tool": "get_standard_model",
        "title_tr": "Ev Kalemlik", "title_en": "House pencil holder",
        "blurb_tr": "130×90×180 mm · 2,7 mm · Noçsuz standart model",
        "blurb_en": "130×90×180 mm · 2.7 mm · No holding bridges",
        "src": "house-pencil-holder.assembled.svg", "cut": "house-pencil-holder.svg",
        "model_url": "/models/house-pencil-holder", "dxf_url": "/demo/house-pencil-holder.dxf",
    },
    {
        "id": "traffic_light",
        "tool": "create_traffic_light",
        "title_tr": "Trafik lambası",
        "title_en": "Traffic light",
        "blurb_tr": "3 şalter, 3 LED. Her şartel kendi lambasını yakar.",
        "blurb_en": "3 switches, 3 LEDs. Each switch lights its own lamp.",
        "src": "traffic_light.src.svg",
        "cut": "traffic_light.cut.svg",
    },
    {
        "id": "product_box",
        "tool": "create_product_box",
        "title_tr": "Ağzı açık kutu",
        "title_en": "Open finger-joint box",
        "blurb_tr": "Dört duvar + taban. Kapak yok. Parmak eklem, dış ölçü.",
        "blurb_en": "Four walls + floor. No lid. Finger joints, outside size.",
        "src": "product_box.src.svg",
        "cut": "product_box.cut.svg",
    },
    {
        "id": "robot_bank",
        "tool": "create_robot_bank",
        "title_tr": "Robot kumbara",
        "title_en": "Robot bank",
        "blurb_tr": "Para atılınca LED. Arka kapak vida ile açılır.",
        "blurb_en": "Coin in, LED on. Rear door opens with screws.",
        "src": "robot_bank.src.svg",
        "cut": "robot_bank.cut.svg",
    },
]


def list_kits() -> dict[str, Any]:
    return {
        "success": True,
        "kits": [
            {
                **{k: v for k, v in kit.items() if k not in {"src", "cut"}},
                "src_url": f"/demo/{kit['src']}",
                "svg_url": f"/demo/{kit['cut']}",
            }
            for kit in KITS
        ],
        "note": "Stored kits only. No upload.",
    }


def kit_by_id(kit_id: str) -> dict[str, Any] | None:
    for kit in KITS:
        if kit["id"] == kit_id:
            return kit
    return None


def demo_file(name: str) -> Path:
    path = (DEMO_DIR / Path(name).name).resolve()
    if not str(path).startswith(str(DEMO_DIR.resolve())):
        raise ValueError("invalid filename")
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def tight_cut_svg(svg_bytes: bytes) -> bytes:
    root = ET.fromstring(svg_bytes)
    xmin = ymin = None
    xmax = ymax = None
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "path":
            continue
        stroke = (el.get("stroke") or "").lower()
        if "255" in stroke or stroke in {"#ff0000", "red", "rgb(255,0,0)"}:
            el.set("stroke", "#E10600")
        elif stroke in {"#000", "#000000", "black", "rgb(0,0,0)"}:
            el.set("stroke", "#E10600")
        el.set("fill", "none")
        d = el.get("d") or ""
        nums = []
        buf = ""
        for ch in d.replace(",", " "):
            if ch in "0123456789.+-eE":
                buf += ch
            elif buf:
                try:
                    nums.append(float(buf))
                except ValueError:
                    pass
                buf = ""
        if buf:
            try:
                nums.append(float(buf))
            except ValueError:
                pass
        xs = nums[0::2]
        ys = nums[1::2]
        if not xs or not ys:
            continue
        xmin = min(xs) if xmin is None else min(xmin, min(xs))
        ymin = min(ys) if ymin is None else min(ymin, min(ys))
        xmax = max(xs) if xmax is None else max(xmax, max(xs))
        ymax = max(ys) if ymax is None else max(ymax, max(ys))
    if xmin is None:
        return svg_bytes
    pad = 8.0
    w = max(1.0, xmax - xmin + 2 * pad)
    h = max(1.0, ymax - ymin + 2 * pad)
    root.set("viewBox", f"{xmin - pad:.2f} {ymin - pad:.2f} {w:.2f} {h:.2f}")
    root.set("width", "100%")
    root.set("height", "100%")
    root.attrib.pop("xmlns:dc", None)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
