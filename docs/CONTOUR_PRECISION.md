# Contour precision cleanup

LaserMCP applies the same conservative CUT cleanup to the millimetre SVG before
preview, validation and DXF export. This prevents the files from diverging.

The cleanup removes only forward vertices within 0.03 mm of their neighbouring
line and removes up to 0.05 mm of drift from a nominal horizontal or vertical
run of at least 5 mm. It leaves ENGRAVE geometry, real slopes, curves and
non-millimetre source coordinates untouched.

Every candidate closed contour is checked after cleanup. If it becomes
self-intersecting, that complete contour is restored rather than guessed.
The final SVG has `data-contour-precision` with the number of scanned paths,
removed vertices, snapped vertices and reverted contours. SVG and DXF consume
the same cleaned geometry.

The tolerance is intentionally below normal laser kerf compensation. It removes
accidental point noise; it does not alter a meaningful cut dimension or repair
an actually misplaced connector.
