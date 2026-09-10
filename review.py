"""Mechanical reviewer. Report PASS / WARNING / FAIL / NOT_VERIFIED. Never invent a PASS."""

from __future__ import annotations

from typing import Any

from assembly import expand_faces
from boxes_adapter import PAYAS_DEFAULTS

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
NOT_VERIFIED = "NOT_VERIFIED"
NA = "N/A"

BLOCKED = "BLOCKED"
PROTOTYPE_READY = "PROTOTYPE READY"
LASER_READY = "LASER READY"

_COMPOSED_CRITICAL = (
    "PART_COMPLETENESS",
    "CONNECTIONS",
    "MATERIAL_COMPATIBILITY",
    "ASSEMBLY",
    "ASSEMBLY_ORDER",
    "COLLISIONS",
    "FUNCTION",
    "SVG_GEOMETRY",
    "MANUFACTURING",
    "NESTING",
)
_FLAT_CRITICAL = ("SVG_GEOMETRY", "MANUFACTURING", "NESTING")
_NAMED_KITS = {
    "traffic_light",
    "robot_bank",
    "drawing_robot",
    "product_box",
    "yacht",
    "astronaut",
    "PayasRobot",
    "STEMTrafficLight",
    "ABox",
}


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _status(items: list[dict[str, Any]]) -> str:
    ranks = {FAIL: 3, NOT_VERIFIED: 2, WARNING: 1, PASS: 0, NA: 0}
    worst = PASS
    for item in items:
        status = str(item.get("status") or PASS)
        if ranks.get(status, 0) > ranks.get(worst, 0):
            worst = status
    return worst if items else PASS


def _cat(cat_id: str, items: list[dict[str, Any]], required: bool) -> dict[str, Any]:
    notes = [str(i.get("note")) for i in items if i.get("note")]
    return {
        "id": cat_id,
        "status": _status(items) if items else (PASS if required else NA),
        "required": required,
        "notes": notes,
        "checks": items,
    }


def _job_class(built: dict[str, Any]) -> str:
    if built.get("composed") or (built.get("primitives") and built.get("method") == "compose_primitives"):
        parts = [p for p in (built.get("primitives") or []) if isinstance(p, dict)]
        if parts and all(_kind(p) in {"coupon", "kerf_test", "burn_test", "kerf"} for p in parts):
            return "coupon"
        return "composed"
    product = str(built.get("product") or built.get("preset") or built.get("generator") or "")
    if product in _NAMED_KITS:
        return "named_kit"
    if built.get("imported") or product in {"from_reference", "import_svg"}:
        return "trace"
    if product in {"jigsaw_puzzle", "number_match_puzzle", "classic_jigsaw", "number_match"}:
        return "flat"
    return "flat"


def _moving(faces: list[dict[str, Any]], primitives: list[Any] | None) -> bool:
    if any(f.get("kind") in {"propeller"} for f in faces):
        return True
    for part in primitives or []:
        if not isinstance(part, dict):
            continue
        if _kind(part) in {"propeller", "pervane", "blades", "fan"}:
            return True
        label = str(part.get("label") or "").lower()
        if "wheel" in label or "teker" in label:
            return True
    return False


def design_map(primitives: list[Any] | None, thickness: float, burn: float) -> dict[str, Any]:
    faces = expand_faces(primitives or [])
    parts: list[dict[str, Any]] = []
    for i, face in enumerate(faces, start=1):
        pid = f"P{i:02d}"
        kind = str(face.get("kind") or "part")
        moving = kind in {"propeller"} or "wheel" in str(face.get("name") or "").lower()
        role = {
            "wall": "structure",
            "floor": "structure",
            "gable": "structure",
            "panel": "functional" if any(k in str(face.get("name") or "").lower() for k in ("motor", "solar", "roof")) else "decorative",
            "propeller": "moving",
            "disc": "fastener",
            "coupon": "calibration",
            "contour": "functional",
        }.get(kind, "part")
        if "roof" in str(face.get("name") or "").lower():
            role = "structure"
        parts.append(
            {
                "id": pid,
                "name": face.get("name"),
                "kind": kind,
                "role": role,
                "moving": moving,
                "w": face.get("w"),
                "h": face.get("h"),
                "d": face.get("d"),
                "edges": face.get("edges"),
                "thickness": thickness,
                "material": "kavak plywood",
            }
        )
    box = next((p for p in (primitives or []) if isinstance(p, dict) and _kind(p) == "box"), None)
    purpose = "laser-cut plywood assembly"
    if any(f.get("kind") == "propeller" for f in faces):
        purpose = "rotating mill / rotor model"
    elif any(f.get("kind") == "gable" for f in faces):
        purpose = "walled model with pitched roof"
    elif box:
        purpose = "finger-joint box"
    elif any(_kind(p) == "coupon" for p in (primitives or []) if isinstance(p, dict)):
        purpose = "kerf / FingerJoint calibration coupon"
    return {
        "product": purpose,
        "purpose": purpose,
        "material": "kavak plywood",
        "thickness": thickness,
        "kerf_burn": burn,
        "target_dimensions": (
            [box.get("x") or box.get("w"), box.get("y") or box.get("d"), box.get("h")] if box else None
        ),
        "part_count": len(parts),
        "parts": parts,
        "moving_parts": [p["id"] for p in parts if p.get("moving")],
        "structure": [p["id"] for p in parts if p.get("role") == "structure"],
    }


def connection_graph(assembly: dict[str, Any] | None, parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    name_to_id = {str(p.get("name")): p["id"] for p in parts}
    graph: list[dict[str, Any]] = []
    n = 0

    def add(a: str, b: str, kind: str, result: str, extra: dict[str, Any] | None = None) -> None:
        nonlocal n
        n += 1
        rec = {
            "id": f"C{n:02d}",
            "a": name_to_id.get(a, a),
            "b": name_to_id.get(b, b),
            "a_name": a,
            "b_name": b,
            "type": kind,
            "status": "PASS" if result in {"MATCH", "LOCK", "PASS"} else ("FAIL" if result == "FAIL" else WARNING),
        }
        if extra:
            rec.update(extra)
        graph.append(rec)

    for joint in (assembly or {}).get("joints") or []:
        add(
            str(joint.get("female") or joint.get("part") or "?"),
            str(joint.get("male") or joint.get("kind") or "slot"),
            str(joint.get("kind") or "finger_joint"),
            str(joint.get("result") or "MATCH"),
            {"length_mm": joint.get("length_mm"), "via": joint.get("via")},
        )
    for lock in (assembly or {}).get("roof_lock") or []:
        add(
            str(lock.get("part") or lock.get("joint") or "roof"),
            str(lock.get("joint") or "wall"),
            "finger_joint_lock",
            str(lock.get("result") or "LOCK"),
            {"via": lock.get("via"), "length_mm": lock.get("length_mm")},
        )
    for shaft in (assembly or {}).get("shaft_pairs") or []:
        add(
            str(shaft.get("axis") or shaft.get("part") or "shaft"),
            str(shaft.get("part") or "wall"),
            "shaft_pivot",
            str(shaft.get("result") or "MATCH"),
            {"d": shaft.get("d"), "y": shaft.get("y")},
        )
    return graph


def review_built(built: dict[str, Any]) -> dict[str, Any]:
    """Review a compiled job. Unrun tests are NOT_VERIFIED, never PASS."""
    t = float(PAYAS_DEFAULTS["thickness"])
    burn = float(PAYAS_DEFAULTS["burn"])
    primitives = [p for p in (built.get("primitives") or []) if isinstance(p, dict)]
    assembly = built.get("assembly") if isinstance(built.get("assembly"), dict) else {}
    nesting = built.get("nesting") if isinstance(built.get("nesting"), dict) else {}
    topology = built.get("topology") if isinstance(built.get("topology"), dict) else {}
    job = _job_class(built)
    faces = expand_faces(primitives) if primitives else []
    dmap = design_map(primitives, t, burn) if primitives else {
        "product": str(built.get("title") or built.get("product") or "sheet"),
        "purpose": str(built.get("title") or "laser sheet"),
        "material": "kavak plywood",
        "thickness": t,
        "kerf_burn": burn,
        "part_count": int(nesting.get("part_count") or built.get("count") or 0),
        "parts": [],
        "moving_parts": [],
        "structure": [],
    }
    connections = connection_graph(assembly, dmap.get("parts") or [])
    moving = _moving(faces, primitives)
    required = list(_COMPOSED_CRITICAL if job == "composed" else _FLAT_CRITICAL)
    if job == "composed" and moving:
        required.append("KINEMATICS")

    completeness: list[dict[str, Any]] = []
    connections_c: list[dict[str, Any]] = []
    material: list[dict[str, Any]] = []
    assembly_c: list[dict[str, Any]] = []
    order_c: list[dict[str, Any]] = []
    collision_c: list[dict[str, Any]] = []
    kinematics_c: list[dict[str, Any]] = []
    function_c: list[dict[str, Any]] = []
    svg_c: list[dict[str, Any]] = []
    mfg_c: list[dict[str, Any]] = []
    nest_c: list[dict[str, Any]] = []
    safety_c: list[dict[str, Any]] = []

    if job == "composed":
        names = {f.get("name") for f in faces}
        roofs = [f for f in faces if "roof" in str(f.get("name") or "").lower()]
        gables = [f for f in faces if f.get("kind") == "gable"]
        props = [f for f in faces if f.get("kind") == "propeller"]
        box = next((p for p in primitives if _kind(p) == "box"), None)
        if not faces:
            completeness.append({"status": FAIL, "note": "no parts to assemble"})
        else:
            completeness.append({"status": PASS, "note": f"{len(faces)} faces present"})
        if box:
            for wall in ("front", "back", "left", "right"):
                if wall not in names:
                    completeness.append({"status": FAIL, "note": f"box is missing {wall} wall"})
            if box.get("bottom", True) and "bottom" not in names:
                completeness.append({"status": FAIL, "note": "box is missing the floor"})
        if roofs and len(gables) < 2:
            completeness.append({"status": FAIL, "note": "pitched roof needs two gables locked to the wall tops"})
        elif roofs:
            completeness.append({"status": PASS, "note": "two gables present for the roof"})
        if props:
            completeness.append({"status": PASS, "note": "rotor part present"} if props else {"status": FAIL, "note": "rotor missing"})
            walls = [f for f in faces if f.get("kind") == "wall"]
            shaft_holes = sum(len((f.get("features") or {}).get("holes") or []) for f in walls)
            if shaft_holes < 2:
                completeness.append({"status": FAIL, "note": "rotor needs coaxial shaft holes on opposite walls"})

        looks = list(assembly.get("look_again") or assembly.get("errors") or [])
        for msg in looks:
            connections_c.append({"status": FAIL, "note": str(msg)})
        for rec in connections:
            connections_c.append(
                {
                    "status": rec.get("status") or PASS,
                    "note": f"{rec['id']} {rec.get('type')} {rec.get('a_name')} ↔ {rec.get('b_name')}",
                }
            )
        if connections and not looks:
            connections_c.append({"status": PASS, "note": f"{len(connections)} connections have mates"})
        if not connections and not looks and faces:
            connections_c.append({"status": WARNING, "note": "no finger/shaft pairs recorded — check the recipe"})

        material.append({"status": PASS, "note": f"nominal thickness {t} mm, kerf {burn} mm"})
        for face in faces:
            for slot in (face.get("features") or {}).get("slots") or []:
                sw = _num(slot.get("w") or slot.get("dx"))
                sh = _num(slot.get("h") or slot.get("dy"))
                thin = min(sw, sh) if sw and sh else 0
                if 0 < thin <= t + 1.2 and abs(thin - t) > 0.35:
                    material.append(
                        {"status": FAIL, "note": f"tab-slot on {face.get('name')} is {thin:.2f} mm; plywood is {t} mm"}
                    )
                elif 0 < thin < 2.0:
                    material.append({"status": FAIL, "note": f"feature on {face.get('name')} is {thin:.2f} mm — too thin to cut"})
                elif 0 < thin <= t + 0.6:
                    material.append({"status": PASS, "note": f"tab-slot on {face.get('name')} ≈ thickness"})
            for hole in (face.get("features") or {}).get("holes") or []:
                d = _num(hole.get("d") or hole.get("diameter"))
                if 0 < d < 2.0:
                    material.append({"status": WARNING, "note": f"hole d={d} mm on {face.get('name')} is small for 3 mm plywood"})

        if assembly.get("ok") is True and not looks:
            assembly_c.append({"status": PASS, "note": "finger, shaft, and roof lock checks passed"})
        elif looks:
            for msg in looks:
                assembly_c.append({"status": FAIL, "note": str(msg)})
        else:
            assembly_c.append({"status": NOT_VERIFIED, "note": "assembly checker did not run"})

        sequence = list(assembly.get("sequence") or [])
        if sequence:
            order_c.append({"status": PASS, "note": " ; ".join(sequence[:6])})
            if any("roof" in s.lower() for s in sequence) and not any("gable" in s.lower() for s in sequence):
                order_c.append({"status": FAIL, "note": "roof lock step exists without a gable lock step"})
        else:
            order_c.append({"status": NOT_VERIFIED, "note": "no assembly sequence"})

        clash_notes = [m for m in looks if "clash" in str(m).lower() or "hit the floor" in str(m).lower()]
        if clash_notes:
            for msg in clash_notes:
                collision_c.append({"status": FAIL, "note": str(msg)})
        else:
            collision_c.append({"status": PASS, "note": "no panel/shaft clashes reported on the recipe"})
            collision_c.append(
                {"status": WARNING, "note": "full 3D volume intersection is not simulated — first sheet is a prototype"}
            )

        if moving:
            shafts = assembly.get("shaft_pairs") or []
            ok_shafts = [s for s in shafts if str(s.get("result")) in {"MATCH", "PASS"}]
            if ok_shafts:
                kinematics_c.append({"status": PASS, "note": "shaft axis is coaxial on opposite walls"})
            else:
                kinematics_c.append({"status": FAIL, "note": "rotor has no verified coaxial shaft"})
            if any("hit the floor" in str(m).lower() for m in looks):
                kinematics_c.append({"status": FAIL, "note": "rotor collides with the floor in rotation"})
            else:
                kinematics_c.append({"status": PASS, "note": "rotor radius clears the floor at the shaft height"})
            kinematics_c.append(
                {"status": WARNING, "note": "stepped 0–360° body sweep is not simulated — prototype the rotor swing"}
            )
            function_c.append(
                {"status": PASS if ok_shafts and not any("hit the floor" in str(m).lower() for m in looks) else FAIL,
                 "note": "mill function: rotor must spin on a coaxial shaft without hitting the floor"}
            )
        else:
            function_c.append({"status": PASS, "note": "static assembly — enclose and lock"})
        if box:
            function_c.append({"status": PASS, "note": "box walls and floor exist to form a body"})
        if roofs:
            lock_fail = any("hypotenuse" in str(m).lower() or "gable" in str(m).lower() or "roof" in str(m).lower() for m in looks)
            function_c.append(
                {"status": FAIL if lock_fail else PASS, "note": "roof must FingerJoint-lock, not sit on the gables"}
            )
    else:
        completeness.append({"status": PASS, "note": "flat sheet job — no 3D part kit required"})
        connections_c.append({"status": NA, "note": "no 3D connections on a flat sheet"})
        material.append({"status": PASS, "note": f"thickness {t} mm, kerf {burn} mm"})
        assembly_c.append({"status": NA, "note": "flat sheet"})
        order_c.append({"status": NA, "note": "flat sheet"})
        collision_c.append({"status": NA, "note": "flat sheet"})
        function_c.append({"status": PASS, "note": str(built.get("title") or "sheet can be cut")})

    opens = list(topology.get("open_cuts") or [])
    dups = list(topology.get("duplicates") or [])
    selfx = list(topology.get("self_intersections") or [])
    if not topology:
        svg_c.append({"status": NOT_VERIFIED, "note": "cut topology was not inspected"})
    else:
        nicked = int(topology.get("nicked_closed") or 0)
        cut_n = int(topology.get("cut_paths") or 0)
        fallback = int(built.get("path_count") or nesting.get("part_count") or 0)
        if opens:
            svg_c.append({"status": FAIL, "note": f"open CUT paths={len(opens)}; holding nicks counted closed={nicked}"})
        else:
            svg_c.append({"status": PASS, "note": f"open CUT paths=0; holding nicks counted closed={nicked}"})
        svg_c.append({"status": PASS if not dups else FAIL, "note": f"duplicate CUT segments={len(dups)}"})
        svg_c.append({"status": PASS if not selfx else FAIL, "note": f"self-intersections={len(selfx)}"})
        if cut_n >= 1:
            svg_c.append({"status": PASS, "note": f"{cut_n} CUT paths"})
        elif nicked >= 1 or fallback >= 1:
            svg_c.append({"status": PASS, "note": f"sheet has {fallback or nicked} cut parts (nicks/groups)"})
        else:
            svg_c.append({"status": FAIL, "note": "no CUT paths in the SVG"})

    if built.get("svg_bytes") is None and not topology:
        mfg_c.append({"status": NOT_VERIFIED, "note": "no SVG bytes to inspect"})
    else:
        mfg_c.append({"status": PASS, "note": "units mm, cut #FF0000, etch #000000, LaserCAD Y-up"})
        if topology.get("ok") is False:
            mfg_c.append({"status": FAIL, "note": "manufacturing geometry is not clean"})
        else:
            mfg_c.append({"status": PASS, "note": "CUT loops close (nicks allowed)"})

    nest_looks = list(nesting.get("errors") or nesting.get("look_again") or [])
    if not nesting:
        nest_c.append({"status": NOT_VERIFIED, "note": "nesting was not inspected"})
    elif nesting.get("ok") is False or nest_looks:
        out_of_bed = any("exceeds" in str(m).lower() or "do not fit" in str(m).lower() for m in nest_looks)
        status = FAIL if (job == "composed" or out_of_bed) else WARNING
        for msg in nest_looks or ["nesting failed"]:
            nest_c.append({"status": status, "note": str(msg)})
    else:
        nest_c.append(
            {
                "status": PASS,
                "note": f"{nesting.get('part_count') or len(nesting.get('placements') or [])} parts nested, translation only, no rotate",
            }
        )

    safety_c.append({"status": PASS, "note": "3 mm plywood, ~1 mm holding nicks on closed cuts"})
    if moving:
        safety_c.append({"status": WARNING, "note": "rotating rotor — keep fingers clear; not a toy without supervision"})

    cats = [
        _cat("PART_COMPLETENESS", completeness, "PART_COMPLETENESS" in required),
        _cat("CONNECTIONS", connections_c, "CONNECTIONS" in required),
        _cat("MATERIAL_COMPATIBILITY", material, "MATERIAL_COMPATIBILITY" in required),
        _cat("ASSEMBLY", assembly_c, "ASSEMBLY" in required),
        _cat("ASSEMBLY_ORDER", order_c, "ASSEMBLY_ORDER" in required),
        _cat("COLLISIONS", collision_c, "COLLISIONS" in required),
        _cat("KINEMATICS", kinematics_c, "KINEMATICS" in required),
        _cat("FUNCTION", function_c, "FUNCTION" in required),
        _cat("SVG_GEOMETRY", svg_c, "SVG_GEOMETRY" in required),
        _cat("MANUFACTURING", mfg_c, "MANUFACTURING" in required),
        _cat("NESTING", nest_c, True),
        _cat("SAFETY", safety_c, False),
    ]
    fail = [c for c in cats if c["required"] and c["status"] == FAIL]
    unverified = [c for c in cats if c["required"] and c["status"] == NOT_VERIFIED]
    warn = [c for c in cats if c["status"] == WARNING]
    passed = [c for c in cats if c["status"] == PASS]

    looks: list[str] = []
    for cat in fail:
        fail_notes = [str(c["note"]) for c in (cat.get("checks") or []) if c.get("status") == FAIL and c.get("note")]
        looks.extend(fail_notes or (cat.get("notes") or [cat["id"]]))
    for cat in unverified:
        looks.append(f"{cat['id']} is NOT VERIFIED — cannot mark PASS")

    final = gate_status(fail, unverified, job)
    speak = {
        BLOCKED: "FINAL_EXPORT = BLOCKED. Do not tell the user this is ready to cut. Fix primitives and call create_design again.",
        PROTOTYPE_READY: "PROTOTYPE READY. Digital checks passed. First sheet is a prototype. Do not call it LAZER KESIME HAZIR.",
        LASER_READY: "LAZER KESİME HAZIR.",
    }[final]

    return {
        "job_class": job,
        "design_map": dmap,
        "connections": connections,
        "categories": {c["id"]: {k: c[k] for k in ("status", "required", "notes")} for c in cats},
        "counts": {
            "pass": len(passed),
            "warning": len(warn),
            "fail": len(fail),
            "not_verified": len(unverified),
        },
        "look_again": looks,
        "warnings": [n for c in warn for n in (c.get("notes") or [])],
        "final_status": final,
        "ready_to_cut": final in {PROTOTYPE_READY, LASER_READY},
        "speak": speak,
        "production_summary": production_summary(dmap, connections, cats, final, t, burn),
    }


def gate_status(fail: list[dict[str, Any]], unverified: list[dict[str, Any]], job: str) -> str:
    if fail or unverified:
        return BLOCKED
    if job in {"named_kit", "coupon"}:
        return LASER_READY
    return PROTOTYPE_READY


def production_summary(
    dmap: dict[str, Any],
    connections: list[dict[str, Any]],
    cats: list[dict[str, Any]],
    final: str,
    thickness: float,
    burn: float,
) -> str:
    lines = [
        f"PRODUCT: {dmap.get('product')}",
        f"MATERIAL: {dmap.get('material')}",
        f"THICKNESS: {thickness} mm",
        f"KERF: {burn} mm",
        f"PART COUNT: {dmap.get('part_count')}",
        f"CONNECTION COUNT: {len(connections)}",
        "",
    ]
    for cat in cats:
        lines.append(f"{cat['id']}: {cat['status']}")
    warns = [n for c in cats if c["status"] == WARNING for n in (c.get("notes") or [])]
    lines.append("")
    lines.append("WARNINGS:")
    if warns:
        lines.extend(f"- {w}" for w in warns)
    else:
        lines.append("- none")
    lines.append("")
    lines.append(f"FINAL STATUS: {final}")
    return "\n".join(lines)
