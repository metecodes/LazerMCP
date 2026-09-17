import re

with open('c:/Project/boxes-mcp/review.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''        for rec in connections:
            note = f"{rec['id']} {rec.get('type')} {rec.get('a_name')} ↔ {rec.get('b_name')}"
            if rec.get("reason"):
                note += f" — {rec['reason']}"
            connections_c.append(
                {
                    "status": rec.get("status") or PASS,
                    "note": note,
                }
            )'''

text = text.replace('''        for rec in connections:
            connections_c.append(
                {
                    "status": rec.get("status") or PASS,
                    "note": f"{rec['id']} {rec.get('type')} {rec.get('a_name')} ↔ {rec.get('b_name')}",
                }
            )''', replacement)

with open('c:/Project/boxes-mcp/review.py', 'w', encoding='utf-8') as f:
    f.write(text)
