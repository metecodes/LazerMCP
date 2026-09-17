import re

with open('c:/Project/boxes-mcp/persist/authz.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''def can_access_org(principal: dict[str, Any] | None, organization_id: str) -> bool:
    if organization_id == "public":
        return True
    if not principal or not organization_id:
        return False'''

text = text.replace('''def can_access_org(principal: dict[str, Any] | None, organization_id: str) -> bool:
    if not principal or not organization_id:
        return False''', replacement)

with open('c:/Project/boxes-mcp/persist/authz.py', 'w', encoding='utf-8') as f:
    f.write(text)
