"""Workshop loop: onboard → cut → human feedback → version. Never invents a physical PASS."""

from __future__ import annotations

import re
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
    from ai_cost import MODEL_PRICES
    from llm_guard import access, allowed_models, default_model
    from llm_keys import any_configured, list_status
    from plans import gate_job

    payload = body or {}
    prompt = str(payload.get("prompt") or payload.get("ai_prompt") or payload.get("text") or "")
    # The picked model prices the MCP-host column; Studio itself only calls an allowed one.
    model = str(payload.get("model") or default_model())
    mode = str(payload.get("mode") or "mcp_thin")
    workshop_llm = any_configured()
    llm_access = access(payload.get("model"))
    studio_model = llm_access["model"]
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
    workshop = estimate_prompt_cost(
        prompt,
        model=studio_model,
        mode="mcp_thin",
        photo=bool(payload.get("has_photo") or payload.get("photo")),
    )
    gate = gate_job("platform_ai")
    provider = llm_access["provider"]
    own_models: list[dict[str, str]] = []
    if llm_access.get("own_key"):
        from llm_keys import user_providers

        mine = user_providers(str(llm_access.get("key_owner") or ""))
        own_models = [
            {"id": mid, "label": str(row.get("label") or mid)}
            for mid, row in MODEL_PRICES.items()
            # "gpt-5" is a legacy alias served by an older model, and the tuned model lives in
            # the workshop's provider account: neither is offered to a caller's own key.
            if row.get("provider") in mine and mid not in {"gpt-5", "lasermcp-tuned"}
        ]
        # Strongest first: the people who connect a key want the top model.
        own_models.sort(key=lambda m: -float(MODEL_PRICES[m["id"]]["output_per_mtok"]))
    if llm_access.get("own_key"):
        note = (
            f"Kendi {provider} anahtarın bağlı → Stüdyo AI {studio_model} modelini senin anahtarınla çağırır; "
            "fatura senin sağlayıcı hesabına gider. Günlük site sınırı uygulanmaz."
        )
    elif llm_access["allow"]:
        note = (
            f"Atölye {provider} anahtarı kayıtlı → Stüdyo AI {studio_model} modeline çağrı yapar; fatura sağlayıcıya gider "
            f"(LaserMCP lzr_ değil). Bir adresten günde en çok {llm_access['daily_per_ip']} AI isteği."
        )
    elif llm_access["reason"] == "signin":
        note = "AI modeli yalnız onaylı hesapla giriş yapınca çalışır. Misafir istekleri yerel planner ile üretilir ($0)."
    elif llm_access["reason"] == "pending":
        note = "Hesabın onaylanınca AI modeli açılır. O zamana kadar yerel planner kullanılır ($0)."
    elif llm_access["reason"] == "global_limit":
        note = "AI modeli bugünlük kapalı (günlük sınır). Yerel planner kullanılır ($0)."
    else:
        note = "AI modeli şu an kapalı; Stüdyo AI yerel planner ile üretir ($0). Anahtar eklemen gerekmez."
    return {
        "success": True,
        "kind": "ai_prompt",
        "prompt_preview": prompt[:240],
        # This quote is open to guests: say which providers have a key, nothing about the key itself.
        "workshop_llm_keys": [{"provider": row["provider"], "configured": row["configured"]} for row in list_status()],
        "studio_ai": {
            **(workshop if llm_access["allow"] else local),
            "quota": {"used": gate.get("used"), "limit": gate.get("quota"), "plan": gate.get("plan_name")},
            "uses_workshop_key": workshop_llm,
            "provider": provider,
            "note": note,
        },
        "llm_access": {
            "eligible": llm_access["allow"],
            "reason": llm_access["reason"],
            "model": studio_model,
            "provider": provider,
            "daily_per_ip": llm_access["daily_per_ip"],
            "own_key": bool(llm_access.get("own_key")),
        },
        "studio_models": (
            {"default": studio_model, "allowed": own_models, "own_key": True}
            if own_models
            else {
                "default": default_model(),
                "allowed": [{"id": mid, "label": (MODEL_PRICES.get(mid) or {}).get("label") or mid} for mid in allowed_models()],
            }
        ),
        "mcp_host_ai": mcp,
        "models": list_models(),
        "recommendation": (
            "Basit kutu/kapak/süs → parametrik Stüdyo / Süs ($0 API). "
            "Serbest prompt → Stüdyo AI (modeli LaserMCP sağlar, anahtar gerekmez) veya MCP host."
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


def create_studio_maker(body: dict[str, Any] | None = None, *, public_base_url: str | None = None) -> dict[str, Any]:
    """Parametric makers (name ornament, birdhouse, christmas). Explicitly NOT AI."""
    from assembly_result import panels_for_viewer
    from plans import gate_job
    from studio_makers import MAKERS, build_maker, list_makers
    import payas_cad
    from boxes_adapter import generate_svg

    payload = body or {}
    if str(payload.get("action") or "").lower() in {"list", "catalog"}:
        return {"success": True, "ai": False, "makers": list_makers()}
    gate = gate_job("design")
    if not gate.get("ok"):
        return gate
    kind = str(payload.get("maker") or payload.get("kind") or payload.get("type") or "").strip()
    if not kind:
        return {
            "success": False,
            "ok": False,
            "ai": False,
            "makers": list_makers(),
            "look_again": ["maker required: name_ornament | birdhouse | christmas | flexible_box | named_gift"],
            "plan": gate,
        }
    try:
        built = build_maker(kind, payload)
    except (TypeError, ValueError) as exc:
        return {"success": False, "ok": False, "ai": False, "look_again": [str(exc)], "plan": gate}

    base = public_base_url or ""
    try:
        if built.get("mode") == "generator":
            result = generate_svg(
                str(built["generator"]),
                built.get("parameters") or {},
                public_base_url=base,
                extra={
                    "product": built["summary"]["maker"],
                    "title": MAKERS.get(built["summary"]["maker"], {}).get("label_tr")
                    or built["summary"]["maker"],
                    "method": "parametric_maker",
                    "ai": False,
                },
            )
            if isinstance(result.get("assembly_result"), dict):
                viewer = panels_for_viewer(result.get("assembly_result"))
            else:
                viewer = {
                    "success": True,
                    "panels": [],
                    "thickness_mm": float((built.get("parameters") or {}).get("thickness") or 3),
                    "note": "Generator nest sheet — SVG/DXF ready; 3D assembly N/A for this maker.",
                    "validation_state": "DIGITAL_PROTOTYPE",
                }
        else:
            result = payas_cad.create_design(
                primitives=built.get("primitives") or [],
                parameters=built.get("parameters") or {},
                public_base_url=base,
            )
            viewer = panels_for_viewer(result.get("assembly_result"))
    except Exception as exc:
        return {
            "success": False,
            "ok": False,
            "ai": False,
            "maker": built.get("summary", {}).get("maker") or kind,
            "look_again": [str(exc)],
            "summary": built.get("summary"),
            "plan": gate,
        }
    final_status = str(result.get("final_status") or "BLOCKED")
    export_ok = final_status not in {"BLOCKED", "FAIL"} and bool(result.get("success"))
    # Guests/pending still get 3D; downloads require an approved account (same as box).
    principal = None
    account_ok = False
    try:
        from keys import current_auth
        from supabase_auth import account_is_approved

        principal = current_auth.get()
        account_ok = bool(principal) and account_is_approved(principal)
    except Exception:
        account_ok = False
    if export_ok and not account_ok:
        export_ok = False
        looks_gate = (
            ["Sign in to download maker SVG/DXF. 3D preview stays open for guests."]
            if not principal
            else ["Account pending approval — maker preview open; download unlocks after approval."]
        )
    else:
        looks_gate = []
    file_id = result.get("file_id") if export_ok else None
    studio_url = f"{base.rstrip('/')}/studio?file={file_id}" if base and file_id else (f"/studio?file={file_id}" if file_id else None)
    looks = list(looks_gate) + list(result.get("look_again") or []) + [
        "Parametric maker — no AI / no LLM.",
        "Digital prototype only. Measure thickness and dry-fit before production.",
    ]
    if final_status == "BLOCKED":
        looks.insert(0, "BLOCKED — SVG/DXF not authorized (Final Gate). Fix assembly/connections or choose another maker.")
    if studio_url:
        looks.append(f"Open in Studio 3D: {studio_url}")
    return {
        "success": bool(result.get("success")),
        "ai": False,
        "maker": built.get("summary", {}).get("maker") or kind,
        "export_allowed": export_ok,
        "file_id": file_id,
        "svg_url": result.get("svg_url") if export_ok else None,
        "dxf_id": result.get("dxf_id") if export_ok else None,
        "dxf_url": result.get("dxf_url") if export_ok else None,
        "studio_url": studio_url,
        "project": result.get("project"),
        "final_status": final_status,
        "production_export": "BLOCKED" if not export_ok else (result.get("production_export") or "BLOCKED"),
        "scorecard": result.get("scorecard") or {"final_gate": final_status, "physical_fit": "NOT_VERIFIED"},
        "assembly": viewer,
        "summary": built.get("summary"),
        "look_again": looks,
        "plan": gate,
        "gate_skipped": False,
    }


def create_studio_coupon(body: dict[str, Any] | None = None, *, public_base_url: str | None = None) -> dict[str, Any]:
    """Kerf / FingerJoint dry-fit coupon (100 mm bar). Human measurement required for PASS."""
    from plans import gate_job
    import payas_cad

    gate = gate_job("design")
    if not gate.get("ok"):
        return gate
    payload = body or {}
    thickness = float(payload.get("thickness") or 3)
    params = {
        "thickness": thickness,
        "project": str(payload.get("project") or payload.get("name") or "kerf-coupon"),
        "material": str(payload.get("material") or "poplar_3mm"),
        "machine": str(payload.get("machine") or "payas_workshop"),
        "what_you_see": "kerf calibration coupon — measure the 100 mm bar after cutting",
    }
    if payload.get("burn") not in (None, ""):
        try:
            params["burn"] = float(payload.get("burn"))
        except (TypeError, ValueError):
            pass
    primitives = [{"type": "coupon", "label": "kerf-coupon", "x": float(payload.get("x") or 40)}]
    result = payas_cad.create_design(
        primitives=primitives,
        parameters=params,
        public_base_url=public_base_url or "",
    )
    looks = list(result.get("look_again") or [])
    looks.append("Cut the coupon, measure the 100 mm bar, enter measured_bar_mm in Studio Kalibrasyon.")
    looks.append("Software will not invent kerf. Physical fit stays NOT_VERIFIED until dry-fit.")
    return {
        "success": bool(result.get("success")),
        "file_id": result.get("file_id"),
        "svg_url": result.get("svg_url"),
        "dxf_id": result.get("dxf_id"),
        "dxf_url": result.get("dxf_url"),
        "final_status": result.get("final_status"),
        "export_allowed": str(result.get("final_status") or "") not in {"BLOCKED", "FAIL"},
        "speak": result.get("speak") or "Kerf coupon ready.",
        "look_again": looks,
        "plan": gate,
        "coupon": True,
        "nominal_bar_mm": 100,
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

    payload = body or {}
    preview = bool(payload.get("preview") or payload.get("fast"))
    gate = gate_job("design")
    # A live preview writes no file and spends no quota, so a full monthly quota must not
    # freeze the 3D view; only the gated save stops here.
    if not gate.get("ok") and not preview:
        return gate
    try:
        built = build_studio_box(payload)
    except (TypeError, ValueError) as exc:
        return {
            "success": False,
            "ok": False,
            "look_again": [str(exc)],
            "plan": gate,
        }

    if not preview:
        # Guest/pending may preview freely; authorized download needs an approved account.
        try:
            from keys import current_auth
            from supabase_auth import account_is_approved

            principal = current_auth.get()
        except Exception:
            principal = None
        if not principal:
            return {
                "success": True,
                "ok": False,
                "export_allowed": False,
                "final_status": "BLOCKED",
                "look_again": ["Sign in to download SVG/DXF. Preview stays open for guests."],
                "plan": gate,
            }
        if not account_is_approved(principal):
            return {
                "success": True,
                "ok": False,
                "export_allowed": False,
                "final_status": "BLOCKED",
                "look_again": ["Account pending approval — design/preview stays open; download unlocks after approval."],
                "plan": gate,
                "assembly": None,
            }
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
        joints = (built.get("summary") or {}).get("joints") or {}
        guide = built.get("assembly_guide") or (built.get("summary") or {}).get("assembly_guide") or {}
        looks = [
            "PREVIEW_ONLY — Final Gate / nest skipped. Click «Kaydet ve indir» for gated SVG/DXF.",
            "3D view is a nominal digital assembly. Measure kerf and dry-fit before production.",
        ] + list(joints.get("warnings") or []) + list(joints.get("failures") or [])
        if guide.get("speak"):
            looks.append(str(guide["speak"]))
        joint_status = joints.get("status") or "NOT_VERIFIED"
        return {
            "success": bool(viewer.get("success")) and joint_status != "FAIL",
            "preview": True,
            "gate_skipped": True,
            "file_id": None,
            "assembly": viewer,
            "summary": built.get("summary"),
            "joints": joints,
            "assembly_guide": guide,
            "speak": guide.get("speak"),
            "final_status": "PREVIEW_ONLY",
            "authorized_output": [],
            "production_export": "BLOCKED",
            "scorecard": {
                "preview": "PASS" if viewer.get("success") else "FAIL",
                "joints": joint_status,
                "final_gate": "SKIPPED",
                "physical_fit": "NOT_VERIFIED",
            },
            "look_again": looks,
            "plan": gate,
        }

    joints = (built.get("summary") or {}).get("joints") or {}
    guide = built.get("assembly_guide") or (built.get("summary") or {}).get("assembly_guide") or {}
    if joints.get("status") == "FAIL":
        return {
            "success": False,
            "ok": False,
            "final_status": "BLOCKED",
            "authorized_output": [],
            "production_export": "BLOCKED",
            "summary": built.get("summary"),
            "joints": joints,
            "assembly_guide": guide,
            "scorecard": {"joints": "FAIL", "final_gate": "BLOCKED", "physical_fit": "NOT_VERIFIED"},
            "look_again": list(joints.get("failures") or []) + list(joints.get("warnings") or []),
            "plan": gate,
        }

    # Optional nest gap from Studio Nest tab (mm) — applied on full compile only.
    params = dict(built["parameters"] or {})
    if payload.get("nest_gap_mm") not in (None, ""):
        try:
            params["nest_gap_mm"] = max(2.0, min(30.0, float(payload.get("nest_gap_mm"))))
        except (TypeError, ValueError):
            pass
    if payload.get("material"):
        params["material"] = str(payload.get("material"))
    if payload.get("machine"):
        params["machine"] = str(payload.get("machine"))

    result = payas_cad.create_design(
        primitives=built["primitives"],
        parameters=params,
        public_base_url=public_base_url or "",
    )
    viewer = panels_for_viewer(result.get("assembly_result"))
    looks = list(result.get("look_again") or []) + list(joints.get("warnings") or [])
    looks.append("3D view is a nominal digital assembly. Measure kerf and dry-fit before production.")
    looks.append(f"Kerf digital status: {joints.get('kerf_status')} (physical fit NOT_VERIFIED).")
    if guide.get("speak"):
        looks.append(str(guide["speak"]))
    file_id = result.get("file_id")
    base = (public_base_url or "").rstrip("/")
    speak = guide.get("speak") or result.get("speak")
    final_status = str(result.get("final_status") or "BLOCKED")
    export_ok = final_status not in {"BLOCKED", "FAIL"} and bool(result.get("success"))
    studio_url = None
    if export_ok and file_id:
        studio_url = f"{base}/studio?file={file_id}" if base else f"/studio?file={file_id}"
        looks.append(f"Open in Studio 3D: {studio_url}")
    elif final_status == "BLOCKED":
        looks.insert(0, "BLOCKED — SVG/DXF not authorized (Final Gate). Fix connections/assembly before download.")
    authorized = list(result.get("authorized_output") or []) if export_ok else []
    return {
        # Compile may succeed while Final Gate blocks export — UI shows 3D + locks downloads.
        "success": bool(result.get("success")),
        "export_allowed": export_ok,
        "file_id": file_id if export_ok else None,
        "svg_url": result.get("svg_url") if export_ok else None,
        "dxf_id": result.get("dxf_id") if export_ok else None,
        "dxf_url": result.get("dxf_url") if export_ok else None,
        "studio_url": studio_url,
        "project": result.get("project"),
        "final_status": final_status,
        "authorized_output": authorized,
        "production_export": "BLOCKED" if not export_ok else (result.get("production_export") or "BLOCKED"),
        "scorecard": result.get("scorecard") or {},
        "speak": speak,
        "assembly": viewer,
        "summary": built.get("summary"),
        "joints": joints,
        "assembly_guide": guide,
        "look_again": looks,
        "plan": gate,
        "gate_skipped": False,
        "nesting": result.get("nesting") or (result.get("extra") or {}).get("nesting"),
    }


def create_studio_pdf(body: dict[str, Any] | None = None, *, public_base_url: str | None = None) -> dict[str, Any]:
    """Digital control-print PDF. Does not claim kerf/fit PASS. Physical remains NOT_VERIFIED."""
    import base64

    from plans import gate_job
    from studio_pdf import create_studio_pdf as build_pdf

    gate = gate_job("design")
    if not gate.get("ok"):
        return gate
    payload = body or {}

    try:
        from keys import current_auth
        from supabase_auth import account_is_approved

        principal = current_auth.get()
    except Exception:
        principal = None
    if not principal:
        return {
            "success": True,
            "ok": False,
            "export_allowed": False,
            "look_again": ["Sign in to download the control PDF. Preview stays open for guests."],
            "plan": gate,
        }
    if not account_is_approved(principal):
        return {
            "success": True,
            "ok": False,
            "export_allowed": False,
            "look_again": ["Account pending approval — control PDF unlocks after approval."],
            "plan": gate,
        }

    nesting = payload.get("nesting") if isinstance(payload.get("nesting"), dict) else None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else None
    file_id = str(payload.get("file_id") or "").strip() or None

    # Rebuild summary from live box params when the client only sends form fields.
    if not summary and (payload.get("x") or payload.get("width")):
        try:
            from studio_box import build_studio_box

            summary = build_studio_box(payload).get("summary")
        except (TypeError, ValueError):
            summary = None

    built = build_pdf(nesting=nesting, summary=summary, file_id=file_id)
    pdf_bytes = built["pdf_bytes"]
    name = built["pdf_name"]
    return {
        "success": True,
        "export_allowed": True,
        "pdf_id": name,
        "pdf_name": name,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "note": built.get("note"),
        "physical": "NOT_VERIFIED",
        "look_again": [
            "Digital control print only — not a kerf or dry-fit PASS.",
            "Physical cut / fit remain NOT_VERIFIED until measured.",
        ],
        "plan": gate,
    }


def create_studio_stl(
    body: dict[str, Any] | None = None,
    *,
    public_base_url: str | None = None,
    svg_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Extrude a generated SVG (mm) to STL. XY scale comes from the SVG — never invented.

    ``svg_bytes`` lets the HTTP route pass a source it already authorized and read from
    durable storage; on serverless hosts the local output dir is per-instance.
    """
    import base64
    from pathlib import Path

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
    if svg_bytes is None:
        try:
            svg_bytes = _safe_output_file(file_id).read_bytes()
        except (OSError, ValueError):
            return {"success": False, "ok": False, "look_again": ["SVG not found for STL export"], "plan": gate}
    path = Path(Path(file_id).name)
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
    stl_bytes = stl["stl_bytes"]
    (OUTPUT_DIR / stl_id).write_bytes(stl_bytes)
    from persist.env import uses_supabase_app_db

    if uses_supabase_app_db():
        # Best effort so /files/<stl> works across instances; the inline bytes below always work.
        try:
            from persist.authz import PUBLIC_ORG_ID
            from persist.job import _org_id, _principal, persist_bytes

            persist_bytes(
                organization_id=_org_id(_principal()) or PUBLIC_ORG_ID,
                kind="stl",
                data=stl_bytes,
                mime_type="model/stl",
                source_file_id=stl_id,
                durable=True,
                name=stl_id,
            )
        except Exception:
            pass
    base = public_base_url or ""
    return {
        "success": True,
        "file_id": path.name,
        "stl_id": stl_id,
        "stl_base64": base64.b64encode(stl_bytes).decode("ascii"),
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


def _compose_ai_chat_prompt(prompt: str, payload: dict[str, Any]) -> str:
    """Fold Studio chat / prior gate text into the planner prompt for a retry turn."""
    base = str(prompt or "").strip()
    chunks: list[str] = []
    prior = payload.get("prior_look_again") or payload.get("block_reasons") or []
    if isinstance(prior, str) and prior.strip():
        prior = [prior.strip()]
    if isinstance(prior, list):
        reasons = [str(x).strip() for x in prior if str(x).strip()]
        if reasons:
            chunks.append("Previous design was BLOCKED. Fix these gate notes:\n- " + "\n- ".join(reasons[:12]))
    prior_status = str(payload.get("prior_status") or "").strip()
    if prior_status:
        chunks.append(f"Previous final_status: {prior_status}")
    messages = payload.get("messages") or payload.get("chat") or []
    if isinstance(messages, list) and messages:
        lines: list[str] = []
        for row in messages[-16:]:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "user").strip().lower() or "user"
            text = str(row.get("text") or row.get("content") or "").strip()
            if not text:
                continue
            label = "User" if role in {"user", "human"} else ("Assistant" if role in {"assistant", "ai", "system"} else role)
            lines.append(f"{label}: {text}")
        if lines:
            chunks.append("Studio chat so far:\n" + "\n".join(lines))
    if not chunks:
        return base
    head = base or "Revise the laser-cut design from the Studio chat."
    return head + "\n\n" + "\n\n".join(chunks)


def _studio_ai_result(result: dict[str, Any], *, cost: dict[str, Any] | None = None, extra_look: list[str] | None = None, plan: dict[str, Any] | None = None, plan_job: dict[str, Any] | None = None, source: str = "prompt", public_base_url: str | None = None, lead_look: str = "", repair: dict[str, Any] | None = None) -> dict[str, Any]:
    from assembly_result import panels_for_viewer

    viewer = panels_for_viewer(result.get("assembly_result"))
    looks = list(result.get("look_again") or [])
    looks.extend(extra_look or [])
    final_status = str(result.get("final_status") or "BLOCKED")
    export_ok = final_status not in {"BLOCKED", "FAIL"} and bool(result.get("success"))
    # BLOCKED drafts must not look like authorized downloads in Studio.
    file_id = result.get("file_id") if export_ok else None
    base = (public_base_url or "").rstrip("/")
    studio_url = f"{base}/studio?file={file_id}" if base and file_id else (f"/studio?file={file_id}" if file_id else None)
    info = dict(repair or {})
    note = _repair_note(info)
    if note:
        looks.insert(0, note)
    if final_status == "BLOCKED":
        looks.insert(0, "BLOCKED — SVG/DXF not authorized. Read the notes below, fix in chat, then retry.")
    if lead_look:
        # Why the paid model did not answer comes before the reviewer's notes, which can be long.
        looks.insert(0, lead_look)
    if studio_url:
        looks.append(f"Open in Studio 3D: {studio_url}")
    return {
        "success": bool(result.get("success")),
        "ok": export_ok,
        "export_allowed": export_ok,
        "file_id": file_id,
        "svg_url": result.get("svg_url") if export_ok else None,
        "dxf_id": result.get("dxf_id") if export_ok else None,
        "dxf_url": result.get("dxf_url") if export_ok else None,
        "studio_url": studio_url,
        "project": result.get("project"),
        "final_status": final_status,
        "authorized_output": list(result.get("authorized_output") or []) if export_ok else [],
        "production_export": "BLOCKED" if not export_ok else (result.get("production_export") or "BLOCKED"),
        "scorecard": result.get("scorecard"),
        "speak": result.get("speak"),
        "source": source,
        "plan_job": plan_job,
        "assembly": viewer,
        "cost": cost,
        "look_again": looks,
        "plan": plan,
        # Studio reads this to say "found N issues, fixed them" instead of showing a block.
        "auto_repair": {
            "attempted": int(info.get("attempted") or 0),
            "fixed": bool(info.get("fixed")),
            "issues": list(info.get("issues") or [])[:6],
        },
    }


def _chat_for_storage(messages: Any, limit: int = 20) -> list[dict[str, str]]:
    """Last user/assistant turns of the Studio AI chat, trimmed for a project version."""
    if not isinstance(messages, list):
        return []
    rows: list[dict[str, str]] = []
    for row in messages[-limit:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip().lower()
        text = str(row.get("text") or row.get("content") or "").strip()
        if role in {"user", "assistant"} and text:
            rows.append({"role": role, "text": text[:600]})
    return rows


def _draft_blocked(result: dict[str, Any]) -> bool:
    return not result.get("success") or str(result.get("final_status") or "BLOCKED") in {"BLOCKED", "FAIL"}


def _gate_issues(result: dict[str, Any], limit: int = 10) -> list[str]:
    """The reviewer's notes on a blocked draft, without the generic status banner lines."""
    rows = []
    for raw in result.get("look_again") or []:
        line = str(raw or "").strip()
        if line and not line.upper().startswith(("BLOCKED", "OPEN IN STUDIO")) and line not in rows:
            rows.append(line[:300])
    return rows[:limit]


_EDGE_NOTE = re.compile(r"^(?:female|male) edge (\S+)\.(bottom|right|top|left) \(", re.I)
_EDGE_INDEX = {"bottom": 0, "right": 1, "top": 2, "left": 3}


def _straighten_unmatched_edges(primitives: list[Any], notes: list[str]) -> list[Any] | None:
    """Free repair: a finger edge the gate says has no partner becomes a straight edge.

    Only panels named in the notes change, and only those edges. Returns None when no
    note applies. The caller recompiles and keeps the result only if the gate passes, so
    parts that are genuinely unconnected still fail and go on to the model.
    """
    wanted: dict[str, set[int]] = {}
    for note in notes:
        hit = _EDGE_NOTE.match(str(note))
        if hit:
            wanted.setdefault(hit.group(1).lower(), set()).add(_EDGE_INDEX[hit.group(2).lower()])
    if not wanted:
        return None
    changed = False
    out: list[Any] = []
    for part in primitives:
        label = str((part or {}).get("label") or "").lower() if isinstance(part, dict) else ""
        edges = str(part.get("edges") or "") if isinstance(part, dict) else ""
        if label in wanted and len(edges) == 4:
            fixed = "".join("e" if i in wanted[label] and ch in "fF" else ch for i, ch in enumerate(edges))
            if fixed != edges:
                part = {**part, "edges": fixed}
                changed = True
        out.append(part)
    return out if changed else None


_FEATURE_NOTE = re.compile(r"^(?:hole|slot) on \S+.* leaves (?:the wall|its actual outline)", re.I)
# Which inner box sizes span each face: (width key, height key).
_BOX_FACES = {"front": ("x", "h"), "back": ("x", "h"), "left": ("y", "h"), "right": ("y", "h"), "bottom": ("x", "y"), "lid": ("x", "y")}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fit_features(features: Any, width: float, height: float, pad: float) -> tuple[Any, bool]:
    """Holes and slots of one face, moved (or shrunk) to lie inside width x height."""
    if not isinstance(features, dict):
        return features, False
    out, changed = dict(features), False
    for key in ("holes", "slots"):
        rows = features.get(key)
        if not isinstance(rows, list):
            continue
        kept = []
        for row in rows:
            x, y = (_number(row.get("x")), _number(row.get("y"))) if isinstance(row, dict) else (None, None)
            if x is None or y is None:
                kept.append(row)
                continue
            if key == "holes":
                half_w = half_h = (_number(row.get("d")) or 0.0) / 2.0
            else:
                half_w, half_h = (_number(row.get("w")) or 0.0) / 2.0, (_number(row.get("h")) or 0.0) / 2.0
            new = dict(row)
            if key == "slots":
                # A slot wider than its face is cut down to fit; its thin side is left alone.
                if half_w * 2 > width - 2 * pad:
                    half_w = max(0.0, (width - 2 * pad) / 2.0)
                    new["w"] = round(half_w * 2, 2)
                if half_h * 2 > height - 2 * pad:
                    half_h = max(0.0, (height - 2 * pad) / 2.0)
                    new["h"] = round(half_h * 2, 2)
            if half_w <= 0 or half_h <= 0 or half_w * 2 > width - 2 * pad or half_h * 2 > height - 2 * pad:
                changed = True  # cannot fit on this face at all: leave it out
                continue
            new["x"] = round(min(max(x, pad + half_w), width - pad - half_w), 2)
            new["y"] = round(min(max(y, pad + half_h), height - pad - half_h), 2)
            changed = changed or new != row
            kept.append(new)
        out[key] = kept
    return (out, True) if changed else (features, False)


def _pull_features_inside(primitives: list[Any], notes: list[str], thickness: float) -> list[Any] | None:
    """Free repair: holes and slots the gate says leave their part are moved inside it.

    Models often place a hole at 0,0 or on the edge. Each one is moved the shortest way
    to a safe margin, on box walls and flat panels. Returns None when no note asks for it
    or nothing moved; the caller recompiles and keeps the result only if the gate passes.
    """
    if not any(_FEATURE_NOTE.match(str(note)) for note in notes):
        return None
    pad = float(thickness or 3.0) + 2.5
    changed = False
    out: list[Any] = []
    for part in primitives:
        if not isinstance(part, dict):
            out.append(part)
            continue
        kind = str(part.get("type") or "").lower()
        new = part
        if kind == "box":
            sizes = {k: _number(part.get(k)) for k in ("x", "y", "h")}
            if all(v and v > 0 for v in sizes.values()):
                walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
                fixed_walls = dict(walls)
                for face, (wk, hk) in _BOX_FACES.items():
                    holder = fixed_walls if face in walls else part if isinstance(part.get(face), dict) else None
                    if holder is None:
                        continue
                    fitted, moved = _fit_features(holder.get(face), sizes[wk], sizes[hk], pad)
                    if moved:
                        changed = True
                        if holder is fixed_walls:
                            fixed_walls[face] = fitted
                        else:
                            new = {**new, face: fitted}
                if fixed_walls != walls:
                    new = {**new, "walls": fixed_walls}
        elif kind == "panel":
            width, height = _number(part.get("w")), _number(part.get("h"))
            if width and height:
                fitted, moved = _fit_features(part, width, height, pad)
                if moved:
                    changed = True
                    new = fitted
        out.append(new)
    return out if changed else None


_AXLE_NOTE = re.compile(r"^front hole .* has no coaxial back hole", re.I)
_AXLE_WORDS = re.compile(r"(tekerlek|teker|wheel|aks|axle|mil\b|shaft|pervane|propeller|rotor|dişli|disli|gear|makara|pulley|motor|dönen|donen|turning|spinning)", re.I)


def _declare_mount_holes(primitives: list[Any], notes: list[str], request: str) -> list[Any] | None:
    """Free repair: undeclared front-wall holes become mounting holes when nothing turns.

    The gate reads a bare front hole as an axle and wants its twin in the back wall. For
    a request with no wheel, shaft or motor in it, such a hole is a screw hole: say so.
    Requests that do mention a turning part are left for the model to fix properly.
    """
    if not any(_AXLE_NOTE.match(str(note)) for note in notes) or _AXLE_WORDS.search(str(request or "")):
        return None
    changed = False
    out: list[Any] = []
    for part in primitives:
        walls = part.get("walls") if isinstance(part, dict) and str(part.get("type") or "").lower() == "box" else None
        front = walls.get("front") if isinstance(walls, dict) else None
        holes = front.get("holes") if isinstance(front, dict) else None
        if isinstance(holes, list) and any(isinstance(h, dict) and not h.get("purpose") for h in holes):
            marked = [{**h, "purpose": "mount"} if isinstance(h, dict) and not h.get("purpose") else h for h in holes]
            part = {**part, "walls": {**walls, "front": {**front, "holes": marked}}}
            changed = True
        out.append(part)
    return out if changed else None


def _free_repairs(primitives: list[Any], notes: list[str], thickness: float, request: str = "") -> list[Any] | None:
    """Every code-only fix that applies to these gate notes, or None when none does."""
    current, changed = primitives, False
    for fix in (
        lambda p: _straighten_unmatched_edges(p, notes),
        lambda p: _pull_features_inside(p, notes, thickness),
        lambda p: _declare_mount_holes(p, notes, request),
    ):
        fixed = fix(current)
        if fixed:
            current, changed = fixed, True
    return current if changed else None


class _PaidDrafts:
    """Paid provider calls for one Studio AI request: drafts, repairs and their summed usage."""

    def __init__(self, *, thickness: Any, parameters: dict[str, Any], base: str, key_owner: str = "") -> None:
        self.key_owner = key_owner  # set when the caller's own provider key pays
        self.thickness = float(thickness) if thickness not in (None, "") else None
        self.parameters = parameters
        self.base = base
        self.total = {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "calls": 0}

    def call(self, text: str, model: str, effort: str) -> dict[str, Any]:
        from ai_cost import usage_cost
        from keys import current_auth
        from llm_client import plan_primitives_with_llm
        from metering import record_usage

        extra = {"key_owner": self.key_owner} if self.key_owner else {}
        plan = plan_primitives_with_llm(text, model=model, thickness=self.thickness, effort=effort, **extra)
        usage = dict(plan.get("usage") or {})
        usage["usd"] = usage_cost(
            model,
            usage.get("input_tokens") or 0,
            usage.get("output_tokens") or 0,
            usage.get("cache_read_tokens") or 0,
            usage.get("cache_write_tokens") or 0,
        )
        try:
            record_usage(current_auth.get(), "studio_ai_llm", {"model": model, **usage})
        except OSError:
            pass  # the paid plan is still worth returning when the usage log cannot be written
        self.total["input_tokens"] += int(usage.get("input_tokens") or 0)
        self.total["output_tokens"] += int(usage.get("output_tokens") or 0)
        self.total["usd"] = round(self.total["usd"] + float(usage["usd"]), 6)
        self.total["calls"] += 1
        return plan

    def design(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Compile a candidate without recording it; commit_draft() records the winner."""
        import payas_cad
        from studio import quiet_drafts

        import copy

        merged = dict(plan.get("parameters") or {})
        merged.update(self.parameters)
        token = quiet_drafts.set(True)
        try:
            # The compiler writes its own bookkeeping (ids, roles, operations) into the parts
            # it is given. On a copy, the plan stays what the model wrote: that is what the
            # repair prompt quotes, the draft cache stores and the training set records.
            primitives = copy.deepcopy(plan.get("primitives") or [])
            return payas_cad.create_design(primitives=primitives, parameters=merged, public_base_url=self.base)
        finally:
            quiet_drafts.reset(token)

    def usage(self) -> dict[str, Any]:
        return {**self.total, "usd": round(float(self.total["usd"]), 6)}

    def repair(
        self,
        request: str,
        plan: dict[str, Any],
        result: dict[str, Any],
        *,
        model_id: str,
        client_ip: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Fix a BLOCKED draft from the gate's own notes before the user ever sees it.

        Up to repair_attempts() paid tries, each passing the daily caps; the second try
        thinks harder (effort high). Returns (plan, result, info) where info says what
        was wrong and whether it was fixed, so Studio can say "fixed it" instead of
        showing a block.
        """
        from llm_client import repair_prompt
        from llm_guard import auto_repair_enabled, authorize, repair_attempts, repair_model

        issues = _gate_issues(result)
        info: dict[str, Any] = {"attempted": 0, "fixed": False, "issues": issues, "error": ""}
        if not _draft_blocked(result) or not auto_repair_enabled():
            return plan, result, info
        straightened = _free_repairs(plan.get("primitives") or [], issues, self.thickness or 3.0, request)
        if straightened:
            try:
                free_plan = {**plan, "primitives": straightened}
                free_result = self.design(free_plan)
                if not _draft_blocked(free_result):
                    info["fixed"] = True
                    info["free"] = True
                    return free_plan, free_result, info
            except Exception:
                pass  # the paid repair below still gets its turn
        # An own-key caller keeps their chosen model; the workshop may name a stronger fixer.
        fixer = model_id if self.key_owner else repair_model(model_id)
        current_plan, current_result = plan, result
        for attempt in range(repair_attempts()):
            if not authorize(fixer, client_ip=client_ip).get("allow"):
                break
            info["attempted"] = attempt + 1
            try:
                notes = _gate_issues(current_result) or issues
                text = repair_prompt(request, current_plan.get("primitives") or [], notes)
                fixed_plan = self.call(text, fixer, "medium" if attempt == 0 else "high")
                fixed = self.design(fixed_plan)
            except Exception as exc:  # keep the best draft so far and its gate notes
                info["error"] = str(exc)[:160]
                break
            current_plan, current_result = fixed_plan, fixed
            if not _draft_blocked(fixed):
                info["fixed"] = True
                return fixed_plan, fixed, info
        # Not fixed: show the latest attempt, whose notes are the freshest.
        return current_plan, current_result, info


def _repair_note(info: dict[str, Any]) -> str:
    if info.get("fixed"):
        return f"Auto-repair: the first draft had {len(info.get('issues') or []) or 'a'} gate issue(s); fixed automatically."
    if info.get("attempted"):
        return f"Auto-repair tried {info['attempted']} time(s) and could not pass the gate."
    return ""


def _studio_llm_draft(
    request: str,
    *,
    model_id: str,
    thickness: Any,
    parameters: dict[str, Any],
    base: str,
    client_ip: str,
    key_owner: str = "",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """One paid draft, repaired automatically when the gate BLOCKS it.

    Returns (design result, plan, summed usage, repair info). Raises when the first draft
    fails, so the caller can fall back to the local planner. A good draft is cached.
    """
    from ai_cache import cache_key, put as cache_put

    drafts = _PaidDrafts(thickness=thickness, parameters=parameters, base=base, key_owner=key_owner)
    # Own key: the user chose to pay for quality, so the first draft already thinks more.
    plan = drafts.call(request, model_id, "medium" if key_owner else "low")
    result = drafts.design(plan)
    plan, result, info = drafts.repair(request, plan, result, model_id=model_id, client_ip=client_ip)
    from studio import commit_draft

    # Only the draft shown to the user becomes a project version and uses quota.
    result = commit_draft(result)
    if not _draft_blocked(result):
        cache_put(cache_key(model_id, request, thickness), {**plan, "model": model_id})
    return result, plan, drafts.usage(), info


def create_studio_ai(body: dict[str, Any] | None = None, *, public_base_url: str | None = None, client_ip: str = "") -> dict[str, Any]:
    """Studio AI: prompt and/or uploaded photo|svg|plt|dxf → 3D panels. Gated by platform_ai + quota.

    client_ip keys the daily cap on provider calls; without it the signed-in caller is the key.
    """
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
    raw_prompt = str(payload.get("prompt") or payload.get("name") or payload.get("what_you_see") or "").strip()
    request = _compose_ai_chat_prompt(raw_prompt, payload)
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
        "project": (raw_prompt or request or "studio-upload")[:48],
        "what_you_see": raw_prompt or request or "studio upload",
    }
    if thickness not in (None, ""):
        parameters["thickness"] = float(thickness)
    if payload.get("material"):
        parameters["material"] = payload["material"]
    if payload.get("machine"):
        parameters["machine"] = payload["machine"]
    chat = _chat_for_storage(payload.get("messages"))
    if chat:
        # Kept with the version, so the thread comes back on another device or tab.
        parameters["studio_chat"] = chat

    cost = estimate_ai_prompt_cost(
        {
            "prompt": request or f"upload:{kind or 'file'}",
            "model": payload.get("model") or "",
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
            public_base_url=base,
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
            public_base_url=base,
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
            public_base_url=base,
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
            public_base_url=base,
            source="dxf",
            extra_look=["DXF converted to SVG millimetres. Layer ops preserved when named CUT/ENGRAVE."],
        )

    # --- Text prompt → workshop LLM (if key) else local planner ---
    from ai_cache import cache_key, simple_box_request
    from llm_guard import access, authorize

    planner_mode = str(payload.get("planner") or "").lower()
    force_local = planner_mode in {"local", "rules", "plan_laser_job"}
    prefer_llm = planner_mode in {"llm", "provider", "openai", "anthropic", "external"}
    # Studio always sends the thread, and a first request is a thread of one user turn (the
    # prompt itself); only earlier turns, gate notes or a retry make it a revision.
    turns = [m for m in (payload.get("messages") or []) if isinstance(m, dict) and str(m.get("text") or m.get("content") or "").strip()]
    in_conversation = bool(len(turns) > 1 or payload.get("prior_look_again") or payload.get("retry"))
    fresh = not prefer_llm and not in_conversation
    from ai_cache import match_maker

    recipe = match_maker(raw_prompt) if fresh and not force_local else None
    if recipe:
        # A fixed recipe already draws this (bird house, gift box, name plate…): it passes
        # the gate every time and costs nothing.
        made = create_studio_maker(
            {**recipe, "thickness": thickness or 3, "material": payload.get("material"), "machine": payload.get("machine")},
            public_base_url=base,
        )
        if made.get("success") and str(made.get("final_status")) not in {"BLOCKED", "FAIL"}:
            from studio_makers import MAKERS

            label = MAKERS.get(str(made.get("maker")), {}).get("label_tr") or str(made.get("maker"))
            return {
                **made,
                "ok": bool(made.get("export_allowed")),
                "source": "prompt",
                "plan_job": {"method": "studio_maker", "maker": made.get("maker"), "summary": f"{label} — hazır şablondan, ölçüler Süs sekmesinden değiştirilebilir."},
                "cost": cost,
                "auto_repair": {"attempted": 0, "fixed": False, "issues": []},
            }
    # A plain "W×D×H box" is drafted as well by the local planner: never pay a model for it.
    simple_box = fresh and simple_box_request(raw_prompt)
    guard: dict[str, Any]
    cached = None
    if force_local or simple_box:
        guard = {"allow": False, "reason": "local", "note": ""}
    else:
        verdict = access(payload.get("model"))
        if verdict["allow"]:
            # A draft that already passed the gate for this exact request costs nothing to reuse.
            from ai_cache import get as cache_get

            cached = cache_get(cache_key(str(verdict.get("model") or ""), request, thickness))
        guard = verdict if cached else authorize(payload.get("model"), client_ip=client_ip)
    model_id = str(guard.get("model") or "")
    provider = str(guard.get("provider") or "")
    if prefer_llm and guard["reason"] == "no_key":
        return {
            "success": True,
            "ok": False,
            "look_again": [
                "The AI model is not switched on for this site yet. Use the local planner, or try again later.",
            ],
            "plan": gate,
        }

    if cached:
        merged = dict(cached.get("parameters") or {})
        merged.update(parameters)
        result = payas_cad.create_design(primitives=cached["primitives"], parameters=merged, public_base_url=base)
        return _studio_ai_result(
            result,
            cost={**cost, "usd": {**dict(cost.get("usd") or {}), "total": 0.0}},
            plan=design_gate,
            public_base_url=base,
            plan_job={
                "summary": cached.get("summary"),
                "method": "workshop_llm_cache",
                "provider": provider,
                "model": model_id,
                "usage": {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "cached": True},
            },
            source="prompt_llm",
            extra_look=[
                "AI draft is digital only. Confirm joints and dry-fit before cutting.",
                "Same request was drafted before — reused that draft, no new AI charge.",
            ],
        )

    llm_error = ""
    if guard["allow"]:
        try:
            result, llm_plan, usage, repair_info = _studio_llm_draft(
                request,
                model_id=model_id,
                thickness=thickness,
                parameters=parameters,
                base=base,
                client_ip=client_ip,
                key_owner=str(guard.get("key_owner") or ""),
            )
            cost = estimate_ai_prompt_cost(
                {
                    "prompt": request,
                    "model": model_id,
                    "has_photo": False,
                    "mode": "mcp_thin",
                }
            )
            looks = [
                "AI draft is digital only. Confirm joints and dry-fit before cutting.",
                f"Studio AI used your own {provider} key ({model_id}) — billed to your provider account."
                if guard.get("own_key")
                else f"Studio AI used workshop {provider} key — billed to that provider, not LaserMCP lzr_.",
            ]
            return _studio_ai_result(
                result,
                cost=cost,
                plan=design_gate,
                public_base_url=base,
                plan_job={
                    "summary": llm_plan.get("summary"),
                    "method": "workshop_llm",
                    "provider": provider,
                    "model": model_id,
                    "usage": usage,
                    "own_key": bool(guard.get("own_key")),
                },
                source="prompt_llm",
                extra_look=looks,
                repair=repair_info,
            )
        except Exception as exc:
            # Fall through to local planner; surface the LLM error in look_again.
            llm_error = str(exc)
    guard_note = str(guard.get("note") or "")

    from ai_cache import parse_box_request

    box_request = parse_box_request(raw_prompt) if simple_box else None
    if box_request:
        # Same parametric engine as the Box tab: it honours the typed sizes and passes the
        # gate, where the generic planner drew a default-sized box.
        from studio_box import build_studio_box

        built = build_studio_box(
            {
                **box_request,
                "thickness": float(thickness) if thickness not in (None, "") else 3,
                "material": payload.get("material") or "poplar_3mm",
                "machine": payload.get("machine") or "payas_workshop",
            }
        )
        dims = f"{box_request['x']:g}×{box_request['y']:g}×{box_request['h']:g} {box_request['unit']}"
        plan = {
            "method": "studio_box",
            "summary": f"{dims} finger-joint box, lid: {box_request['lid']}",
            "next_arguments": {"primitives": built["primitives"], "parameters": built["parameters"]},
        }
    else:
        # The typed request is not a photo description: passing it as what_you_see made the
        # planner treat every prompt as a photo job and the reviewer demand reference
        # evidence that cannot exist, so every local draft was BLOCKED.
        plan = plan_laser_job(
            request,
            what_you_see=str(payload.get("what_you_see") or ""),
            has_photo=False,
        )
    args = plan.get("next_arguments") if isinstance(plan.get("next_arguments"), dict) else {}
    primitives = args.get("primitives") if isinstance(args.get("primitives"), list) else []
    if not primitives:
        # The planner's own notes talk to an assistant about photos; a Studio user needs
        # to know what will work instead.
        looks = [
            "Bu tasarımı yerel planlayıcı çizemiyor; AI modeli şu an kullanılamıyor."
            if guard.get("reason") not in {"signin", "pending", "ip_limit", "global_limit"}
            else "Bu tasarım için AI modeli gerekiyor.",
            "Şimdilik: ölçülü bir kutu yaz (ör. «180x120x70 kapaklı kutu»), Süs sekmesindeki hazır şablonları "
            "kullan ya da SVG/DXF/fotoğraf yükle.",
        ]
        if llm_error:
            looks.insert(0, f"Workshop LLM failed: {llm_error}")
        if guard_note:
            looks.insert(0, guard_note)
        return {
            "success": True,
            "ok": False,
            "plan_job": plan,
            "cost": cost,
            "look_again": looks
            or ["Could not draft primitives. Try a simpler box description, or upload SVG/PLT/DXF/photo."],
            "plan": gate,
        }
    merged = dict(args.get("parameters") or {}) if isinstance(args.get("parameters"), dict) else {}
    merged.update(parameters)
    from studio import commit_draft, quiet_drafts

    # Compiled quietly: if a repair replaces it, the discarded draft must not become a
    # project version or use quota. commit_draft() below records whichever is shown.
    token = quiet_drafts.set(True)
    try:
        result = payas_cad.create_design(
            primitives=primitives,
            parameters=merged,
            public_base_url=base,
        )
    finally:
        quiet_drafts.reset(token)
    repair_info: dict[str, Any] | None = None
    if _draft_blocked(result) and not force_local and not llm_error:
        # The free draft failed the gate: let the model fix it (paid, capped) rather than
        # hand the user a block. Callers who may not use the model keep the local result.
        verdict = access(payload.get("model"))
        if verdict["allow"]:
            drafts = _PaidDrafts(thickness=thickness, parameters=parameters, base=base, key_owner=str(verdict.get("key_owner") or ""))
            local_plan = {"primitives": primitives, "parameters": args.get("parameters") or {}}
            _, result, repair_info = drafts.repair(
                request, local_plan, result, model_id=str(verdict.get("model") or ""), client_ip=client_ip
            )
            if repair_info.get("attempted"):
                plan = {**plan, "usage": drafts.usage(), "repair_model": verdict.get("model")}
    result = commit_draft(result)
    looks = [
        "AI draft is digital only. Confirm joints and dry-fit before cutting.",
        "Studio AI used the local planner — no external LLM API charge from LaserMCP."
        if not (repair_info or {}).get("attempted")
        else "Local draft was repaired by the workshop model (billed to the workshop key).",
    ]
    if llm_error:
        looks.insert(0, f"Workshop LLM failed ({llm_error}); fell back to local planner.")
    if simple_box:
        looks.insert(0, "Plain box with all three sizes → drafted by the local planner at $0 (the Box tab edits it live).")
    return _studio_ai_result(
        result,
        cost=cost,
        plan=design_gate,
        public_base_url=base,
        plan_job={k: plan.get(k) for k in ("summary", "next_tool", "method", "look_again", "usage", "repair_model") if k in plan},
        source="prompt",
        extra_look=looks,
        lead_look=guard_note,
        repair=repair_info,
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
        raw_limit = body.get("limit")
        limit = None if raw_limit in (None, "", "all") else raw_limit
        if pid:
            hit = project_history(pid)
            return {"success": True, "project": hit} if hit else {"success": True, "look_again": [f"No project {pid}."], "projects": list_projects(limit=limit)}
        rows = list_projects(limit=limit)
        return {"success": True, "projects": rows, "returned": len(rows)}
    return {
        "success": True,
        "look_again": [
            "action=onboard|catalog|machines|batch|feedback|preflight|editor|revise|cost|make_this|box|ai|approve|activate|mint"
        ],
    }
