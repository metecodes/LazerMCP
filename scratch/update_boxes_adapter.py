import re

with open('c:/Project/boxes-mcp/boxes_adapter.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''def save_generated_svg(
    svg_bytes: bytes,
    public_base_url: str = "http://127.0.0.1:8000",
    extra: dict[str, Any] | None = None,
    generator: str = "cad",
    dxf_bytes: bytes | None = None,
) -> dict[str, Any]:
    try:
        from persist.cleanup import cleanup_expired
        cleanup_expired()
    except Exception:
        pass
        
    name = (extra or {}).get("generator") or (extra or {}).get("product") or generator'''

text = text.replace('''def save_generated_svg(
    svg_bytes: bytes,
    public_base_url: str = "http://127.0.0.1:8000",
    extra: dict[str, Any] | None = None,
    generator: str = "cad",
    dxf_bytes: bytes | None = None,
) -> dict[str, Any]:
    name = (extra or {}).get("generator") or (extra or {}).get("product") or generator''', replacement)

with open('c:/Project/boxes-mcp/boxes_adapter.py', 'w', encoding='utf-8') as f:
    f.write(text)
