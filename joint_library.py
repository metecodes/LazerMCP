"""Search installed Boxes.py source and schemas; never invent mating geometry."""
from __future__ import annotations
import ast
import hashlib
import inspect
import re
from functools import lru_cache
from boxes_adapter import _generators_by_name, _schema_for_class

_ALIASES = {"kalemlik": "pencil pen holder organizer", "gecme": "joint finger slot", "gecmeli": "joint finger slot", "kutu": "box", "mentese": "hinge", "kilit": "click lock", "cekmece": "drawer", "kapak": "lid", "raf": "shelf", "ev": "house"}
_FOLD = str.maketrans("ışğüöç", "isguoc")

def _tokens(text):
    words = re.findall(r"[a-z0-9]+", str(text).lower().translate(_FOLD))
    return set(words + [word for token in words for word in _ALIASES.get(token, "").split()])

@lru_cache(maxsize=1)
def library_index():
    rows, failures = [], []
    for name, cls in sorted(_generators_by_name().items()):
        try:
            source = inspect.getsource(cls)
            tree = ast.parse(source)
            settings = sorted({node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr.endswith("Settings") and isinstance(node.value, ast.Name) and node.value.id in {"edges", "lids"}})
            literals = []
            for call in ast.walk(tree):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr.endswith("Wall"):
                    literals.extend(call.args[2:3])
                    literals.extend(kw.value for kw in call.keywords if kw.arg == "edges")
            sequences = sorted({node.value for node in literals if isinstance(node, ast.Constant) and isinstance(node.value, str) and 3 <= len(node.value) <= 8 and re.fullmatch(r"[eEfFhHsSdDcCiIjJkKlLmMnNoOpPqQuUvVsSzZ|]+", node.value)})
            rows.append({"name": name, "group": getattr(cls, "ui_group", "Misc"), "description": (cls.__doc__ or "").strip(), "settings_declared": settings, "edge_sequences_in_source": sequences, "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "verification": "SOURCE_INDEXED; physical fit NOT VERIFIED"})
        except Exception as exc:
            failures.append({"name": name, "reason": str(exc)})
    return {"templates": rows, "failures": failures}

def search_joint_templates(query: str, limit: int = 5, *, include_parameters: bool = True):
    index = library_index()
    words, ranked = _tokens(query), []
    for row in index["templates"]:
        name_words = _tokens(re.sub(r"([a-z])([A-Z])", r"\1 \2", row["name"]))
        corpus = _tokens(row["description"] + " " + row["group"] + " " + " ".join(row["settings_declared"]))
        score = 4 * len(words & name_words) + len(words & corpus)
        if row["name"].lower() in str(query).lower():
            score += 50
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
    matches = [{"match_score": score, **row} for score, row in ranked[:max(1, min(int(limit), 10))]]
    if include_parameters:
        classes = _generators_by_name()
        for row in matches:
            row["parameters"] = _schema_for_class(classes[row["name"]])["parameters"]
    return {"success": True, "indexed_templates": len(index["templates"]), "scan_failures": index["failures"], "matches": matches, "workflow": "Read schema; use the named generator for matching topology. Custom silhouettes require explicit paired tabs/slots and assembly placement. Never copy only one side of a joint.", "learning_mode": "Source retrieval and code reuse; no model training or physical verification."}

def plan_references(query: str):
    result = search_joint_templates(query, 3, include_parameters=False)
    return {**result, "matches": [{k: v for k, v in row.items() if k != "parameters"} for row in result["matches"]]}
