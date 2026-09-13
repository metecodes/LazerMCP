import re

with open('c:/Project/boxes-mcp/web/landing.html', encoding='utf-8') as f:
    text = f.read()

m = re.findall(r'wow-picks.{0,1000}', text, flags=re.DOTALL)
if len(m) > 1:
    print(m[1][:500])
if len(m) > 2:
    print(m[2][:500])
