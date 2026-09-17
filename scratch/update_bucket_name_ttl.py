import re

with open('c:/Project/boxes-mcp/persist/storage.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('SIGNED_TTL_SEC = 30 * 24 * 60 * 60', 'SIGNED_TTL_SEC = 1 * 24 * 60 * 60')

with open('c:/Project/boxes-mcp/persist/storage.py', 'w', encoding='utf-8') as f:
    f.write(text)

with open('c:/Project/boxes-mcp/persist/job.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(r'def expires_in_hours\(\) -> int:\s*return 30 \* 24', 'def expires_in_hours() -> int:\n    return 24', text)

with open('c:/Project/boxes-mcp/persist/job.py', 'w', encoding='utf-8') as f:
    f.write(text)

with open('c:/Project/boxes-mcp/persist/env.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('"lasermcp-artifacts"', '"cikti"')

with open('c:/Project/boxes-mcp/persist/env.py', 'w', encoding='utf-8') as f:
    f.write(text)
