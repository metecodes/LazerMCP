import re

with open('c:/Project/boxes-mcp/review.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_func = '''def connection_graph(assembly: dict[str, Any] | None, parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    name_to_id = {str(p.get("name")): p["id"] for p in parts}
    graph: list[dict[str, Any]] = []
    n = 0

    def add(a: str, b: str, kind: str, result: str, extra: dict[str, Any] | None = None) -> None:
        nonlocal n
        n += 1
        
        status = "PASS" if result in {"MATCH", "LOCK", "PASS"} else ("FAIL" if result == "FAIL" else WARNING)
        reason = ""

        # 1. SELF-CONNECTION PROHIBITION
        if a == b and a not in {"?", "slot", "roof", "wall", "shaft"}:
            status = "FAIL"
            reason = "Self-connection prohibited"
        
        # 3. EXPECTED BOX TOPOLOGY (Forbidden relationships)
        a_lower, b_lower = a.lower(), b.lower()
        if {"top", "bottom"}.issubset({a_lower, b_lower}) or {"lid", "bottom"}.issubset({a_lower, b_lower}):
            status = "FAIL"
            reason = "Top panel cannot connect directly to bottom"
        if a_lower == b_lower and a_lower in {"front", "back", "left", "right"}:
            status = "FAIL"
            reason = f"Forbidden topology: {a_lower} to {b_lower}"
            
        rec = {
            "id": f"C{n:02d}",
            "a": name_to_id.get(a, a),
            "b": name_to_id.get(b, b),
            "a_name": a,
            "b_name": b,
            "type": kind,
            "status": status,
        }
        if reason:
            rec["reason"] = reason
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
    return graph'''

old_func_pattern = r'def connection_graph\(assembly: dict\[str, Any\] \| None, parts: list\[dict\[str, Any\]\]\) -> list\[dict\[str, Any\]\]:.*?return graph'
text = re.sub(old_func_pattern, new_func, text, flags=re.DOTALL)

with open('c:/Project/boxes-mcp/review.py', 'w', encoding='utf-8') as f:
    f.write(text)
