import re

with open('c:/Project/boxes-mcp/persist/job.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''    principal = _principal()
    org = _org_id(principal) or "public"
    result["design_generation"] = "DESIGN_GENERATION_SUCCESS"
    result["durable_persistence"] = False
    
    status = str(result.get("final_status") or extra.get("final_status") or "")'''

text = text.replace('''    principal = _principal()
    org = _org_id(principal)
    result["design_generation"] = "DESIGN_GENERATION_SUCCESS"
    result["durable_persistence"] = False
    if not org:
        result["persistence_note"] = "no organization boundary; local file only"
        return result
    status = str(result.get("final_status") or extra.get("final_status") or "")''', replacement)

text = text.replace('expires = expires_in_hours(30 * 24)  # 30 days', 'expires = expires_in_hours(24)  # 1 day')

with open('c:/Project/boxes-mcp/persist/job.py', 'w', encoding='utf-8') as f:
    f.write(text)
