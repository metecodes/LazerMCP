# Exact SVG input

Use `create_design(svg=<complete SVG XML>, parameters={"thickness": 2.7, "svg_default_operation": "CUT", "format": "both"})` for a supplied cutting drawing.

The operation default is explicit: untagged geometry otherwise remains UNKNOWN. Existing operation metadata takes precedence. Imported SVG geometry does not receive additional holding nicks. Existing open cuts stay open; the production gate may still block them. Flat SVG does not prove assembly or identify mating partners.

DXF conversion retains each line endpoint, separate continuous subpaths, ancestor transforms and the physical viewBox scale. Curve sampling happens per segment so corners are never skipped by whole-path resampling.

The supplied `ev_kalemlik_130x90_180h_2_7mm.svg` has 116 paths including open cuts, 2.7 mm slots, detailed ornaments and a surrounding rectangular contour. Exact import retains all of them. The old 3 mm holder recipe is not an equivalent reconstruction of this drawing.
