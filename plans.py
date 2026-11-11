"""Freemium plans. MCP stays thin/free; platform AI and DXF are paid when beta is off."""

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
        "platform_3d": True,
        "platform_ai": False,
        "mcp_create": True,
        "commercial": False,
        "support": "community",
        "price_usd": 0,
    },
    "maker": {
        "id": "maker",
        "name": "Maker",
        "designs_per_month": 80,
        "svg": True,
        "dxf": True,
        "custom_materials": True,
        "machine_profiles": True,
        "photo": True,
        "advanced_validation": True,
        "bom": False,
        "advanced_nesting": False,
        "project_history": True,
        "api": False,
        "platform_3d": True,
        "platform_ai": True,
        "mcp_create": True,
        "commercial": False,
        "support": "email",
        "price_usd": 12,
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "designs_per_month": 400,
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
        "platform_3d": True,
        "platform_ai": True,
        "mcp_create": True,
        "commercial": True,
        "support": "priority",
        "price_usd": 39,
    },
}

# Free MCP may call these; paid features stay on Maker/Pro when beta is closed.
MCP_FREE_TOOLS = {
    "plan_laser_job",
    "payas_defaults",
    "get_operation_settings",
    "list_cad_tools",
    "get_generator_schema",
    "validate_svg",
    "validate_assembly",
    "get_preview",
    "render_preview",
    "studio",
}
MCP_QUOTA_TOOLS = {
    "create_design",
    "generate_svg",
    "create_from_reference",
}
MCP_PAID_TOOLS = {
    "create_from_reference",
    "export_dxf",
    "export_composed_dxf",
}

_ROLE_PLAN = {"admin": "pro", "workshop": "maker", "maker": "maker", "pro": "pro", "free": "free"}


def beta_open() -> bool:
    return str(os.environ.get("LASERMCP_BETA") or "1").strip().lower() not in {"0", "false", "no", "off"}


def hard_quota() -> bool:
    """When true, monthly design quotas apply even if beta is open (platform cost control)."""
    raw = str(os.environ.get("LASERMCP_HARD_QUOTA") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return not beta_open()


def resolve_plan_id(key: dict[str, Any] | None = None) -> str:
    row = key if key is not None else current_auth.get()
    if not row:
        return "free"
    raw = str(row.get("plan") or row.get("role") or "free").strip().lower()
    return _ROLE_PLAN.get(raw, raw if raw in PLANS else "free")


def get_plan(plan_id: str | None = None) -> dict[str, Any]:
    return dict(PLANS.get(plan_id or resolve_plan_id()) or PLANS["free"])


def entitled(feature: str, key: dict[str, Any] | None = None) -> bool:
    if beta_open() and not hard_quota():
        return True
    return bool(get_plan(resolve_plan_id(key)).get(feature))


def gate_job(feature: str = "design") -> dict[str, Any]:
    """MCP-safe: never raises. look_again when a paid feature or quota is closed."""
    from metering import designs_this_month

    key = current_auth.get()
    plan = get_plan(resolve_plan_id(key))
    used = designs_this_month((key or {}).get("id") or None)  # guests: per-address id from metering
    quota = int(plan.get("designs_per_month") or 0)
    info = {
        "success": True,
        "ok": True,
        "beta": beta_open(),
        "hard_quota": hard_quota(),
        "plan": plan["id"],
        "plan_name": plan["name"],
        "used": used,
        "quota": quota,
    }
    need = {
        "photo": "photo",
        "dxf": "dxf",
        "bom": "bom",
        "history": "project_history",
        "nesting": "advanced_nesting",
        "api": "api",
        "platform_ai": "platform_ai",
        "ai": "platform_ai",
    }.get(feature)
    enforce_features = hard_quota() or not beta_open()
    if enforce_features and need and not plan.get(need):
        info["ok"] = False
        info["look_again"] = [f"{feature} is on Maker/Pro. This account is {plan['name']}."]
        return info
    if feature in {"design", "platform_ai", "ai"} and hard_quota() and quota and used >= quota:
        info["ok"] = False
        info["look_again"] = [
            f"{plan['name']} includes {quota} designs / month. {used} already used. Upgrade or wait for next month."
        ]
    return info


def gate_mcp_tool(tool: str, key: dict[str, Any] | None = None) -> dict[str, Any]:
    """Thin free MCP: allowlist + paid tool lock when entitlements are enforced."""
    name = str(tool or "").strip()
    plan = get_plan(resolve_plan_id(key))
    info = gate_job("design" if name in MCP_QUOTA_TOOLS else "open")
    info["tool"] = name
    if not hard_quota() and beta_open():
        return info
    if name in MCP_PAID_TOOLS and not plan.get("photo") and name == "create_from_reference":
        info["ok"] = False
        info["look_again"] = ["create_from_reference needs Maker/Pro. Free MCP: plan_laser_job or limited create_design."]
        return info
    if name in MCP_PAID_TOOLS and name.startswith("export") and not plan.get("dxf"):
        info["ok"] = False
        info["look_again"] = ["DXF export needs Maker/Pro."]
        return info
    if name in MCP_QUOTA_TOOLS and not plan.get("mcp_create") and plan["id"] == "free":
        # free still has mcp_create True; reserved for future kill-switch
        pass
    if name in MCP_QUOTA_TOOLS:
        return gate_job("design")
    if name and name not in MCP_FREE_TOOLS and name not in MCP_QUOTA_TOOLS and name not in MCP_PAID_TOOLS:
        # Unknown tools stay available on Maker/Pro; free gets look_again for expensive ones only via paid set
        pass
    return info


def apply_plan_to_result(result: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strip exports the current plan does not include. Beta keeps everything visible unless hard quota."""
    data = result
    extra = extra or {}
    plan = get_plan()
    data["plan"] = {
        "id": plan["id"],
        "name": plan["name"],
        "beta": beta_open(),
        "hard_quota": hard_quota(),
        "quota": plan["designs_per_month"],
    }
    extra["plan"] = data["plan"]
    if beta_open() and not hard_quota():
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
        row["price_visible"] = not beta_open()
        if not beta_open():
            row["price_usd"] = plan.get("price_usd")
        rows.append(row)
    return {
        "success": True,
        "beta": beta_open(),
        "hard_quota": hard_quota(),
        "plans": rows,
        "note": (
            "Beta is open. Pricing stays unpublished until usage is measured."
            if beta_open()
            else "MCP link stays free and thin. Platform AI, DXF and history are Maker/Pro."
        ),
    }
