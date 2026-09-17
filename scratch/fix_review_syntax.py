import re

with open('c:/Project/boxes-mcp/review.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will find the NEW CHECKS block and re-indent it to 4 spaces, BUT `mfg_ops` is at 8 spaces. Wait, `mfg_ops` SHOULD be inside the `else:` block!
# So the NEW CHECKS should be OUTSIDE the `else:` block, and `mfg_ops` should stay inside the `else:` block.

# Let's just fix it manually.
# The code currently looks like:
"""
    if built.get("svg_bytes") is None and not topology:
        mfg_c.append({"status": NOT_VERIFIED, "note": "no SVG bytes to inspect"})
    else:
        mfg_c.append({"status": PASS, "note": "units mm; operation groups are authoritative, colors are presentation"})
        if topology.get("ok") is False:
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
    report_c.append({"status": PASS, "note": "Internal reports match."})
        mfg_ops = built.get("manufacturing") if isinstance(built.get("manufacturing"), dict) else None
"""

# I need to move `mfg_ops = ...` up BEFORE the NEW CHECKS, or put the NEW CHECKS at the bottom.
# Actually I'll just remove the NEW CHECKS and insert them at the correct spot.

text_lines = text.split('\n')
start_idx = -1
end_idx = -1
for i, line in enumerate(text_lines):
    if line.strip() == "# NEW CHECKS":
        start_idx = i
    if line.strip() == 'report_c.append({"status": PASS, "note": "Internal reports match."})':
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_checks = text_lines[start_idx:end_idx+1]
    del text_lines[start_idx:end_idx+1]
    
    # find where the `else:` block for mfg_c ends.
    # We can just insert new_checks right before `cats = [` (around line 520)
    insert_idx = -1
    for i, line in enumerate(text_lines):
        if 'cats = [' in line:
            insert_idx = i
            break
            
    if insert_idx != -1:
        text_lines = text_lines[:insert_idx] + new_checks + text_lines[insert_idx:]

with open('c:/Project/boxes-mcp/review.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(text_lines))
