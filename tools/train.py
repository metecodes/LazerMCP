"""Train LaserMCP's own Studio AI model: a small open model tuned on gate-approved designs.

A "teacher" model drafts thousands of varied requests. The LaserMCP gate keeps only the
drafts it approves, so nobody labels data by hand. A small model is then fine-tuned on
those pairs and served as the Studio id "lasermcp-tuned". The whole plan, with setup, is
in docs/MODEL_TRAINING.md.

Free path (a model on this machine; nothing is billed), from the repository root:
  .venv/Scripts/python.exe tools/train.py collect --count 50          (teacher: local:lasermcp-teacher)
  .venv/Scripts/python.exe tools/train.py build
  -> fine-tune on Kaggle with tools/kaggle_finetune.py, install the result in Ollama
  .venv/Scripts/python.exe tools/ai_eval.py --model lasermcp-tuned

Paid path (a provider's model as teacher and fine-tuner): pass --teacher <provider model>
and --spend to collect, then `start --spend` and `status`. Those bill the OPENAI_API_KEY /
ANTHROPIC_API_KEY in your environment and refuse to run without --spend.

collect can be stopped and re-run: it resumes. Everything is written under output/train/
(not committed).

Limits to keep in mind: the gate checks joints and sizes, not whether a design is a good
phone stand — read a sample of examples.jsonl before training. A tuned model is only worth
serving if tools/ai_eval.py scores it above the model it started from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = ROOT / "output" / "train"
EXAMPLES = "examples.jsonl"
REJECTED = "rejected.jsonl"
ERRORS = "errors.jsonl"
REPORT = "report.txt"
# Base model to tune. Providers retire snapshots: if `start` reports an unknown model, pass
# the current fine-tunable small model with --base.
DEFAULT_BASE = "gpt-4o-mini-2024-07-18"
MIN_EXAMPLES = 10  # the provider's floor; a useful model needs a few hundred


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a line cut off by an interrupted run
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def answer_json(plan: dict[str, Any]) -> str:
    """The reply the tuned model must learn: exactly the JSON contract of the system prompt."""
    return json.dumps(
        {
            "primitives": plan.get("primitives") or [],
            "parameters": plan.get("parameters") if isinstance(plan.get("parameters"), dict) else {},
            "summary": str(plan.get("summary") or "")[:240],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def user_text(text: str, thickness: Any) -> str:
    """Same bytes as llm_client.plan_primitives_with_llm sends for this request."""
    from llm_client import request_text

    return request_text(text, thickness)


def studio_request(prompt: str) -> str:
    """How Studio phrases a first request to the model (the prompt plus its one-turn thread)."""
    from workshop import _compose_ai_chat_prompt

    return _compose_ai_chat_prompt(prompt, {"messages": [{"role": "user", "text": prompt}]})


# --- quality -----------------------------------------------------------------------------
# The gate proves a draft can be cut and joined. It does not prove the draft is what was
# asked for: a small model often answers any request with the example box from its own
# system prompt, and that passes the gate. Training on such rows teaches exactly that.

_EXAMPLE_TEXTS = ("Name", "PAYAS")
_SIZE_WORD = None  # compiled on first use


def _stated_sizes(prompt: str) -> tuple[list[float], list[float]]:
    """(the W x D x H triple in mm, single sizes such as "50 mm wide") typed in a request."""
    import re

    from ai_cache import _DIMS3
    from llm_client import _CM_SIZE

    global _SIZE_WORD
    if _SIZE_WORD is None:
        _SIZE_WORD = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*mm\s*(?:genişlik|yükseklik|wide|tall)", re.I)
    triple: list[float] = []
    hit = _DIMS3.search(prompt)
    if hit:
        scale = 10.0 if _CM_SIZE.search(prompt) else 1.0
        triple = [float(v.replace(",", ".")) * scale for v in hit.groups()]
    singles = [float(v.replace(",", ".")) for v in _SIZE_WORD.findall(prompt)]
    return triple, singles


def _design_sizes(primitives: list[Any]) -> list[float]:
    out: list[float] = []
    for part in primitives:
        if isinstance(part, dict):
            for key in ("x", "y", "h", "w", "d"):
                try:
                    out.append(float(part[key]))
                except (KeyError, TypeError, ValueError):
                    pass
    return out


def quality_problems(prompt: str, primitives: list[Any]) -> list[str]:
    """Why an approved draft is still a bad training example, or [] when it looks faithful."""
    from ai_cache import _QUOTED

    prompt = str(prompt or "")
    text = json.dumps(primitives, ensure_ascii=False)
    sizes = _design_sizes(primitives)
    problems: list[str] = []

    def near(value: float) -> bool:
        # Inner or outer size, with or without the sheet thickness: all count as honoured.
        return any(abs(value - size) <= 7.0 for size in sizes)

    triple, singles = _stated_sizes(prompt)
    if triple and sum(near(v) for v in triple) < 2:
        problems.append("ignores the stated size " + "x".join(f"{v:g}" for v in triple))
    for value in singles:
        if not near(value):
            problems.append(f"ignores the stated {value:g} mm")
    for part in primitives:
        if not isinstance(part, dict):
            continue
        dims = tuple(part.get(k) for k in ("x", "y", "h"))
        if str(part.get("type")) == "box" and dims == (180, 120, 70) and not triple:
            problems.append("copies the example box from the system prompt")
        holes = part.get("holes") if isinstance(part.get("holes"), list) else []
        if (part.get("w"), part.get("h")) == (100, 40) and any(isinstance(h, dict) and (h.get("x"), h.get("y")) == (50, 34) for h in holes):
            problems.append("copies the example panel from the system prompt")
    for word in _EXAMPLE_TEXTS:
        if f'"value": "{word}"' in text and word.casefold() not in prompt.casefold():
            problems.append(f"copies the example text {word}")
    quoted = _QUOTED.search(prompt)
    if quoted and quoted.group(1).strip().casefold() not in text.casefold():
        problems.append("leaves out the requested text " + quoted.group(1).strip())
    return list(dict.fromkeys(problems))


def example_problems(example: dict[str, Any]) -> list[str]:
    try:
        prims = json.loads(str(example.get("assistant") or "")).get("primitives") or []
    except (ValueError, AttributeError):
        return ["broken JSON"]
    return quality_problems(str(example.get("prompt") or ""), prims)


# --- collect -----------------------------------------------------------------------------


def collect_one(
    row: dict[str, Any], teacher: str, effort: str = "medium", detail: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], float, str]:
    """Teacher drafts one request. Returns (examples, usd spent, reason when nothing was kept).

    `detail`, when given, is filled with what a person needs to diagnose a failure: every
    gate note and the draft that was refused, or the full provider error.
    """
    import workshop

    detail = detail if detail is not None else {}

    prompt, thickness = str(row["prompt"]), row.get("thickness") or 3.0
    request = studio_request(prompt)
    drafts = workshop._PaidDrafts(
        thickness=thickness,
        parameters={"project": prompt[:48], "what_you_see": prompt, "thickness": float(thickness)},
        base="",
    )
    try:
        plan = drafts.call(request, teacher, effort)
        result = drafts.design(plan)
    except Exception as exc:
        detail["error"] = str(exc)[:600]
        return [], float(drafts.usage()["usd"]), "error:" + str(exc)[:120]
    examples: list[dict[str, Any]] = []
    base = {"prompt_id": row["id"], "prompt": prompt, "thickness": float(thickness), "teacher": teacher}
    if workshop._draft_blocked(result):
        notes = workshop._gate_issues(result)
        first = plan
        plan, result, info = drafts.repair(request, plan, result, model_id=teacher, client_ip="train")
        if workshop._draft_blocked(result):
            detail["first_notes"] = notes
            detail["notes"] = workshop._gate_issues(result) or notes
            detail["repair"] = {k: info.get(k) for k in ("attempted", "error")}
            detail["draft"] = json.dumps(plan.get("primitives") or [], ensure_ascii=False, separators=(",", ":"))[:4000]
            return [], float(drafts.usage()["usd"]), "blocked:" + "; ".join(notes[:2])[:160]
        if not info.get("free"):
            # A real repair turn: teaches the model to fix a blocked draft from the gate notes.
            from llm_client import repair_prompt

            examples.append({**base, "kind": "repair", "user": user_text(repair_prompt(request, first.get("primitives") or [], notes), thickness), "assistant": answer_json(plan)})
    problems = quality_problems(prompt, plan.get("primitives") or [])
    if problems:
        # Cuttable, but not what was asked for: never a training example.
        detail["notes"] = ["quality: " + p for p in problems]
        detail["draft"] = json.dumps(plan.get("primitives") or [], ensure_ascii=False, separators=(",", ":"))[:4000]
        return [], float(drafts.usage()["usd"]), "quality:" + "; ".join(problems)[:160]
    panels = len((result.get("assembly_result") or {}).get("parts") or [])
    examples.insert(0, {**base, "kind": "draft", "user": user_text(request, thickness), "assistant": answer_json(plan), "parts": panels})
    return examples, float(drafts.usage()["usd"]), ""


def cmd_collect(args: argparse.Namespace) -> int:
    from train_prompts import make_prompts

    from llm_keys import own_endpoint

    teacher = args.teacher.strip().lower()
    if not own_endpoint(teacher) and not args.spend:
        print(f"collect: up to {args.count} requests to {teacher}, stopping at ${args.max_usd:.2f}. Re-run with --spend to start.")
        return 2
    out = Path(args.out)
    if args.retry_rejected and (out / REJECTED).is_file():
        # After the gate or the repairs improve, earlier refusals deserve another try.
        (out / REJECTED).replace(out / (REJECTED + "." + time.strftime("%Y%m%d-%H%M%S") + ".old"))
    done = {r.get("prompt_id") for r in _read_jsonl(out / EXAMPLES)} | {r.get("prompt_id") for r in _read_jsonl(out / REJECTED)}
    todo = [r for r in make_prompts(args.count + len(done), seed=args.seed) if r["id"] not in done][: args.count]

    # Throwaway state and no daily caps: this is the operator's own batch, not site traffic.
    os.environ["MCP_DATA_DIR"] = tempfile.mkdtemp(prefix="lasermcp-train-")
    os.environ["LASERMCP_AI_CACHE_DAYS"] = "0"
    os.environ["LASERMCP_AI_DAILY_PER_IP"] = "1000000"
    os.environ["LASERMCP_AI_DAILY_GLOBAL"] = "1000000"
    os.environ["LASERMCP_LLM_MODELS"] = teacher
    os.environ.pop("LASERMCP_LLM_REPAIR_MODEL", None)

    spent, kept, failed, errors_in_a_row = 0.0, 0, 0, 0
    for i, row in enumerate(todo, 1):
        if spent >= args.max_usd:
            print(f"stopped: budget ${args.max_usd:.2f} reached")
            break
        detail: dict[str, Any] = {}
        examples, usd, why = collect_one(row, teacher, args.effort, detail)
        spent = round(spent + usd, 6)
        if examples:
            kept += 1
            errors_in_a_row = 0
            for ex in examples:
                _append(out / EXAMPLES, {**ex, "usd": usd if ex["kind"] == "draft" else 0.0})
        else:
            failed += 1
            if not why.startswith("error:"):
                # A provider error (wrong key, outage) says nothing about the request: leave it
                # for the next run instead of marking it as tried.
                _append(out / REJECTED, {"prompt_id": row["id"], "prompt": row["prompt"], "teacher": teacher, "why": why, "usd": usd, **detail})
            else:
                # Kept apart: read by `report`, never by the resume logic.
                _append(out / ERRORS, {"prompt_id": row["id"], "prompt": row["prompt"], "teacher": teacher, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **detail})
            errors_in_a_row = errors_in_a_row + 1 if why.startswith("error:") else 0
        print(f"[{i}/{len(todo)}] {'kept' if examples else 'drop'} ${spent:.3f} {row['prompt'][:60]} {why[:70]}", flush=True)
        if errors_in_a_row >= 5:
            # A wrong key or model id fails every call; do not walk the whole list.
            print("stopped: 5 provider errors in a row — check the key and the teacher model id")
            break
    print(f"\nkept {kept}, dropped {failed}, spent ${spent:.3f}. File: {out / EXAMPLES}")
    write_report(out)
    return 0


# --- report ------------------------------------------------------------------------------


def _shape(note: str) -> str:
    """A gate note with its numbers blanked, so the same problem groups together."""
    import re

    text = re.sub(r"[0-9]+(?:[.,][0-9]+)?", "#", str(note))
    return " ".join(text.split())[:90]


def build_report(out: Path) -> str:
    """What a run produced and why drafts were refused: short enough to paste or push."""
    from collections import Counter

    rows = _read_jsonl(out / EXAMPLES)
    kept = [r for r in rows if r.get("kind") == "draft"]
    repairs = [r for r in rows if r.get("kind") == "repair"]
    rejected = _read_jsonl(out / REJECTED)
    errors = _read_jsonl(out / ERRORS)
    tried = len(kept) + len(rejected)
    flawed = [(r, example_problems(r)) for r in kept]
    flawed = [(r, why) for r, why in flawed if why]
    teachers = sorted({str(r.get("teacher")) for r in kept + rejected + errors if r.get("teacher")})
    lines = [
        "LaserMCP training data report  " + time.strftime("%Y-%m-%d %H:%M"),
        "teachers: " + (", ".join(teachers) or "-"),
        f"requests tried: {tried}   kept: {len(kept)}   rejected: {len(rejected)}   yield: {(100.0 * len(kept) / tried if tried else 0):.0f}%",
        f"repair examples: {len(repairs)}   provider errors (not counted as tried): {len(errors)}",
        f"kept examples that are faithful to the request: {len(kept) - len(flawed)} of {len(kept)}   true yield: {(100.0 * (len(kept) - len(flawed)) / tried if tried else 0):.0f}%",
    ]
    if flawed:
        lines.append("")
        lines.append("kept by the gate but left out of training (not what was asked for):")
        lines += [f"  - {r.get('prompt')}: {'; '.join(why)}" for r, why in flawed[:25]]
    notes = Counter(_shape(n) for r in rejected for n in (r.get("notes") or [r.get("why") or "?"]))
    if notes:
        lines.append("")
        lines.append("why drafts were refused (gate notes, most common first; one draft can have several):")
        lines += [f"  {count:4d}  {text}" for text, count in notes.most_common(15)]
    errs = Counter(_shape(r.get("error") or "?") for r in errors)
    if errs:
        lines.append("")
        lines.append("provider errors:")
        lines += [f"  {count:4d}  {text}" for text, count in errs.most_common(8)]
    if rejected:
        lines.append("")
        lines.append("three refused drafts (request, then the start of the draft):")
        for r in rejected[-3:]:
            lines.append(f"  - {r.get('prompt')}")
            lines.append("    " + str(r.get("draft") or "")[:400])
    if kept:
        lines.append("")
        lines.append("faithful examples (latest), with the start of each design:")
        good = [r for r in kept if not example_problems(r)]
        lines += [f"  - {r.get('prompt')} ({r.get('parts')} parts)  {str(r.get('assistant'))[:160]}" for r in good[-12:]]
    return chr(10).join(lines) + chr(10)


def write_report(out: Path) -> str:
    text = build_report(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT).write_text(text, encoding="utf-8")
    return text


def cmd_report(args: argparse.Namespace) -> int:
    sys.stdout.buffer.write(write_report(Path(args.out)).encode("utf-8"))
    return 0


# --- build -------------------------------------------------------------------------------


def to_chat(example: dict[str, Any], system: str) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": str(example["user"])},
            {"role": "assistant", "content": str(example["assistant"])},
        ]
    }


def usable(example: dict[str, Any]) -> bool:
    """Drop rows the tuned model must not copy: broken JSON, empty designs, giant outputs."""
    try:
        data = json.loads(str(example.get("assistant") or ""))
    except ValueError:
        return False
    prims = data.get("primitives") if isinstance(data, dict) else None
    if not (isinstance(prims, list) and prims and str(example.get("user") or "").strip() and len(str(example["assistant"])) < 24000):
        return False
    # Rows collected before the quality check existed are judged here.
    return not quality_problems(str(example.get("prompt") or ""), prims)


def split(examples: list[dict[str, Any]], valid_share: float = 0.1, seed: int = 7) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Train/validation by request, so a draft and its own repair never straddle the split."""
    seen: set[str] = set()
    rows = []
    for ex in examples:
        key = hashlib.sha256((str(ex.get("user")) + "\x00" + str(ex.get("assistant"))).encode("utf-8")).hexdigest()
        if usable(ex) and key not in seen:
            seen.add(key)
            rows.append(ex)
    ids = sorted({str(ex.get("prompt_id") or ex.get("user")) for ex in rows})
    random.Random(seed).shuffle(ids)
    held = set(ids[: int(len(ids) * valid_share)]) if len(ids) >= 20 else set()
    train = [ex for ex in rows if str(ex.get("prompt_id") or ex.get("user")) not in held]
    valid = [ex for ex in rows if str(ex.get("prompt_id") or ex.get("user")) in held]
    return train, valid


def cmd_build(args: argparse.Namespace) -> int:
    from ai_cost import estimate_tokens
    from llm_client import tuned_system_prompt

    out = Path(args.out)
    train, valid = split(_read_jsonl(out / EXAMPLES))
    if len(train) < MIN_EXAMPLES:
        print(f"only {len(train)} usable examples in {out / EXAMPLES}; need at least {MIN_EXAMPLES} (a few hundred to be useful). Run collect first.")
        return 1
    system = tuned_system_prompt()
    tokens = 0
    for name, rows in (("train.jsonl", train), ("valid.jsonl", valid)):
        lines = [json.dumps(to_chat(ex, system), ensure_ascii=False) for ex in rows]
        (out / name).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        if name == "train.jsonl":
            tokens = sum(estimate_tokens(line) for line in lines)
    rate = float(os.environ.get("LASERMCP_TUNE_PRICE_PER_MTOK") or 3.0)
    usd = tokens * args.epochs * rate / 1_000_000.0
    repairs = sum(1 for ex in train if ex.get("kind") == "repair")
    print(f"train {len(train)} ({repairs} repair turns), validation {len(valid)}")
    print(f"~{tokens:,} training tokens x {args.epochs} epochs ~ ${usd:.2f} at ${rate:g}/1M (estimate; check the provider's price)")
    if len(train) < 200:
        print("note: under 200 examples the tuned model rarely beats the base model. Collect more before `start`.")
    return 0


# --- start / status ----------------------------------------------------------------------


def _key() -> str:
    key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set in this terminal. Set it yourself; never paste it into a chat.")
    return key


def _api(method: str, path: str, *, body: bytes | None = None, content_type: str = "application/json") -> dict[str, Any]:
    req = urllib.request.Request("https://api.openai.com/v1" + path, data=body, method=method, headers={"authorization": f"Bearer {_key()}", "content-type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit(f"provider HTTP {exc.code}: {detail}") from exc


def multipart(path: Path, purpose: str = "fine-tune") -> tuple[bytes, str]:
    boundary = "lasermcp" + uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\n{purpose}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/jsonl\r\n\r\n"
    ).encode("utf-8")
    return head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def cmd_start(args: argparse.Namespace) -> int:
    out = Path(args.out)
    train, valid = out / "train.jsonl", out / "valid.jsonl"
    if not train.is_file() or not train.read_text(encoding="utf-8").strip():
        print("no train.jsonl — run `build` first")
        return 1
    if not args.spend:
        print(f"start: uploads {train.name} and begins a paid fine-tuning job on {args.base}. Re-run with --spend to start.")
        return 2
    files = {}
    for name, path in (("training_file", train), ("validation_file", valid)):
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            body, ctype = multipart(path)
            files[name] = _api("POST", "/files", body=body, content_type=ctype)["id"]
            print(f"uploaded {path.name} -> {files[name]}")
    spec = {"model": args.base, "suffix": "lasermcp", **files}
    if args.epochs:
        spec["hyperparameters"] = {"n_epochs": args.epochs}
    job = _api("POST", "/fine_tuning/jobs", body=json.dumps(spec).encode("utf-8"))
    (out / "job.json").write_text(json.dumps({"id": job.get("id"), "base": args.base, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1), encoding="utf-8")
    print(f"job {job.get('id')} is {job.get('status')}. Check it with: tools/train.py status")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.out) / "job.json"
    if not path.is_file():
        print("no job started yet — run `start`")
        return 1
    job = _api("GET", "/fine_tuning/jobs/" + json.loads(path.read_text(encoding="utf-8"))["id"])
    print(f"status: {job.get('status')}   trained tokens: {job.get('trained_tokens')}")
    if job.get("error") and (job["error"] or {}).get("message"):
        print("error:", job["error"]["message"])
    model = job.get("fine_tuned_model")
    if model:
        print(f"\nmodel ready: {model}")
        print("1) locally:  set LASERMCP_TUNED_MODEL to that id, then run tools/ai_eval.py --model lasermcp-tuned --spend")
        print("2) if it beats the base model: add LASERMCP_TUNED_MODEL in Vercel; add LASERMCP_LLM_DEFAULT_MODEL=lasermcp-tuned to make it the default")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(OUT), help="working folder (default output/train)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="teacher model drafts requests; gate-approved drafts are kept")
    c.add_argument("--teacher", default="local:lasermcp-teacher", help="local:<name> is free; a provider model id bills your key")
    c.add_argument("--count", type=int, default=300)
    c.add_argument("--max-usd", type=float, default=20.0)
    c.add_argument("--effort", default="medium", choices=["low", "medium", "high"])
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--spend", action="store_true")
    c.add_argument("--retry-rejected", action="store_true", help="try earlier refused requests again")
    c.set_defaults(fn=cmd_collect)
    b = sub.add_parser("build", help="examples.jsonl -> train.jsonl / valid.jsonl")
    b.add_argument("--epochs", type=int, default=3)
    b.set_defaults(fn=cmd_build)
    s = sub.add_parser("start", help="upload the files and start the fine-tuning job")
    s.add_argument("--base", default=DEFAULT_BASE)
    s.add_argument("--epochs", type=int, default=0, help="0 lets the provider choose")
    s.add_argument("--spend", action="store_true")
    s.set_defaults(fn=cmd_start)
    sub.add_parser("status", help="job state and the model id when done").set_defaults(fn=cmd_status)
    sub.add_parser("report", help="yield and the reasons drafts were refused (also written to report.txt)").set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
