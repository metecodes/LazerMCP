import re

with open('c:/Project/boxes-mcp/server.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''@mcp.tool(description="Validate a generated SVG: XML, 1500×3000 bed, nested part spacing. Pass file_id (for internal) OR url (if user uploaded an SVG directly to you).")
def validate_svg(file_id: str | None = None, url: str | None = None) -> dict[str, Any]:
    try:
        if url and not file_id:
            import urllib.request
            import uuid
            from pathlib import Path
            req = urllib.request.Request(url, headers={"User-Agent": "LazerMCP/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            file_id = f"uploaded_{uuid.uuid4().hex[:8]}.svg"
            out_path = Path("output") / file_id
            out_path.parent.mkdir(exist_ok=True, parents=True)
            out_path.write_bytes(data)
            
        if not file_id:
            return payas_cad._mcp({"look_again": ["Must provide either file_id or url"], "well_formed": False})
            
        return payas_cad._mcp(boxespy.validate_svg(file_id))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "file_id": file_id, "well_formed": False})'''

text = re.sub(
    r'@mcp\.tool\(description="Validate a generated SVG: XML, 1500×3000 bed, nested part spacing. Loads assembly report if present."\)\s*def validate_svg\(file_id: str\) -> dict\[str, Any\]:\s*try:\s*return payas_cad\._mcp\(boxespy\.validate_svg\(file_id\)\)\s*except Exception as exc:\s*return payas_cad\._mcp\(\{"look_again": \[str\(exc\)\], "file_id": file_id, "well_formed": False\}\)',
    replacement,
    text,
    flags=re.MULTILINE
)

with open('c:/Project/boxes-mcp/server.py', 'w', encoding='utf-8') as f:
    f.write(text)
