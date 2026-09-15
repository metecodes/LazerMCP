with open('c:/Project/boxes-mcp/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''def _wants_svg_editor(request: Request) -> bool:
    if request.query_params.get("download") in {"1", "true", "yes"}:
        return False'''

text = text.replace('def _wants_svg_editor(request: Request) -> bool:', replacement)

with open('c:/Project/boxes-mcp/server.py', 'w', encoding='utf-8') as f:
    f.write(text)
