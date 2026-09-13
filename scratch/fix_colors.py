import os
import re

d = r'c:\Project\boxes-mcp\web'
for x in os.listdir(d):
    if not x.endswith('.html'): continue
    path = os.path.join(d, x)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Replace background: #fff with background: var(--paper)
    # 2. Replace color: #fff with color: var(--bg) WHEN it's paired with background: var(--ink) or similar situations where text must contrast with --ink
    
    # Let's fix .chip background
    content = content.replace('background: #fff', 'background: var(--paper)')
    
    # Let's fix .lang button.on { background: var(--ink); color: #fff; } -> color: var(--bg)
    content = content.replace('color: #fff', 'color: var(--bg)')
    
    # WAIT! .pane { background: #111; color: var(--bg) } -> this is wrong because in dark mode --bg is #111, so it will be #111 text on #111 bg!
    # Let's restore .pane color: var(--bg) back to #fff because .pane background is #111 always!
    content = content.replace('.pane { background: #111; color: var(--bg)', '.pane { background: #111; color: #fff')
    content = content.replace('.pane { background: #111; color: #fff', '.pane { background: #111; color: #fff') # just in case
    
    # Also pass-card and pane.light
    content = content.replace('background: #eef7f2', 'background: var(--surface-ok)')
    content = content.replace('background: #f4efe6', 'background: var(--surface-alt)')
    content = content.replace('background: #f3eee6', 'background: var(--surface)')
    
    # Also in .toggle button.on { background: var(--ink); color: #fff; }
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed {x}")
