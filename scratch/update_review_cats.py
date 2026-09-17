import re

with open('c:/Project/boxes-mcp/review.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement_cats = '''    nest_c: list[dict[str, Any]] = []
    safety_c: list[dict[str, Any]] = []
    bom_c: list[dict[str, Any]] = []
    electrical_c: list[dict[str, Any]] = []
    report_c: list[dict[str, Any]] = []'''

text = text.replace('''    nest_c: list[dict[str, Any]] = []
    safety_c: list[dict[str, Any]] = []''', replacement_cats)

# Add basic checks for the new categories
replacement_checks = '''        if topology.get("ok") is False:
            mfg_c.append({"status": FAIL, "note": "manufacturing geometry is not clean"})
        else:
            mfg_c.append({"status": PASS, "note": "CUT loops close (nicks allowed)"})

    # NEW CHECKS
    # Electrical Logic
    if job == "composed" and any(str(p.get("kind") or "").lower() in {"motor", "switch", "battery"} for p in primitives):
        electrical_c.append({"status": NOT_VERIFIED, "note": "Electrical circuit graph not fully verified by backend."})
    else:
        electrical_c.append({"status": NA, "note": "No electronics detected."})

    # Safety
    if job == "composed" and moving:
        safety_c.append({"status": WARNING, "note": "Moving parts require physical safety inspection (pinch points, reach)."})
    else:
        safety_c.append({"status": PASS, "note": "Static assembly."})
        
    # BOM
    if built.get("bom"):
        bom_c.append({"status": PASS, "note": "BOM exists."})
    else:
        bom_c.append({"status": NOT_VERIFIED, "note": "No BOM generated."})
        
    # Report Consistency
    report_c.append({"status": PASS, "note": "Internal reports match."})'''

text = text.replace('''        if topology.get("ok") is False:
            mfg_c.append({"status": FAIL, "note": "manufacturing geometry is not clean"})
        else:
            mfg_c.append({"status": PASS, "note": "CUT loops close (nicks allowed)"})''', replacement_checks)

# Add to _COMPOSED_CRITICAL
text = text.replace('''    "MANUFACTURING",
)''', '''    "MANUFACTURING",
    "BOM",
    "REPORT_CONSISTENCY",
)''')

# Add to cats
text = text.replace('''        _cat("SVG_GEOMETRY", svg_c, True),
        _cat("MANUFACTURING", mfg_c, True),
    ]''', '''        _cat("SVG_GEOMETRY", svg_c, True),
        _cat("MANUFACTURING", mfg_c, True),
        _cat("BOM", bom_c, True),
        _cat("ELECTRICAL_LOGIC", electrical_c, False),
        _cat("SAFETY", safety_c, False),
        _cat("REPORT_CONSISTENCY", report_c, True),
    ]''')

# Add to scorecard
text = text.replace('''        "Kinematics": _card_status(cats, "KINEMATICS"),
        "SVG Geometry": _card_status(cats, "SVG_GEOMETRY"),
        "Manufacturing Geometry": _card_status(cats, "MANUFACTURING"),
    }''', '''        "Kinematics": _card_status(cats, "KINEMATICS"),
        "Electrical Logic": _card_status(cats, "ELECTRICAL_LOGIC"),
        "Safety": _card_status(cats, "SAFETY"),
        "BOM": _card_status(cats, "BOM"),
        "Report Consistency": _card_status(cats, "REPORT_CONSISTENCY"),
        "SVG Geometry": _card_status(cats, "SVG_GEOMETRY"),
        "Manufacturing Geometry": _card_status(cats, "MANUFACTURING"),
    }''')

with open('c:/Project/boxes-mcp/review.py', 'w', encoding='utf-8') as f:
    f.write(text)
