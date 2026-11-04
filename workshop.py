"""Workshop loop: onboard → cut → human feedback → version. Never invents a physical PASS."""

from __future__ import annotations

import secrets
from typing import Any

from catalog import (
    get_batch,
    get_machine,
    mint_activation,
    public_catalog,
    redeem_activation,
    upsert_batch,
    upsert_machine,
)
from profiles import MATERIALS, apply_profiles, list_profiles, resolve_machine, resolve_material
from projects import list_projects, project_by_file, project_history, save_version
from review import FAIL, NOT_VERIFIED, PASS, WARNING, build_scorecard
from studio_store import now_iso, read_json, write_json

STEPS = ("machine", "bed", "material", "thickness", "coupon")
FITS = ("seated", "loose", "tight", "collision", "hole_small", "hole_large", "other")


def _owner(principal: dict[str, Any] | None) -> str:
    return str((principal or {}).get("id") or (principal or {}).get("email") or "anon")


def _onboarding_store() -> dict[str, Any]:
    raw = read_json("onboarding.json", {})
    return raw if isinstance(raw, dict) else {}


def _feedback_rows() -> list[dict[str, Any]]:
    raw = read_json("cut_feedback.json", [])
    return raw if isinstance(raw, list) else []


def get_onboarding(principal: dict[str, Any] | None = None) -> dict[str, Any]:
    store = _onboarding_store()
    row = store.get(_owner(principal)) or {"step": "machine"}
    return {"success": True, "onboarding": row, "steps": list(STEPS), "catalog": public_catalog()}


def save_onboarding(body: dict[str, Any], principal: dict[str, Any] | None = None) -> dict[str, Any]:
    owner = _owner(principal)
    store = _onboarding_store()
    row = dict(store.get(owner) or {"step": "machine"})
    machine_id = str(body.get("machine") or body.get("machine_id") or row.get("machine") or "")
    has_bed = str(body.get("bed_w") or "").strip() and str(body.get("bed_h") or "").strip()
    if (body.get("brand") or body.get("model")) and has_bed:
        created = upsert_machine(body, owner=owner)
        machine_id = created["id"]
        row["machine"] = machine_id
    if machine_id:
        machine = get_machine(machine_id) or resolve_machine({"machine": machine_id})
        row["machine"] = machine.get("id")
        row["bed_w"] = float(body.get("bed_w") or machine.get("bed_w") or row.get("bed_w") or 0)
        row["bed_h"] = float(body.get("bed_h") or machine.get("bed_h") or row.get("bed_h") or 0)
    if body.get("material") or body.get("material_id"):
        row["material"] = str(body.get("material") or body.get("material_id"))
    if body.get("batch_id"):
        row["batch_id"] = str(body.get("batch_id"))
        batch = get_batch(row["batch_id"])
        if batch:
            row["material"] = batch.get("material")
            if batch.get("measured_thickness"):
                row["thickness"] = batch["measured_thickness"]
    if body.get("thickness") not in (None, ""):
        row["thickness"] = float(body.get("thickness"))
    if body.get("step") in STEPS:
        row["step"] = body.get("step")
    elif not row.get("machine"):
        row["step"] = "machine"
    elif not row.get("bed_w"):
        row["step"] = "bed"
    elif not row.get("material"):
        row["step"] = "material"
    elif not row.get("thickness"):
        row["step"] = "thickness"
    else:
        row["step"] = "coupon"
    row["updated"] = now_iso()
    store[owner] = row
    write_json("onboarding.json", store)
    params = apply_profiles({"machine": row.get("machine"), "material": row.get("material"), "batch_id": row.get("batch_id")})
    return {
        "success": True,
        "onboarding": row,
        "profiles": {"machine": params.get("_machine"), "material": params.get("_material")},
        "next": row.get("step"),
        "look_again": (
            ["Cut the coupon and pass measured_bar_mm. Software will not invent kerf."]
            if row.get("step") == "coupon"
            else []
        ),
    }


def record_feedback(body: dict[str, Any], principal: dict[str, Any] | None = None) -> dict[str, Any]:
    fit = str(body.get("fit") or body.get("result") or "").strip().lower()
    if fit not in FITS:
        raise ValueError("fit must be seated|loose|tight|collision|hole_small|hole_large|other")
    row = {
        "id": "fb_" + secrets.token_hex(4),
        "at": now_iso(),
        "owner": _owner(principal),
        "project_id": str(body.get("project_id") or ""),
        "version": body.get("version"),
        "file_id": str(body.get("file_id") or ""),
        "machine": str(body.get("machine") or body.get("machine_id") or ""),
        "material": str(body.get("material") or body.get("material_id") or ""),
        "batch_id": str(body.get("batch_id") or ""),
        "fit": fit,
        "note": str(body.get("note") or "")[:240],
        "measured_bar_mm": body.get("measured_bar_mm"),
        "physical_pass": False,
    }
    rows = _feedback_rows()
    rows.append(row)
    write_json("cut_feedback.json", rows[-500:])
    if row.get("project_id"):
        save_version(
            {"project_id": row["project_id"], "machine": row["machine"], "material": row["material"]},
            {
                "file_id": row.get("file_id"),
                "final_status": "FEEDBACK",
                "speak": f"human fit={fit}",
                "feedback": row,
            },
        )
    return {
        "success": True,
        "feedback": row,
        "look_again": [
            "Recorded against project + machine + material. This is not a software PASS.",
            "PRODUCTION READY still needs human kerf/assembly/movement/use.",
        ],
    }


def list_feedback(project_id: str = "") -> list[dict[str, Any]]:
    rows = _feedback_rows()
    if project_id:
        rows = [row for row in rows if row.get("project_id") == project_id]
    return list(reversed(rows[-80:]))


def preflight(body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    score = payload.get("scorecard")
    if not isinstance(score, dict):
        score = build_scorecard(payload.get("categories") or [], payload.get("physical"))
    digital = score.get("digital") or {}
    physical = score.get("physical") or {}
    checks: list[dict[str, Any]] = []
    worst = PASS
    rank = {FAIL: 3, WARNING: 2, NOT_VERIFIED: 1, PASS: 0}
    for name, status in digital.items():
        label = str(status or PASS)
        if label == "N/A":
            label = PASS
        checks.append({"group": "software", "name": name, "status": label})
        if rank.get(label, 0) > rank.get(worst, 0) and label != NOT_VERIFIED:
            worst = label
    for name, status in physical.items():
        label = str(status or NOT_VERIFIED)
        checks.append({"group": "human", "name": name, "status": label})
    machine = resolve_machine(payload)
    material = resolve_material(payload)
    batch = get_batch(str(payload.get("batch_id") or ""))
    checks.append(
        {
            "group": "profile",
            "name": "Machine / material",
            "status": PASS if machine and material else WARNING,
            "detail": f"{machine.get('name')} · {material.get('name')}"
            + (f" · batch {batch.get('id')}" if batch else ""),
        }
    )
    if any(c["status"] == FAIL and c["group"] == "software" for c in checks):
        result = FAIL
    elif any(c["status"] == WARNING and c["group"] == "software" for c in checks):
        result = WARNING
    else:
        result = PASS
    return {
        "success": True,
        "result": result,
        "checks": checks,
        "human": [c for c in checks if c["group"] == "human"],
        "note": "Software PASS is digital only. Human rows stay NOT VERIFIED until a person cuts.",
    }


def _part_keys(item: dict[str, Any]) -> list[str]:
    return [
        str(item.get("label") or ""),
        str(item.get("part_id") or ""),
        str(item.get("id") or ""),
        str(item.get("name") or ""),
        str(item.get("type") or ""),
    ]


def _find_part(primitives: list[dict[str, Any]], part: str) -> tuple[int, dict[str, Any]]:
    raw = str(part or "").strip()
    if raw.isdigit():
        idx = int(raw)
        if 0 <= idx < len(primitives):
            return idx, dict(primitives[idx])
    needle = raw.lower()
    for idx, item in enumerate(primitives):
        keys = [k.lower() for k in _part_keys(item) if k]
        if needle and needle in keys:
            return idx, dict(item)
    for idx, item in enumerate(primitives):
        label = " ".join(k.lower() for k in _part_keys(item) if k)
        if needle and needle in label:
            return idx, dict(item)
    raise ValueError("part not found — pass label or index")


def editor_context(file_id: str) -> dict[str, Any]:
    hit = project_by_file(file_id) or {}
    primitives = [dict(p) for p in (hit.get("primitives") or []) if isinstance(p, dict)]
    parts = []
    for idx, part in enumerate(primitives):
        parts.append(
            {
                "index": idx,
                "label": str(part.get("label") or part.get("part_id") or part.get("id") or part.get("type") or f"part-{idx}"),
                "part_id": str(part.get("part_id") or part.get("id") or ""),
                "type": part.get("type"),
                "x": part.get("x") or part.get("w"),
                "y": part.get("y") or part.get("h"),
            }
        )
    from assembly import check_assembly
    parameters = dict(hit.get("parameters") or {})
    assembly_result = hit.get("assembly_result") if isinstance(hit.get("assembly_result"), dict) else None
    assembly = {}
    if primitives and not assembly_result:
        assembly = check_assembly(primitives, thickness=float(parameters.get("thickness") or 3), parameters=parameters)
        from assembly_result import build as build_assembly_result
        assembly_result = build_assembly_result(assembly, file_id=str(file_id or ""), project_id=hit.get("project_id"))
        # Old project versions did not contain an assembly hand-off.  Resolve
        # it once, retain it on that version, then let all future previews use
        # the stored transforms without invoking the solver again.
        from projects import attach_assembly_result
        attach_assembly_result(str(file_id or ""), assembly_result)
    return {
        "success": True,
        "file_id": str(file_id or ""),
        "dxf_id": hit.get("dxf_id"),
        "dxf_url": ("/files/" + str(hit.get("dxf_id")) + "?download=1") if hit.get("dxf_id") else None,
        "project_id": hit.get("project_id") or "",
        "name": hit.get("name") or "",
        "version": hit.get("version"),
        "material": hit.get("material") or "",
        "machine": hit.get("machine") or "",
        "parameters": parameters,
        "primitives": primitives,
        "parts": parts,
        "editable": bool(primitives),
        "assembly_result": assembly_result,
        "assembled_preview_svg": assembly.get("assembled_preview_svg") if assembly else None,
        "look_again": (
            []
            if primitives
            else ["Bu SVG'de kayıtlı parametrik parça yok. create_design ile üretince tıklayarak uzatabilir, delik veya pencere ekleyebilirsin."]
        ),
    }


def apply_revision(body: dict[str, Any]) -> dict[str, Any]:
    primitives = [dict(p) for p in (body.get("primitives") or []) if isinstance(p, dict)]
    parameters = dict(body.get("parameters") or {}) if isinstance(body.get("parameters"), dict) else {}
    if not primitives and body.get("file_id"):
        hit = project_by_file(str(body.get("file_id") or ""))
        if hit:
            primitives = [dict(p) for p in (hit.get("primitives") or []) if isinstance(p, dict)]
            body.setdefault("project_id", hit.get("project_id"))
            parameters = {**dict(hit.get("parameters") or {}), **parameters}
            if hit.get("material") and not body.get("material"):
                body["material"] = hit.get("material")
    if not primitives:
        history = project_history(str(body.get("project_id") or ""))
        versions = (history or {}).get("versions") or []
        for ver in reversed(versions):
            if isinstance(ver.get("primitives"), list) and ver["primitives"]:
                primitives = [dict(p) for p in ver["primitives"] if isinstance(p, dict)]
                break
    if not primitives:
        raise ValueError("no primitives on this project version — generate first")
    if body.get("material"):
        parameters["material"] = str(body["material"])
    op = str(body.get("op") or body.get("edit") or "").strip().lower()
    mm = body.get("mm")
    try:
        delta = float(mm) if mm not in (None, "") else 0.0
    except (TypeError, ValueError) as exc:
        raise ValueError("mm must be a number") from exc
    if op in {"set_joint_clearance", "set_clearance", "clearance"}:
        if not -0.15 <= delta <= 0.40:
            raise ValueError("joint clearance must be between -0.15 and 0.40 mm")
        parameters["joint_clearance_mm"] = round(delta, 3)
        draft = save_version(
            {
                **parameters,
                "project_id": str(body.get("project_id") or ""),
                "project": str(body.get("project") or "revision"),
                "machine": body.get("machine"),
            },
            {
                "primitives": primitives,
                "final_status": "DRAFT",
                "speak": f"revision joint clearance {delta:.3f} mm",
            },
        )
        return {
            "success": True,
            "primitives": primitives,
            "parameters": parameters,
            "project": draft,
            "next_tool": "create_design",
            "look_again": ["Joint clearance is applied at the next Boxes.py compile. Previous version is kept."],
        }
    if op == "set_material":
        parameters["material"] = str(body.get("material") or "")
        return {
            "success": True,
            "primitives": primitives,
            "parameters": parameters,
            "next_tool": "create_design",
            "look_again": ["Call create_design with these primitives and the new material. Old version stays."],
        }
    idx, part = _find_part(primitives, str(body.get("part") or body.get("label") or "0"))
    dim = str(body.get("dim") or "x").strip().lower()
    if dim not in {"x", "y", "h", "w", "d"}:
        dim = "x"
    if op in {"extend", "grow"}:
        part[dim] = float(part.get(dim) or part.get("w") or 0) + delta
    elif op == "set_hole":
        holes = list(part.get("holes") or [])
        holes.append({"d": delta, "note": "human edit"})
        part["holes"] = holes
        part["hole"] = delta
    elif op == "add_window":
        cutouts = list(part.get("cutouts") or part.get("windows") or [])
        cutouts.append({"type": "window", "w": max(8.0, delta), "h": max(8.0, delta * 0.7)})
        part["cutouts"] = cutouts
    else:
        raise ValueError("op must be extend|set_hole|add_window|set_material")
    primitives[idx] = part
    draft = save_version(
        {
            **parameters,
            "project_id": str(body.get("project_id") or ""),
            "project": str(body.get("project") or "revision"),
            "machine": body.get("machine"),
            "material": body.get("material"),
        },
        {
            "primitives": primitives,
            "final_status": "DRAFT",
            "speak": f"revision {op} {part.get('label') or idx}",
        },
    )
    return {
        "success": True,
        "primitives": primitives,
        "parameters": parameters,
        "project": draft,
        "next_tool": "create_design",
        "next_arguments": {"primitives": primitives, "parameters": {"project_id": (draft or {}).get("project_id")}},
        "look_again": ["Previous version is kept. Call create_design to compile this revision."],
    }


def estimate_cost(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from bom import _area_m2

    payload = body or {}
    # Prompt / LLM API quote (no network call)
    if payload.get("prompt") or payload.get("ai_prompt") or payload.get("kind") in {"ai", "llm", "prompt"}:
        return estimate_ai_prompt_cost(payload)
    primitives = [p for p in (payload.get("primitives") or []) if isinstance(p, dict)]
    material = resolve_material(payload)
    machine = resolve_machine(payload)
    area_m2 = _area_m2(primitives, float(material.get("thickness") or 3.0)) if primitives else 0.0
    sheet_m2 = (float(material.get("sheet_w") or machine.get("bed_w") or 1500) * float(material.get("sheet_h") or machine.get("bed_h") or 3000)) / 1_000_000.0
    parts = sum(max(1, int(p.get("count") or p.get("n") or 1)) for p in primitives) if primitives else 0
    sheets = 1
    if sheet_m2 and area_m2:
        sheets = max(1, int((area_m2 / max(sheet_m2 * 0.72, 0.001)) + 0.999))
    nesting = payload.get("nesting") if isinstance(payload.get("nesting"), dict) else {}
    if nesting.get("sheets"):
        try:
            sheets = max(sheets, int(nesting["sheets"]))
        except (TypeError, ValueError):
            pass
    return {
        "success": True,
        "kind": "material",
        "parts": parts,
        "area_m2": area_m2,
        "sheet_m2": round(sheet_m2, 4),
        "sheets": sheets,
        "utilization": round((area_m2 / (sheets * sheet_m2)), 3) if sheets and sheet_m2 else 0,
        "cut_length_mm": nesting.get("cut_length_mm"),
        "material": material.get("name"),
        "machine": machine.get("name"),
        "note": "Estimate from part area and sheet size. Not a quote.",
    }


def estimate_ai_prompt_cost(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dry-run LLM $ estimate for a prompt. Studio AI local path is $0 API."""
    from ai_cost import estimate_prompt_cost, list_models
    from plans import gate_job

    payload = body or {}
    prompt = str(payload.get("prompt") or payload.get("ai_prompt") or payload.get("text") or "")
    model = str(payload.get("model") or "gpt-4o-mini")
    mode = str(payload.get("mode") or "mcp_thin")
    # Studio AI tab uses in-process planner — surface both quotes
    local = estimate_prompt_cost(
        prompt,
        model=model,
        mode="studio_local",
        photo=bool(payload.get("has_photo") or payload.get("photo")),
    )
    mcp = estimate_prompt_cost(
        prompt,
        model=model,
        mode=mode if mode != "studio_local" else "mcp_thin",
        photo=bool(payload.get("has_photo") or payload.get("photo")),
    )
    gate = gate_job("platform_ai")
    return {
        "success": True,
        "kind": "ai_prompt",
        "prompt_preview": prompt[:240],
        "studio_ai": {
            **local,
            "quota": {"used": gate.get("used"), "limit": gate.get("quota"), "plan": gate.get("plan_name")},
            "note": "Stüdyo AI şu an yerel plan_laser_job kullanır → harici API $0. Aylık tasarım kotasına 1 sayılabilir.",
        },
        "mcp_host_ai": mcp,
        "models": list_models(),
        "recommendation": (
            "Basit kutu/kapak/bölücü → parametrik Stüdyo ($0 API). "
            "Karmaşık maket / serbest form → MCP ile Claude/ChatGPT; önce mcp_host_ai.usd.total’a bak."
        ),
        "look_again": list(mcp.get("look_again") or []),
    }


def make_this(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from job_planner import plan_laser_job

    payload = body or {}
    plan = plan_laser_job(
        str(payload.get("name") or payload.get("user_request") or payload.get("what_you_see") or "maket"),
        what_you_see=str(payload.get("what_you_see") or ""),
        has_photo=bool(payload.get("has_photo") or payload.get("photo")),
    )
    args = plan.get("next_arguments") if isinstance(plan.get("next_arguments"), dict) else {}
    primitives = args.get("primitives") if isinstance(args.get("primitives"), list) else []
    structure: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for part in primitives:
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "part")
        counts[kind] = counts.get(kind, 0) + max(1, int(part.get("count") or 1))
        structure.append(
            {
                "type": kind,
                "label": part.get("label") or kind,
                "x": part.get("x") or part.get("w"),
                "y": part.get("y") or part.get("h"),
                "h": part.get("h"),
            }
        )
    return {
        "success": True,
        "needs_confirm": True,
        "structure": structure,
        "counts": counts,
        "plan": {k: plan.get(k) for k in ("summary", "next_tool", "method", "look_again") if k in plan},
        "next_tool": "create_design",
        "next_arguments": args,
        "look_again": [
            "Confirm the part list, then call create_design. Photo is not traced into 3D.",
            str(plan.get("look_again") or ""),
        ],
    }


def approve_prototype(body: dict[str, Any]) -> dict[str, Any]:
    pid = str(body.get("project_id") or "")
    if not pid:
        raise ValueError("project_id required")
    from projects import approve_latest
    approved = approve_latest(pid)
    return {
        "success": True,
        "project_id": pid,
        "version": approved.get("version"),
        "status": "approved prototype",
        "look_again": ["Approved prototype only. Production still needs human physical tests."],
    }


def create_studio_box(body: dict[str, Any] | None = None, *, public_base_url: str | None = None) -> dict[str, Any]:
    """Parametric finger-joint box for the platform 3D studio. No AI cost.

    body.preview=true → fast path: compile + 3D panels only (no DXF/project persist).
    Use for live lid/dimension scrubbing; call without preview to export.
    """
    from assembly_result import build as build_assembly_result
    from assembly_result import panels_for_viewer
    from plans import gate_job
    from studio_box import build_studio_box
    from toolbox import render_toolbox
    import payas_cad

    gate = gate_job("design")
    if not gate.get("ok"):
        return gate
    payload = body or {}
    try:
        built = build_studio_box(payload)
    except (TypeError, ValueError) as exc:
        return {
            "success": False,
            "ok": False,
            "look_again": [str(exc)],
            "plan": gate,
        }

    preview = bool(payload.get("preview") or payload.get("fast"))
    if preview:
        try:
            params = dict(built["parameters"] or {})
            params["studio_preview"] = True
            rendered = render_toolbox(built["primitives"], params)
        except (TypeError, ValueError) as exc:
            return {"success": False, "ok": False, "look_again": [str(exc)], "plan": gate}
        assembly = rendered.get("assembly") if isinstance(rendered.get("assembly"), dict) else {}
        thickness = float((built.get("parameters") or {}).get("thickness") or 3)
        result_blob = build_assembly_result(
            {**assembly, "thickness": thickness},
            file_id="studio-preview.svg",
            project_id="studio-preview",
        )
        viewer = panels_for_viewer(result_blob)
        return {
            "success": bool(viewer.get("success")),
            "preview": True,
            "file_id": None,
            "assembly": viewer,
            "summary": built.get("summary"),
            "look_again": [
                "Live preview — SVG/DXF not saved yet. Click Yeniden üret to export.",
                "3D view is a nominal digital assembly. Measure kerf and dry-fit before production.",
            ],
            "plan": gate,
        }

    result = payas_cad.create_design(
        primitives=built["primitives"],
        parameters=built["parameters"],
        public_base_url=public_base_url or "",
    )
    viewer = panels_for_viewer(result.get("assembly_result"))
    return {
        "success": bool(result.get("success")),
        "file_id": result.get("file_id"),
        "svg_url": result.get("svg_url"),
        "dxf_id": result.get("dxf_id"),
        "dxf_url": result.get("dxf_url"),
        "project": result.get("project"),
        "final_status": result.get("final_status"),
        "speak": result.get("speak"),
        "assembly": viewer,
        "summary": built.get("summary"),
        "look_again": list(result.get("look_again") or [])
        + ["3D view is a nominal digital assembly. Measure kerf and dry-fit before production."],
        "plan": gate,
    }


def create_studio_stl(body: dict[str, Any] | None = None, *, public_base_url: str | None = None) -> dict[str, Any]:
    """Extrude a generated SVG (mm) to STL. XY scale comes from the SVG — never invented."""
    from boxes_adapter import OUTPUT_DIR, _file_url, _safe_output_file
    from plans import gate_job
    from svg_to_stl import svg_bytes_to_stl

    gate = gate_job("design")
    if not gate.get("ok"):
        return gate
    payload = body or {}
    file_id = str(payload.get("file_id") or "").strip()
    if not file_id:
        return {"success": False, "ok": False, "look_again": ["file_id required"], "plan": gate}
    try:
        path = _safe_output_file(file_id)
        svg_bytes = path.read_bytes()
    except (OSError, ValueError):
        return {"success": False, "ok": False, "look_again": ["SVG not found for STL export"], "plan": gate}
    height = payload.get("height_mm") or payload.get("extrude_mm") or payload.get("thickness")
    try:
        stl = svg_bytes_to_stl(
            svg_bytes,
            height_mm=float(height) if height not in (None, "") else None,
            ai_hint=str(payload.get("prompt") or payload.get("ai_hint") or ""),
            default_thickness_mm=float(payload.get("default_thickness") or 3),
        )
    except (TypeError, ValueError) as exc:
        return {"success": False, "ok": False, "look_again": [str(exc)], "plan": gate}
    stl_id = path.stem + ".stl"
    out = OUTPUT_DIR / stl_id
    out.write_bytes(stl["stl_bytes"])
    base = public_base_url or ""
    return {
        "success": True,
        "file_id": path.name,
        "stl_id": stl_id,
        "stl_url": _file_url(base, stl_id) if base else f"/files/{stl_id}",
        "units": "mm",
        "scale": stl.get("scale"),
        "height_mm": stl.get("height_mm"),
        "part_count": stl.get("part_count"),
        "triangle_count": stl.get("triangle_count"),
        "ai": stl.get("ai"),
        "look_again": [
            "STL XY comes from SVG millimetres. Physical print shrink/tolerance is NOT_VERIFIED.",
            "AI only suggests extrusion height when you ask; it does not invent width/depth.",
        ],
        "plan": gate,
    }


def _studio_ai_result(result: dict[str, Any], *, cost: dict[str, Any] | None = None, extra_look: list[str] | None = None, plan: dict[str, Any] | None = None, plan_job: dict[str, Any] | None = None, source: str = "prompt") -> dict[str, Any]:
    from assembly_result import panels_for_viewer

    viewer = panels_for_viewer(result.get("assembly_result"))
    looks = list(result.get("look_again") or [])
    looks.extend(extra_look or [])
    return {
        "success": bool(result.get("success")),
        "file_id": result.get("file_id"),
        "svg_url": result.get("svg_url"),
        "dxf_id": result.get("dxf_id"),
        "dxf_url": result.get("dxf_url"),
        "project": result.get("project"),
        "final_status": result.get("final_status"),
        "speak": result.get("speak"),
        "source": source,
        "plan_job": plan_job,
        "assembly": viewer,
        "cost": cost,
        "look_again": looks,
        "plan": plan,
    }


def create_studio_ai(body: dict[str, Any] | None = None, *, public_base_url: str | None = None) -> dict[str, Any]:
    """Studio AI: prompt and/or uploaded photo|svg|plt|dxf → 3D panels. Gated by platform_ai + quota."""
    from job_planner import plan_laser_job
    from plans import entitled, gate_job
    import payas_cad

    gate = gate_job("platform_ai")
    if not gate.get("ok"):
        return gate
    if not entitled("platform_ai"):
        return {
            "success": True,
            "ok": False,
            "look_again": ["Platform AI is on Maker/Pro. Use parametric box for free, or upgrade."],
            "plan": gate,
        }
    payload = body or {}
    request = str(payload.get("prompt") or payload.get("name") or payload.get("what_you_see") or "").strip()
    kind = str(payload.get("file_kind") or payload.get("attach_kind") or "").strip().lower()
    has_image = bool(payload.get("image_base64") or payload.get("photo_base64"))
    has_svg = bool(payload.get("svg") or payload.get("svg_text") or (kind == "svg" and payload.get("file_text")))
    has_plt = bool(payload.get("plt") or payload.get("plt_base64") or (kind == "plt" and (payload.get("file_text") or payload.get("file_base64"))))
    has_dxf = bool(payload.get("dxf") or payload.get("dxf_text") or (kind == "dxf" and payload.get("file_text")))
    if not request and not (has_image or has_svg or has_plt or has_dxf):
        return {
            "success": True,
            "ok": False,
            "look_again": ["Write a prompt and/or upload a photo, SVG, PLT or DXF."],
            "plan": gate,
        }

    design_gate = gate_job("design")
    if not design_gate.get("ok"):
        return design_gate

    base = public_base_url or ""
    thickness = payload.get("thickness")
    parameters: dict[str, Any] = {
        "project": (request or "studio-upload")[:48],
        "what_you_see": request or "studio upload",
    }
    if thickness not in (None, ""):
        parameters["thickness"] = float(thickness)
    if payload.get("material"):
        parameters["material"] = payload["material"]
    if payload.get("machine"):
        parameters["machine"] = payload["machine"]

    cost = estimate_ai_prompt_cost(
        {
            "prompt": request or f"upload:{kind or 'file'}",
            "model": payload.get("model") or "gpt-4o-mini",
            "has_photo": has_image,
            "mode": "studio_local",
        }
    )

    # --- Photo / image → trace ---
    if has_image:
        photo_gate = gate_job("photo")
        if not photo_gate.get("ok"):
            return {**photo_gate, "ok": False, "success": True}
        image_b64 = str(payload.get("image_base64") or payload.get("photo_base64") or "")
        # strip data-url prefix if present
        if "," in image_b64 and image_b64.strip().lower().startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]
        result = payas_cad.create_from_reference(
            image_base64=image_b64,
            width_mm=float(payload.get("width_mm") or 200),
            height_mm=float(payload["height_mm"]) if payload.get("height_mm") not in (None, "", 0, "0") else None,
            style=str(payload.get("style") or "cut_and_etch"),
            threshold=int(payload.get("threshold") or 0),
            layout=str(payload.get("layout") or "trace"),
            format="svg",
            parameters=parameters,
            public_base_url=base,
        )
        return _studio_ai_result(
            result,
            cost=cost,
            plan=design_gate,
            source="photo",
            extra_look=[
                "Photo was traced to CUT/ENGRAVE — not a parametric 3D box kit.",
                "Digital only. Measure kerf before production.",
            ],
        )

    # --- SVG import ---
    if has_svg:
        svg_text = str(payload.get("svg") or payload.get("svg_text") or payload.get("file_text") or "")
        result = payas_cad.create_design(svg=svg_text, parameters=parameters, public_base_url=base)
        return _studio_ai_result(
            result,
            cost=cost,
            plan=design_gate,
            source="svg",
            extra_look=["SVG imported as design source. Joints are not invented from paths."],
        )

    # --- PLT / HP-GL ---
    if has_plt:
        plt_text = payload.get("plt") or payload.get("file_text")
        plt_b64 = payload.get("plt_base64") or (payload.get("file_base64") if kind == "plt" else None)
        result = payas_cad.create_design(
            plt=str(plt_text) if plt_text else None,
            plt_base64=str(plt_b64) if plt_b64 else None,
            parameters=parameters,
            public_base_url=base,
        )
        return _studio_ai_result(
            result,
            cost=cost,
            plan=design_gate,
            source="plt",
            extra_look=["PLT/HP-GL imported. Pen mapping from profile; physical PASS not claimed."],
        )

    # --- DXF → SVG → design ---
    if has_dxf:
        from dxf_import import dxf_to_svg

        dxf_text = str(payload.get("dxf") or payload.get("dxf_text") or payload.get("file_text") or "")
        try:
            svg_text = dxf_to_svg(dxf_text)
        except Exception as exc:
            return {"success": False, "ok": False, "look_again": [f"DXF import failed: {exc}"], "plan": design_gate}
        result = payas_cad.create_design(svg=svg_text, parameters=parameters, public_base_url=base)
        return _studio_ai_result(
            result,
            cost=cost,
            plan=design_gate,
            source="dxf",
            extra_look=["DXF converted to SVG millimetres. Layer ops preserved when named CUT/ENGRAVE."],
        )

    # --- Text prompt → local planner primitives ---
    plan = plan_laser_job(
        request,
        what_you_see=str(payload.get("what_you_see") or request),
        has_photo=False,
    )
    args = plan.get("next_arguments") if isinstance(plan.get("next_arguments"), dict) else {}
    primitives = args.get("primitives") if isinstance(args.get("primitives"), list) else []
    if not primitives:
        return {
            "success": True,
            "ok": False,
            "plan_job": plan,
            "cost": cost,
            "look_again": list(plan.get("look_again") or [])
            or ["Could not draft primitives. Try a simpler box description, or upload SVG/PLT/DXF/photo."],
            "plan": gate,
        }
    merged = dict(args.get("parameters") or {}) if isinstance(args.get("parameters"), dict) else {}
    merged.update(parameters)
    result = payas_cad.create_design(
        primitives=primitives,
        parameters=merged,
        public_base_url=base,
    )
    return _studio_ai_result(
        result,
        cost=cost,
        plan=design_gate,
        plan_job={k: plan.get(k) for k in ("summary", "next_tool", "method", "look_again") if k in plan},
        source="prompt",
        extra_look=[
            "AI draft is digital only. Confirm joints and dry-fit before cutting.",
            "Studio AI used the local planner — no external LLM API charge from LaserMCP.",
        ],
    )


def workshop_action(action: str, body: dict[str, Any], principal: dict[str, Any] | None = None) -> dict[str, Any]:
    verb = str(action or "").strip().lower()
    if verb in {"onboard", "onboarding"}:
        if any(k in body for k in ("machine", "machine_id", "material", "brand", "model", "bed_w", "thickness", "step", "batch_id")):
            return save_onboarding(body, principal)
        return get_onboarding(principal)
    if verb in {"catalog", "library"}:
        return public_catalog()
    if verb in {"machine", "machines"}:
        return {"success": True, "machine": upsert_machine(body, owner=_owner(principal))}
    if verb in {"batch", "batches"}:
        if body:
            return {"success": True, "batch": upsert_batch(body, owner=_owner(principal))}
        from catalog import batches

        return {"success": True, "batches": batches()}
    if verb in {"feedback", "fit"}:
        if body.get("fit") or body.get("result"):
            return record_feedback(body, principal)
        return {"success": True, "rows": list_feedback(str(body.get("project_id") or ""))}
    if verb in {"preflight", "pre_flight", "check"}:
        return preflight(body)
    if verb in {"editor", "open"}:
        return editor_context(str(body.get("file_id") or body.get("name") or ""))
    if verb in {"revise", "edit"}:
        return apply_revision(body)
    if verb in {"cost", "quote"}:
        return estimate_cost(body)
    if verb in {"make", "make_this", "structure"}:
        return make_this(body)
    if verb in {"box", "studio_box", "parametric"}:
        return create_studio_box(body)
    if verb in {"ai", "studio_ai", "design_ai"}:
        return create_studio_ai(body)
    if verb in {"approve"}:
        return approve_prototype(body)
    if verb in {"activate", "redeem"}:
        return redeem_activation(str(body.get("code") or body.get("name") or ""), owner=_owner(principal))
    if verb in {"mint", "codes"}:
        from supabase_auth import can_mint_activation

        if not can_mint_activation(principal):
            return {"success": True, "look_again": ["Dealers mint activation codes."]}
        return {"success": True, "activation": mint_activation(body, owner=_owner(principal))}
    if verb in {"projects", "project"}:
        pid = str(body.get("project_id") or "")
        if pid:
            hit = project_history(pid)
            return {"success": True, "project": hit} if hit else {"success": True, "look_again": [f"No project {pid}."], "projects": list_projects()}
        return {"success": True, "projects": list_projects()}
    return {
        "success": True,
        "look_again": [
            "action=onboard|catalog|machines|batch|feedback|preflight|editor|revise|cost|make_this|box|ai|approve|activate|mint"
        ],
    }
