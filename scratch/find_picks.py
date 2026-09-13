import re

with open('c:/Project/boxes-mcp/web/landing.html', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'id="wow-picks".{0,2000}', text, flags=re.DOTALL)
if m:
    print(m.group(0)[:2000])
else:
    print("Not found")
