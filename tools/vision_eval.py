"""Image benchmark: show a model one picture, compile what it plans, score the result.

The text benchmark (ai_eval.py) cannot tell whether a model can turn a PICTURE into a
design. This one can. Each row of tools/vision_eval/images.json names an image and what a
faithful design of it must hold; the model sees only the image.

  .venv/Scripts/python.exe tools/vision_eval.py --check                     validate the set, no model
  .venv/Scripts/python.exe tools/vision_eval.py --model local:<vision model>  free: a model on this machine

Adding an image: put the file in tools/vision_eval/images/ and add a row:
  {"id": "photo-01", "file": "photo-01.jpg", "kind": "photo", "about": "3 raflı ahşap kitaplık",
   "min_panels": 6, "max_panels": 9, "types": ["shelf_unit"], "size_mm": [300, 150, 400], "text": ""}
kind: photo (a real object), product (a shop or catalogue picture), sketch (hand drawing),
cut_sheet (flat cutting layout), render (computer drawing). `types`, `size_mm` and `text`
are optional: leave out what the picture does not show.

What a score means: "passed" is the software gate plus the expectations of the row. It
never says a design is good or fits physically; look at a sample by eye.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
SET_DIR = Path(__file__).with_name("vision_eval")
MANIFEST = SET_DIR / "images.json"
KINDS = ("photo", "product", "sketch", "cut_sheet", "render")
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_BYTES = 4_000_000

ASK = (
    "Look at the picture. Plan how to build this object from flat laser-cut sheet material, "
    "then answer with the design JSON only. Estimate sizes from the picture when none are written on it."
)


def load_rows(path: Path = MANIFEST) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["images"] if isinstance(data, dict) else data


def check_rows(rows: list[dict[str, Any]], image_dir: Path) -> list[str]:
    """Everything wrong with the set itself, so a bad row never looks like a bad model."""
    problems: list[str] = []
    seen: set[str] = set()
    for i, row in enumerate(rows, 1):
        name = str(row.get("id") or f"row {i}")
        if not row.get("id") or name in seen:
            problems.append(f"{name}: id is missing or repeated")
        seen.add(name)
        if row.get("kind") not in KINDS:
            problems.append(f"{name}: kind must be one of {', '.join(KINDS)}")
        if not str(row.get("about") or "").strip():
            problems.append(f"{name}: about (what the picture shows) is empty")
        file = image_dir / str(row.get("file") or "")
        if not row.get("file") or not file.is_file():
            problems.append(f"{name}: image file {row.get('file')!r} not found in {image_dir}")
        elif file.suffix.lower() not in MEDIA:
            problems.append(f"{name}: {file.suffix} is not jpg, png or webp")
        elif file.stat().st_size > MAX_BYTES:
            problems.append(f"{name}: image is over {MAX_BYTES // 1_000_000} MB; shrink it")
        low, high = row.get("min_panels"), row.get("max_panels")
        if not isinstance(low, int) or not isinstance(high, int) or low < 1 or high < low:
            problems.append(f"{name}: min_panels and max_panels must be whole numbers, 1 <= min <= max")
        size = row.get("size_mm")
        if size is not None and not (isinstance(size, list) and len(size) == 3 and all(isinstance(v, (int, float)) and v > 0 for v in size)):
            problems.append(f"{name}: size_mm must be [width, depth, height] in mm")
    return problems


def design_types(primitives: list[Any]) -> set[str]:
    return {str(p.get("type") or "").lower() for p in primitives if isinstance(p, dict)}


def score(row: dict[str, Any], plan: dict[str, Any] | None, gate_ok: bool, panels: int, error: str = "") -> dict[str, Any]:
    """One image's verdict. Pure: no I/O, no model."""
    primitives = (plan or {}).get("primitives") or []
    problems: list[str] = []
    if error:
        problems.append("error:" + error[:80])
    elif not gate_ok:
        problems.append("blocked")
    if gate_ok:
        if panels < int(row["min_panels"]):
            problems.append(f"parts:{panels}<{row['min_panels']}")
        if panels > int(row["max_panels"]):
            problems.append(f"parts:{panels}>{row['max_panels']}")
        want = {str(t).lower() for t in row.get("types") or []}
        if want and not (want & design_types(primitives)):
            problems.append("type:" + ",".join(sorted(design_types(primitives))))
        if row.get("size_mm"):
            import train

            sizes = train._design_sizes(primitives)
            # Within a quarter of the true size: a picture carries proportions, not millimetres.
            near = sum(any(abs(s - v) <= 0.25 * v for s in sizes) for v in row["size_mm"])
            if near < 2:
                problems.append("size")
        text = str(row.get("text") or "").strip()
        if text and text.casefold() not in json.dumps(primitives, ensure_ascii=False).casefold():
            problems.append("text")
    return {"id": row.get("id"), "kind": row.get("kind"), "about": row.get("about"), "gate_ok": gate_ok,
            "passed": not problems, "panels": panels, "problems": problems,
            "types": sorted(design_types(primitives))}


def ask_model(model: str, image: Path, thickness: float) -> dict[str, Any]:
    """The model's design JSON for one picture, through its OpenAI-compatible endpoint."""
    import urllib.request

    from llm_client import _extract_json, tuned_system_prompt
    from llm_keys import get_raw_key, own_endpoint

    base = own_endpoint(model)
    if not base:
        raise SystemExit(f"{model}: only local:<name> vision models are supported (free). Paid vision is not part of this plan.")
    name = model.split(":", 1)[1] if model.lower().startswith("local:") else os.environ.get("LASERMCP_TUNED_MODEL", "")
    data = base64.b64encode(image.read_bytes()).decode("ascii")
    body = {
        "model": name,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": tuned_system_prompt()},
            {"role": "user", "content": [
                {"type": "text", "text": f"{ASK}\nMaterial thickness_mm={thickness:g}"},
                {"type": "image_url", "image_url": {"url": f"data:{MEDIA[image.suffix.lower()]};base64,{data}"}},
            ]},
        ],
    }
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode("utf-8"),
                                 {"content-type": "application/json", "authorization": f"Bearer {get_raw_key('local')}"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        content = json.load(resp)["choices"][0]["message"]["content"]
    return _extract_json(content)


def run(model: str, rows: list[dict[str, Any]], image_dir: Path, thickness: float = 3.0) -> list[dict[str, Any]]:
    import workshop

    out = []
    for i, row in enumerate(rows, 1):
        started = time.time()
        plan, gate_ok, panels, error = None, False, 0, ""
        try:
            plan = ask_model(model, image_dir / row["file"], thickness)
            drafts = workshop._PaidDrafts(thickness=thickness, parameters={"project": str(row["about"])[:48], "what_you_see": str(row["about"]), "thickness": thickness}, base="")
            result = drafts.design(plan)
            gate_ok = not workshop._draft_blocked(result)
            panels = len((result.get("assembly_result") or {}).get("parts") or [])
        except SystemExit:
            raise
        except Exception as exc:  # one bad picture must not lose the run
            error = str(exc)
        verdict = score(row, plan, gate_ok, panels, error)
        verdict["seconds"] = round(time.time() - started, 1)
        out.append(verdict)
        print(f"[{i:02d}/{len(rows)}] {'ok ' if verdict['passed'] else 'BAD'} {verdict['id']:<14} {row['kind']:<9} {','.join(verdict['problems'])}", flush=True)
    return out


# What a kit's parts are called once it is built; the reply carries panels, not primitives.
TYPE_LABELS = {"shelf_unit": ("shelf",), "organizer": ("divider",), "bench": ("leg",)}


def score_reply(row: dict[str, Any], reply: dict[str, Any], error: str = "") -> dict[str, Any]:
    """One image's verdict for the Studio route (look, then plan). Pure: no I/O, no model.

    The reply is what create_studio_ai returns. Sizes and text are judged on what the vision
    model read from the picture (that is the part this route adds); parts and kind of object
    on what was built.
    """
    seen = reply.get("look") if isinstance(reply.get("look"), dict) else {}
    gate_ok = bool(reply.get("success")) and str(reply.get("final_status") or "BLOCKED") not in {"BLOCKED", "FAIL"}
    labels = [str(p.get("label") or p.get("part_id") or "").lower() for p in ((reply.get("assembly") or {}).get("panels") or [])]
    # A flat design (a plate, a sign) has no 3D assembly, yet a design that passed has a part.
    panels = len(labels) or (1 if gate_ok else 0)
    problems: list[str] = []
    if error:
        problems.append("error:" + error[:80])
    elif not seen:
        problems.append("traced")      # the picture went to the tracer, not to the model
    elif not gate_ok:
        problems.append("blocked")
    if gate_ok and seen:
        if panels < int(row["min_panels"]):
            problems.append(f"parts:{panels}<{row['min_panels']}")
        if panels > int(row["max_panels"]):
            problems.append(f"parts:{panels}>{row['max_panels']}")
        want = [t for t in row.get("types") or [] if t in TYPE_LABELS]
        if want and not any(hint in label for t in want for hint in TYPE_LABELS[t] for label in labels):
            problems.append("type")
    request = str(seen.get("request") or "")
    if seen and row.get("size_mm"):
        found = [float(n) for n in re.findall(r"\d+(?:[.,]\d+)?", request.replace(",", "."))]
        near = sum(any(abs(s - v) <= 0.1 * v for s in found) for v in row["size_mm"])
        if near < 3:
            problems.append("size")
    text = str(row.get("text") or "").strip()
    if seen and text and text.casefold() not in request.casefold():
        problems.append("text")
    return {"id": row.get("id"), "kind": row.get("kind"), "about": row.get("about"), "gate_ok": gate_ok,
            "passed": not problems, "panels": panels, "problems": problems,
            "saw": seen.get("what"), "request": request, "look_seconds": seen.get("seconds")}


def run_studio(rows: list[dict[str, Any]], image_dir: Path, thickness: float = 3.0) -> list[dict[str, Any]]:
    """Every picture through the same function the Studio calls, with the tuned model chosen."""
    import workshop

    out = []
    for i, row in enumerate(rows, 1):
        file = image_dir / row["file"]
        data = base64.b64encode(file.read_bytes()).decode("ascii")
        body = {"image_base64": f"data:{MEDIA[file.suffix.lower()]};base64,{data}", "file_kind": "photo",
                "prompt": "", "messages": [], "thickness": thickness, "model": "lasermcp-tuned"}
        started = time.time()
        reply, error = {}, ""
        try:
            reply = workshop.create_studio_ai(body, client_ip=f"vision-{i}")
        except Exception as exc:  # one bad picture must not lose the run
            error = str(exc)
        verdict = score_reply(row, reply, error)
        verdict["seconds"] = round(time.time() - started, 1)
        out.append(verdict)
        print(f"[{i:02d}/{len(rows)}] {'ok ' if verdict['passed'] else 'BAD'} {verdict['id']:<20} {row['kind']:<9} "
              f"{verdict['panels']:>2}p {verdict['seconds']:>5}s {','.join(verdict['problems'])}  <- {verdict['request'][:90]}", flush=True)
    return out


def use_local_models(vision: str) -> None:
    """Point the Studio at this machine's Ollama: tuned model plans, `vision` looks. No sign-in."""
    os.environ["LASERMCP_TUNED_MODEL"] = os.environ.get("LASERMCP_TUNED_MODEL_NAME", "lasermcp")
    os.environ["LASERMCP_TUNED_BASE_URL"] = "http://127.0.0.1:11434/v1"
    os.environ["LASERMCP_VISION_MODEL"] = vision
    os.environ.pop("LASERMCP_VISION_BASE_URL", None)
    os.environ.pop("LASERMCP_LOCAL_API_KEY", None)
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "MCP_AUTH_TOKEN"):
        os.environ[key] = ""


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def block(items: list[dict[str, Any]]) -> dict[str, int]:
        return {"n": len(items), "passed": sum(r["passed"] for r in items), "gate_ok": sum(r["gate_ok"] for r in items)}

    kinds = sorted({r["kind"] for r in results})
    return {"all": block(results), "by_kind": {k: block([r for r in results if r["kind"] == k]) for k in kinds}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="", help="local:<vision model in Ollama>, or 'studio' for the look-then-plan route")
    ap.add_argument("--vision", default="qwen3-vl:4b-instruct", help="with --model studio: the Ollama vision model that looks")
    ap.add_argument("--check", action="store_true", help="validate the image set and stop")
    ap.add_argument("--only", default="", help="comma list of kinds")
    ap.add_argument("--set", default=str(MANIFEST), help="manifest path")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    manifest = Path(args.set)
    image_dir = manifest.parent / "images"
    rows = load_rows(manifest)
    problems = check_rows(rows, image_dir)
    counts = {k: sum(1 for r in rows if r.get("kind") == k) for k in KINDS}
    print(f"{len(rows)} images: " + ", ".join(f"{k} {n}" for k, n in counts.items()))
    for line in problems:
        print("  problem:", line)
    if problems:
        return 1
    if args.check or not args.model:
        if not args.model:
            print("the set is valid. Pass --model local:<vision model> to score a model.")
        return 0
    if args.only:
        keep = {k.strip() for k in args.only.split(",") if k.strip()}
        rows = [r for r in rows if r["kind"] in keep]
    os.environ["MCP_DATA_DIR"] = tempfile.mkdtemp(prefix="lasermcp-vision-")
    model = args.model.strip()
    if model == "studio":
        use_local_models(args.vision)
        model = f"studio-{args.vision}"
        results = run_studio(rows, image_dir)
    else:
        results = run(model, rows, image_dir)
    summary = summarize(results)
    out = Path(args.out) if args.out else ROOT / "output" / "vision_eval" / f"{model.replace(':', '-')}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": model, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{'kind':<10} {'n':>3} {'passed':>7} {'gate':>5}")
    for name, b in [*summary["by_kind"].items(), ("ALL", summary["all"])]:
        print(f"{name:<10} {b['n']:>3} {b['passed']:>7} {b['gate_ok']:>5}")
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
