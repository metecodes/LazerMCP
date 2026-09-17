import re

with open('c:/Project/boxes-mcp/persist/authz.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''    if artifact:
        if can_access_org(principal, str(artifact.get("organization_id") or "")):
            # Mark as opened by clearing expiration
            try:
                from persist.db import connect
                with connect() as conn:
                    conn.execute("UPDATE artifacts SET expires_at = NULL WHERE id = ?", (artifact["id"],))
                    conn.commit()
            except Exception:
                pass
            return {"allow": True, "reason": "owner", "artifact": artifact}
        return {"allow": False, "reason": "forbidden", "artifact": artifact}'''

text = text.replace('''    if artifact:
        if can_access_org(principal, str(artifact.get("organization_id") or "")):
            return {"allow": True, "reason": "owner", "artifact": artifact}
        return {"allow": False, "reason": "forbidden", "artifact": artifact}''', replacement)

with open('c:/Project/boxes-mcp/persist/authz.py', 'w', encoding='utf-8') as f:
    f.write(text)
