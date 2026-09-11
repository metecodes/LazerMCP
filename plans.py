"""Freemium plans. Landing stays on beta — prices are not the public story yet."""

from __future__ import annotations

import os
from typing import Any

from keys import current_auth

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "designs_per_month": 10,
        "svg": True,
        "dxf": False,
        "custom_materials": False,
        "machine_profiles": False,
        "photo": False,
        "advanced_validation": False,
        "bom": False,
        "advanced_nesting": False,
        "project_history": False,
        "api": False,
        "commercial": False,
        "support": "community",
        "price_usd": 0,
    },
    "maker": {
        "id": "maker",
        "name": "Maker",
        "designs_per_month": 150,
        "svg": True,
        "dxf": True,
        "custom_materials": True,
        "machine_profiles": True,
        "photo": True,
        "advanced_validation": True,
        "bom": False,
        "advanced_nesting": False,
        "project_history": False,
        "api": False,
        "commercial": False,
        "support": "email",
        "price_usd": 12,
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "designs_per_month": 2000,
        "svg": True,
        "dxf": True,
        "custom_materials": True,
        "machine_profiles": True,
        "photo": True,
        "advanced_validation": True,
        "bom": True,
        "advanced_nesting": True,
        "project_history": True,
        "api": True,
        "commercial": True,
        "support": "priority",
        "price_usd": 39,
    },
}

_ROLE_PLAN = {"admin": "pro", "workshop": "maker", "maker": "maker", "pro": "pro", "free": "free"}


def beta_open() -> bool:
    return str(os.environ.get("LASERMCP_BETA") or "1").strip().lower() not in {"0", "false", "no", "off"}


def resolve_plan_id(key: dict[str, Any] | None = None) -> str:
    row = key if key is not None else current_auth.get()
    if not row:
        return "free"
    raw = str(row.get("plan") or row.get("role") or "free").strip().lower()
    return _ROLE_PLAN.get(raw, raw if raw in PLANS else "free")


def get_plan(plan_id: str | None = None) -> dict[str, Any]:
    return dict(PLANS.get(plan_id or resolve_plan_id()) or PLANS["free"])


def entitled(feature: str, key: dict[str, Any] | None = None) -> bool:
    if beta_open():
        return True
    return bool(get_plan(resolve_plan_id(key)).get(feature))


def gate_job(feature: str = "design") -> dict[str, Any]:
    """MCP-safe: never raises. look_again when a paid feature or quota is closed."""
    from metering import designs_this_month

    key = current_auth.get()
    plan = get_plan(resolve_plan_id(key))
    used = designs_this_month((key or {}).get("id") or "anon")
    quota = int(plan.get("designs_per_month") or 0)
    info = {
        "success": True,
        "ok": True,
        "beta": beta_open(),
        "plan": plan["id"],
        "plan_name": plan["name"],
        "used": used,
        "quota": quota,
    }
    if beta_open():
        return info
    need = {
        "photo": "photo",
        "dxf": "dxf",
        "bom": "bom",
        "history": "project_history",
        "nesting": "advanced_nesting",
        "api": "api",
    }.get(feature)
    if need and not plan.get(need):
        info["ok"] = False
        info["look_again"] = [f"{feature} is on Maker/Pro. This key is {plan['name']}."]
        return info
    if feature == "design" and quota and used >= quota:
        info["ok"] = False
        info["look_again"] = [f"{plan['name']} includes {quota} designs / month. {used} already used."]
    return info


def apply_plan_to_result(result: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strip exports the current plan does not include. Beta keeps everything visible."""
    data = result
    extra = extra or {}
    plan = get_plan()
    data["plan"] = {"id": plan["id"], "name": plan["name"], "beta": beta_open(), "quota": plan["designs_per_month"]}
    extra["plan"] = data["plan"]
    if beta_open():
        return data
    if not plan.get("dxf"):
        for key in ("dxf_id", "dxf_url"):
            data.pop(key, None)
        defaults = dict(data.get("applied_defaults") or {})
        defaults["output"] = "svg"
        data["applied_defaults"] = defaults
    if not plan.get("bom"):
        data.pop("bom", None)
        data.pop("bom_id", None)
        data.pop("materials_speak", None)
        speak = str(data.get("speak") or "")
        if "MATERIALS (MCP)" in speak:
            data["speak"] = speak.split("MATERIALS (MCP)")[0].rstrip()
    if not plan.get("project_history"):
        data.pop("project", None)
    if not plan.get("advanced_nesting"):
        data.pop("sheet_ids", None)
        if data.get("sheets"):
            data["sheets"] = 1
    return data


def public_plans() -> dict[str, Any]:
    """Catalog for studio. Landing does not publish prices during beta."""
    rows = []
    for plan in PLANS.values():
        row = {k: v for k, v in plan.items() if k != "price_usd"}
        row["price_visible"] = False
        rows.append(row)
    return {
        "success": True,
        "beta": beta_open(),
        "plans": rows,
        "note": "Beta is open. Pricing stays unpublished until usage is measured.",
    }
