import re

with open('c:/Project/boxes-mcp/review.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will add `text_c: list[dict[str, Any]] = []`
text = text.replace('bom_c: list[dict[str, Any]] = []', 'bom_c: list[dict[str, Any]] = []\n    text_c: list[dict[str, Any]] = []')

# Add the new check block
text_check = '''
    # Text & Engraving Double Layer Validation
    has_live = False
    svg_data = built.get("svg_bytes")
    if svg_data:
        try:
            svg_text = svg_data.decode("utf-8")
            import re
            if re.search(r"<text[\s>]", svg_text, re.I):
                has_live = True
        except Exception:
            pass
            
    if has_live:
        text_c.append({"status": FAIL, "note": "Layer 1 FAIL: SVG contains raw <text> tags. Must be converted to paths."})
    elif svg_data:
        text_c.append({"status": PASS, "note": "Layer 1 PASS: No raw <text> tags detected."})
    else:
        text_c.append({"status": NOT_VERIFIED, "note": "Layer 1: No SVG generated yet."})
        
    if mfg_ops:
        text_cut = any(
            item.get("status") == "FAIL" and ("text" in str(item.get("note") or "").lower() and "cut" in str(item.get("note") or "").lower()) 
            for item in (mfg_ops.get("checks") or [])
        )
        if text_cut:
            text_c.append({"status": FAIL, "note": "Layer 2 FAIL: Text or label is marked as CUT instead of ENGRAVE."})
        else:
            text_c.append({"status": PASS, "note": "Layer 2 PASS: Text operations correctly mapped to ENGRAVE."})
    else:
        text_c.append({"status": NOT_VERIFIED, "note": "Layer 2: Manufacturing intent not available for text checks."})
'''

# insert it before `# BOM`
text = text.replace('    # BOM\n', text_check + '\n    # BOM\n')

# Add to _COMPOSED_CRITICAL
text = text.replace('    "BOM",', '    "BOM",\n    "TEXT_ENGRAVING",')

# Add to cats
text = text.replace('_cat("BOM", bom_c, True),', '_cat("BOM", bom_c, True),\n        _cat("TEXT_ENGRAVING", text_c, True),')

# Add to scorecard
text = text.replace('"BOM": _card_status(cats, "BOM"),', '"BOM": _card_status(cats, "BOM"),\n        "Text & Engraving": _card_status(cats, "TEXT_ENGRAVING"),')

with open('c:/Project/boxes-mcp/review.py', 'w', encoding='utf-8') as f:
    f.write(text)
