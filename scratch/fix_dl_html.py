with open('c:/Project/boxes-mcp/web/editor.html', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''document.getElementById("download").href = "/files/" + encodeURIComponent(state.file) + "?download=1";'''
text = text.replace('document.getElementById("download").href = "/files/" + encodeURIComponent(state.file);', replacement)

with open('c:/Project/boxes-mcp/web/editor.html', 'w', encoding='utf-8') as f:
    f.write(text)
