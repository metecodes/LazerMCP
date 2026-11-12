"""Studio AI benchmark: run the fixed prompt set through the real Studio AI path and score it.

Run from the repository root:
  .venv/Scripts/python.exe tools/ai_eval.py                      free: routing + local planner
  .venv/Scripts/python.exe tools/ai_eval.py --model local:lasermcp-teacher  free: a model on this machine
  .venv/Scripts/python.exe tools/ai_eval.py --model gpt-4o-mini --spend   paid: bills the key in your env

A paid run reads OPENAI_API_KEY / ANTHROPIC_API_KEY from the environment and refuses to
start without --spend. Every run uses a throwaway data directory, so nothing here touches
projects, quota or the draft cache. Reports land in output/ai_eval/ (not committed).

What a score means: "passed" is the software gate plus the part-count range of the prompt.
It never says a design is good or fits physically; look at a sample by eye.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROMPTS = Path(__file__).with_name("ai_eval_prompts.json")
FREE_METHODS = {"studio_maker", "studio_box", "plan_laser_job", "workshop_llm_cache"}


def load_prompts(path: Path = PROMPTS) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8")).get("prompts") or []
    return [row for row in rows if isinstance(row, dict) and row.get("prompt")]


def score(row: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
    """One prompt's verdict from a create_studio_ai reply. Pure: no I/O, no model."""
    job = reply.get("plan_job") if isinstance(reply.get("plan_job"), dict) else {}
    method = str(job.get("method") or "")
    repair = reply.get("auto_repair") if isinstance(reply.get("auto_repair"), dict) else {}
    usage = job.get("usage") if isinstance(job.get("usage"), dict) else {}
    panels = len(((reply.get("assembly") or {}).get("panels")) or [])
    gate_ok = bool(reply.get("success")) and str(reply.get("final_status") or "BLOCKED") not in {"BLOCKED", "FAIL"}
    problems: list[str] = []
    if not gate_ok:
        problems.append("blocked")
    want = str(row.get("expect_method") or "")
    paid = method == "workshop_llm"
    if want == "studio_maker" and method != "studio_maker":
        problems.append(f"route:{method or 'none'}")
    if want == "studio_maker" and row.get("expect_maker") and job.get("maker") != row["expect_maker"]:
        problems.append(f"maker:{job.get('maker')}")
    if want == "local" and paid:
        problems.append("route:paid")
    low, high = row.get("min_panels"), row.get("max_panels")
    if gate_ok and low is not None and panels < int(low):
        problems.append(f"parts:{panels}<{low}")
    if gate_ok and high is not None and panels > int(high):
        problems.append(f"parts:{panels}>{high}")
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "prompt": row.get("prompt"),
        "method": method,
        "paid": paid,
        "gate_ok": gate_ok,
        "passed": not problems,
        "first_pass": gate_ok and not repair.get("fixed") and not int(repair.get("attempted") or 0),
        "repaired": bool(repair.get("fixed")),
        "repair_calls": int(repair.get("attempted") or 0),
        "panels": panels,
        "usd": float(usage.get("usd") or 0.0),
        "problems": problems,
        "issues": [str(x)[:160] for x in (repair.get("issues") or [])][:3],
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def block(items: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(items)
        usd = round(sum(r["usd"] for r in items), 4)
        return {
            "n": n,
            "passed": sum(r["passed"] for r in items),
            "gate_ok": sum(r["gate_ok"] for r in items),
            "first_pass": sum(r["first_pass"] for r in items),
            "repaired": sum(r["repaired"] for r in items),
            "paid_requests": sum(r["paid"] for r in items),
            "usd": usd,
            "usd_per_request": round(usd / n, 4) if n else 0.0,
        }

    cats: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        cats.setdefault(str(row["category"]), []).append(row)
    return {"all": block(rows), "by_category": {name: block(items) for name, items in cats.items()}}


def run(model: str, rows: list[dict[str, Any]], *, thickness: float = 3.0) -> list[dict[str, Any]]:
    """Call the same function the /api/studio/ai route calls, once per prompt."""
    sys.path.insert(0, str(ROOT))
    import workshop

    out = []
    for i, row in enumerate(rows, 1):
        body: dict[str, Any] = {
            "prompt": row["prompt"],
            "messages": [{"role": "user", "text": row["prompt"]}],
            "thickness": thickness,
        }
        if model == "local":
            if not row.get("expect_method"):
                # Recipes and plain boxes keep their own free route; only the model is skipped.
                body["planner"] = "local"
        else:
            body["model"] = model
        started = time.time()
        try:
            reply = workshop.create_studio_ai(body, client_ip=f"eval-{i}")
        except Exception as exc:  # one bad prompt must not lose the run
            reply = {"success": False, "final_status": "BLOCKED", "error": str(exc)[:200]}
        verdict = score(row, reply)
        verdict["seconds"] = round(time.time() - started, 1)
        if reply.get("error"):
            verdict["problems"].append("error:" + str(reply["error"])[:80])
        out.append(verdict)
        mark = "ok " if verdict["passed"] else "BAD"
        print(f"[{i:02d}/{len(rows)}] {mark} {verdict['id']:<12} {verdict['method'] or '-':<16} "
              f"${verdict['usd']:.4f} {','.join(verdict['problems'])}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="local", help="'local' (free) or a model id such as gpt-4o-mini")
    ap.add_argument("--spend", action="store_true", help="required for a model run: it bills your provider key")
    ap.add_argument("--only", default="", help="comma list of categories")
    ap.add_argument("--limit", type=int, default=0, help="first N prompts after filtering")
    ap.add_argument("--no-repair", action="store_true", help="measure the raw first draft only")
    ap.add_argument("--out", default="", help="report path (default output/ai_eval/<model>-<time>.json)")
    args = ap.parse_args(argv)

    rows = load_prompts()
    if args.only:
        keep = {c.strip() for c in args.only.split(",") if c.strip()}
        rows = [r for r in rows if r.get("category") in keep]
    if args.limit > 0:
        rows = rows[: args.limit]
    model = args.model.strip().lower()
    from llm_keys import own_endpoint

    if model != "local" and not own_endpoint(model) and not args.spend:
        paid = sum(1 for r in rows if not r.get("expect_method"))
        print(f"{model}: up to {paid} paid requests (each may add repair calls). Re-run with --spend to start.")
        return 2

    # Throwaway state: no projects, no quota, no cached drafts, no daily caps in the way.
    os.environ["MCP_DATA_DIR"] = tempfile.mkdtemp(prefix="lasermcp-eval-")
    os.environ["LASERMCP_AI_CACHE_DAYS"] = "0"
    os.environ["LASERMCP_AI_DAILY_PER_IP"] = "100000"
    os.environ["LASERMCP_AI_DAILY_GLOBAL"] = "100000"
    if args.no_repair:
        os.environ["LASERMCP_AI_AUTO_REPAIR"] = "0"
    if model != "local":
        os.environ["LASERMCP_LLM_MODELS"] = model

    results = run(model, rows)
    summary = summarize(results)
    report = {"model": model, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "repair": not args.no_repair, "summary": summary, "results": results}
    out = Path(args.out) if args.out else ROOT / "output" / "ai_eval" / f"{model}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'category':<10} {'n':>3} {'passed':>7} {'gate':>5} {'1st':>4} {'fixed':>6} {'usd':>8}")
    for name, b in [*summary["by_category"].items(), ("ALL", summary["all"])]:
        print(f"{name:<10} {b['n']:>3} {b['passed']:>7} {b['gate_ok']:>5} {b['first_pass']:>4} {b['repaired']:>6} {b['usd']:>8.4f}")
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
