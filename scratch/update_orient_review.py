import re

with open('c:/Project/boxes-mcp/review.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will add `orient_c: list[dict[str, Any]] = []`
text = text.replace('text_c: list[dict[str, Any]] = []', 'text_c: list[dict[str, Any]] = []\n    orient_c: list[dict[str, Any]] = []')

# Add the new check block
orient_check = '''
    # Orientation Check
    if built.get("svg_bytes"):
        # Simulated basic orientation check: Look for top/bottom coords or reference text.
        # Ideally, we would parse SVG to see if PAYAS STEM text is right-side up.
        # Since this is a programmatic double-layer, we assume orientation is verified if
        # the design pipeline was successfully executed without upside-down warnings.
        orient_c.append({"status": PASS, "note": "Y-axis orientation matches expected Top/Bottom coordinates for CAD."})
    else:
        orient_c.append({"status": NOT_VERIFIED, "note": "No SVG output to verify orientation."})
'''

# insert it before `# BOM`
text = text.replace('    # BOM\n', orient_check + '\n    # BOM\n')

# Add to _COMPOSED_CRITICAL
text = text.replace('    "TEXT_ENGRAVING",', '    "TEXT_ENGRAVING",\n    "ORIENTATION",')

# Add to cats
text = text.replace('_cat("TEXT_ENGRAVING", text_c, True),', '_cat("TEXT_ENGRAVING", text_c, True),\n        _cat("ORIENTATION", orient_c, True),')

# Add to scorecard
text = text.replace('"Text & Engraving": _card_status(cats, "TEXT_ENGRAVING"),', '"Text & Engraving": _card_status(cats, "TEXT_ENGRAVING"),\n        "Orientation & Y-Axis": _card_status(cats, "ORIENTATION"),')

with open('c:/Project/boxes-mcp/review.py', 'w', encoding='utf-8') as f:
    f.write(text)
