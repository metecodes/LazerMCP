import re

with open(r'c:\Project\boxes-mcp\.agents\rules\system_design_reviewer.md', 'a', encoding='utf-8') as f:
    f.write('''\n\n## VECTOR ILLUSTRATION / MOTIF SYSTEM
1. When generating `{"type": "illustration"}`, you MUST provide real laser-safe line-art SVG path geometry in the `d` attribute. 
2. Do NOT use simple geometric placeholders (e.g. square for robot). It must be a recognizable SVG path.
3. Subject examples: rocket, astronaut, robot, planet, saturn, sun, cloud, atom, lightbulb, earth, star, telescope, microscope, gear, dna, flask.
4. Must be single-path line-art, no collisions with holes/cuts/text/measurement scales. Engraving-safe spacing.
5. In children's STEM designs, use cute, rounded, recognizable line art.
6. If a reference image is given, follow the composition but draw clean laser line-art.
7. ILLUSTRATION_QUALITY will be verified by the Reviewer. If FAIL, the Repair Agent must re-draw the SVG path.
''')
