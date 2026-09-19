# Semantic CAD composition

The composition subsystem treats mechanical CAD as geometry authority and artwork as semantic objects. It is product-neutral.

Object fields include `id`, `type`, `semantic_role`, `operation`, `position`, `size`, `rotation`, `parent_part_id`, `source`, and `locked`. Text additionally records content and font properties. Production output contains vector paths and explicit operation metadata.

Workflow: `inspect_design` → `compute_safe_design_area` → `create_text` / `create_vector_graphic` / `place_asset` → `align_objects` / `distribute_objects` → `compose_design` → `validate_composition` → optional `repair_composition` → composed SVG / `export_composed_dxf`.

Safe area is the outer part polygon inset by the configured margin, minus contained CUT features buffered by mechanical clearance. Explicit `anchor_feature_id` uses the actual feature center. Placement repair scales and relocates only the affected object, with at most five attempts. UNKNOWN operations fail validation. Text is outlined with the bundled Arial-compatible font and never exported as live text.

SVG paths plus rect/circle/ellipse/line/polyline/polygon elements and ancestor transforms/viewBox scaling are inspected. Millimetre ASCII DXF imports support POLYLINE, LWPOLYLINE, LINE, CIRCLE and ARC. Unknown DXF layers become UNKNOWN.

Reusable organization assets live in private Storage, with metadata in `lasermcp_assets`. A library token scopes access. Tokens are returned only when a new library is created and are stored only as SHA-256 hashes. Assets have no 24-hour artifact expiry.

Current limits: semantic editing operates through immutable object payloads and recomposition; editable DXF TEXT entities are intentionally omitted. Bold text metadata is retained but the bundled font file is regular-weight, so production geometry currently uses the metrically compatible regular face. Image references use contour vectorization, not grayscale raster engraving. Bézier input is accepted through SVG path data and flattened for DXF.
