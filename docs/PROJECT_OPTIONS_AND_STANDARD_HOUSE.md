# Project choices and permanent house pencil holder

MCP create_design exposes holding_nicks (boolean) and surface_texts (list).
The same fields work inside parameters. Missing choices return NEEDS_INPUT
and questions for the client to ask; explicit false and [] are valid answers.
Each project stores its own choices. Empty surface_texts means no additional
text, not deletion of text already present in the source. Source SVG/PLT jobs
with additional text are directed to semantic composition with a target area.
Reference creation also collects choices through parameters. Studio offers
the same nick switch next to its text fields.

Holding nicks are bed-retention bridges, not assembly fingers or tabs. Both
compiler and final persistence honor false. Existing nicked source geometry
is not silently healed: request the un-nicked original. Generated engraving
uses black #000000; CUT stays red #FF0000. DXF ENGRAVE is ACI 7, which viewers
may display white on dark backgrounds. Source raster ink selection (for
example yellow foreground) remains separate from the exported layer color.

Permanent model: /models/house-pencil-holder. SVG, DXF, nominal assembly
preview, recipe and digital report live under /demo/house-pencil-holder.*
and are versioned with the site, outside expiring job storage.
MCP get_standard_model and payas_defaults.standard_models return their URLs.

The model is a dimensioned interpretation of the user's house pencil-holder
reference: 130×90×180 mm, 2.7 mm material, no holding nicks, no added text,
six structural parts and one glued decorative star. Eleven tab-slot pairs
are checked. It is a digitally checked prototype, not a physically verified
production drawing or an exact measured copy of the photograph.

Rebuild with `.venv/Scripts/python.exe tools/build_standard_models.py`.
The contour renderer now strokes a compensated closed polygon, preventing
acute-corner endpoint gaps; Boxes.py inner-corner loops are disabled in favor
of normal corners so the emitted paths do not self-intersect.

Validation: 343 Python tests pass; editor and loading browser tests pass;
standard model page downloads, both actual SVG previews and mobile layout
checked in the browser. Physical assembly/kerf tests remain NOT VERIFIED.
