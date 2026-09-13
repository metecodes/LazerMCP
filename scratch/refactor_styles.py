import os
import re

WEB_DIR = r"c:\Project\boxes-mcp\web"

COMMON_SELECTORS = [
    ":root", "*", "html", "body", "a", "input", "select", "textarea", "input:focus", 
    "select:focus", "textarea:focus", "h1", "h2", "h3", "h1, h2, h3", ".kicker", ".lede", 
    "nav", ".brand", ".mark", ".mark::after", "nav .links", "nav .links a", ".card", 
    ".btn", ".btn.ghost", ".btn.cut", ".btn-google", ".btn-google svg", ".btn:disabled", 
    ".hide", ".row"
]

def refactor_html(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if '<link rel="stylesheet" href="/styles.css">' in content:
        print(f"Already refactored {filepath}")
        return

    # A simple regex to find the style block
    style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
    if not style_match:
        print(f"No style block found in {filepath}")
        return

    style_content = style_match.group(1)
    
    # We will remove lines that define common styles. 
    # Since they are mostly written as one-liners or simple blocks, we can just do a very coarse removal
    # or just let styles.css override it. Wait, embedded styles override linked ones if they come AFTER, 
    # so we should put <link> AFTER <style> or remove them. 
    # It's better to remove them. We can use a regex to match blocks.
    
    # Let's remove basic blocks like `:root { ... }`
    style_content = re.sub(r':root\s*\{[^}]*\}', '', style_content, flags=re.DOTALL)
    
    # It's hard to safely parse CSS with regex. 
    # An easier way is just to replace the whole `<style>...</style>` block with `<link rel="stylesheet" href="/styles.css">\n  <style>...</style>`
    # BUT we want Dark mode to work, so we MUST remove the `body { background: var(--bg); }` etc from the inline style.
    
    # Let's remove these specific lines that are problematic:
    style_content = re.sub(r'body\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\*\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'html\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'a\s*\{[^}]*\}', '', style_content)
    
    # We also remove .btn, .btn.ghost, .btn.cut, .btn-google
    style_content = re.sub(r'\.btn\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.btn\.ghost\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.btn\.cut\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.btn-google\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.btn-google svg\s*\{[^}]*\}', '', style_content)
    
    style_content = re.sub(r'nav\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.brand\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.mark\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'\.mark::after\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'nav \.links\s*\{[^}]*\}', '', style_content)
    style_content = re.sub(r'nav \.links a\s*\{[^}]*\}', '', style_content)
    
    # .hide
    style_content = re.sub(r'\.hide\s*\{[^}]*\}', '', style_content)
    
    # Then we write it back
    new_style_block = f'<link rel="stylesheet" href="/styles.css">\n  <style>{style_content}</style>'
    new_content = content[:style_match.start()] + new_style_block + content[style_match.end():]
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print(f"Refactored {filepath}")

for filename in os.listdir(WEB_DIR):
    if filename.endswith(".html"):
        refactor_html(os.path.join(WEB_DIR, filename))
