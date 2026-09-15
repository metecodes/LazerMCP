import re

with open('c:/Project/boxes-mcp/web/editor.html', encoding='utf-8') as f:
    text = f.read()

for m in re.finditer(r'.{0,50}download.{0,50}', text):
    print(m.group(0))
