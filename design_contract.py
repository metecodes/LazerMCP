"""Product-independent preservation of user-owned design constraints.

Compiler-generated geometry is deliberately excluded. This contract protects
intent; it is not evidence of physical fit or export fidelity.
"""
from copy import deepcopy

PROTECTED = {
    "label", "id", "type", "kind", "count", "n", "w", "h", "x", "y", "d",
    "width", "height", "depth", "length", "diameter", "role", "moving",
    "placement", "ports", "slots", "rect_holes", "holes", "markings",
    "walls", "bottom", "lid", "mechanism", "connections", "target_part",
}


def _intent(value):
    if isinstance(value, dict):
        return {k: _intent(v) for k, v in value.items()
                if k not in {"operation_origin", "operation_source", "geometry_type", "source"} and not k.startswith("_")}
    if isinstance(value, list):
        return [_intent(v) for v in value]
    return deepcopy(value)


def snapshot(parts):
    return [{key: _intent(value) for key, value in part.items() if key in PROTECTED}
            if isinstance(part, dict) else deepcopy(part) for part in parts or []]


def compare(expected, actual):
    """Return field-level diagnostics, never silently repair protected intent."""
    actual = snapshot(actual)
    changes = []
    if len(expected) != len(actual):
        changes.append({"field": "parts.count", "expected": len(expected), "actual": len(actual)})
    for index, (before, after) in enumerate(zip(expected, actual)):
        if not isinstance(before, dict) or not isinstance(after, dict):
            if before != after:
                changes.append({"field": f"parts[{index}]", "expected": before, "actual": after})
            continue
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                changes.append({"part": before.get("label") or before.get("id") or str(index),
                                "field": key, "expected": before.get(key), "actual": after.get(key)})
    return {"status": "FAIL" if changes else "PASS", "changes": changes,
            "scope": "recipe intent preservation; geometric fit is validated separately"}
