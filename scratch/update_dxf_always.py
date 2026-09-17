import re

with open('c:/Project/boxes-mcp/cad_plan.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''def _wants_dxf(text: str, output: str | None) -> str:
    # Always return both as requested
    return "both"'''

text = re.sub(r'def _wants_dxf.*?return "svg"', replacement, text, flags=re.DOTALL)

with open('c:/Project/boxes-mcp/cad_plan.py', 'w', encoding='utf-8') as f:
    f.write(text)

with open('c:/Project/boxes-mcp/job_planner.py', 'r', encoding='utf-8') as f:
    text = f.read()

# in job_planner.py:
# dxf = bool(want_dxf) or "dxf" in text
# fmt = "both" if dxf else "svg"
replacement2 = '''    dxf = True
    fmt = "both"'''

text = re.sub(r'    dxf = bool\(want_dxf\) or "dxf" in text\n    fmt = "both" if dxf else "svg"', replacement2, text)

with open('c:/Project/boxes-mcp/job_planner.py', 'w', encoding='utf-8') as f:
    f.write(text)
