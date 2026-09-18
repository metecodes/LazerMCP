"""Designer → Reviewer → Repair → Reviewer → Final Gate.

Runs inside create_design so the client AI cannot skip review.
"""

from __future__ import annotations

import copy
import json
from typing import Any

MAX_REVIEW = 3

STAGES = ("designer", "reviewer", "repair", "reviewer", "final_gate")


def _sig(parts: list[Any]) -> str:
    return json.dumps(parts, sort_keys=True, default=str)


def run_pipeline(primitives: list[Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    from repair import repair_primitives
    from review import review_built
    from toolbox import render_toolbox

    params = parameters or {}
    parts: list[Any] = copy.deepcopy(list(primitives or []))
    iterations: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    built: dict[str, Any] | None = None
    report: dict[str, Any] | None = None

    for i in range(1, MAX_REVIEW + 1):
        built = render_toolbox(parts, params)
        parts = list(built.get("primitives") or parts)
        report = review_built(built)
        iterations.append(
            {
                "iteration": i,
                "stage": "reviewer",
                "pass": report["counts"]["pass"],
                "warning": report["counts"]["warning"],
                "fail": report["counts"]["fail"],
                "not_verified": report["counts"]["not_verified"],
                "final_status": report["final_status"],
            }
        )
        if report["final_status"] != "BLOCKED":
            break
        if i >= MAX_REVIEW:
            break
        repaired, actions = repair_primitives(parts, report)
        if not actions or _sig(repaired) == _sig(parts):
            iterations.append({"iteration": i, "stage": "repair", "actions": [], "note": "no further parametric repair"})
            break
        repairs.extend(actions)
        iterations.append({"iteration": i, "stage": "repair", "actions": actions})
        parts = repaired

    assert built is not None and report is not None
    built["pipeline"] = {
        "stages": list(STAGES),
        "iterations": iterations,
        "repairs": repairs,
        "max_review": MAX_REVIEW,
    }
    return _attach_gate(built, report)


def review_only(built: dict[str, Any]) -> dict[str, Any]:
    from review import review_built

    report = review_built(built)
    built = dict(built)
    built.setdefault(
        "pipeline",
        {"stages": list(STAGES), "iterations": [{"iteration": 1, "stage": "reviewer", "final_status": report["final_status"]}]},
    )
    return _attach_gate(built, report)


def _attach_gate(built: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    built["review"] = report
    built["blocking_checks"] = report.get("blocking_checks") or []
    built["final_status"] = report["final_status"]
    built["ready_to_cut"] = bool(report.get("ready_to_cut"))
    built["speak"] = report.get("speak")
    built["design_map"] = report.get("design_map")
    built["connections"] = report.get("connections")
    built["scorecard"] = report.get("scorecard")
    built["physical"] = report.get("physical")
    built["assembly_sheet"] = report.get("assembly_sheet")
    built["authorized_output"] = report.get("authorized_output")
    built["production_export"] = report.get("production_export") or "BLOCKED"
    built["production_summary"] = report.get("production_summary")
    if report.get("look_again"):
        built["look_again"] = report["look_again"]
    return built
