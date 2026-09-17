import re

with open('c:/Project/boxes-mcp/toolbox.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''            "icon",
            "lineart",
            "line_art",
            "text",
            "illustration",
        }:'''

text = text.replace('''            "icon",
            "lineart",
            "line_art",
            "text",
        }:''', replacement)

with open('c:/Project/boxes-mcp/toolbox.py', 'w', encoding='utf-8') as f:
    f.write(text)
