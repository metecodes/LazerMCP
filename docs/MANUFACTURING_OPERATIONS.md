# Manufacturing operations

Pipeline: **feature → semantic_role → operation resolution → validation → SVG export**.

CUT is never a generic fallback. `UNKNOWN` is allowed only inside the resolver and **blocks final export**. Stroke color is presentation. The exporter does not decide semantics.

## Data model

Every primitive / feature carries:

| Field | Meaning |
| --- | --- |
| `id` / `part_id` | Identity |
| `geometry_type` | Contour, hole, text, … |
| `semantic_role` | Why the geometry exists |
| `operation` | `CUT` `ENGRAVE` `SCORE` `GUIDE` `LABEL` or `UNKNOWN` |
| `operation_origin` | `EXPLICIT` `SEMANTIC_DEFAULT` `INFERRED` `UNKNOWN` |

## Resolver

`resolve_operation()` is the only place an operation is chosen.

- Designer-set `operation` → `EXPLICIT`
- Known `semantic_role` → role default (`SEMANTIC_DEFAULT`)
- Boxes.py **layer** (green etch / blue inner cut / black outer cut) **before** LaserCAD remap → `INFERRED`
- Anything else → `UNKNOWN` (not CUT)

Role defaults (not product names):

| Role | Operation |
| --- | --- |
| `outer_contour` `inner_cutout` `hole` `slot` `tab` `finger_joint` `pivot_hole` `shaft_hole` | CUT |
| `text` `logo` `surface_decoration` `facade_detail` `roof_texture` `ornament` `engraved_line` | ENGRAVE |
| `score_line` `fold_line` | SCORE |
| `construction_guide` `alignment_guide` | GUIDE |
| `label` | LABEL |
| `custom` | UNKNOWN |

`ornament` defaults to ENGRAVE. `ornament` + explicit `CUT` is a valid decorative cutout and is recorded as `EXPLICIT`.

## Designer helpers

`add_outer_contour`, `add_hole`, `add_slot`, `add_cutout`, `add_engraving`, `add_text`, `add_logo`, `add_texture`, `add_score_line`, `add_guide`.

## Exporter

Consumes already-classified drawables only. Groups `CUT` / `ENGRAVE` / `SCORE` / `GUIDE` / `LABEL`. Does not convert `UNKNOWN` to CUT. `UNKNOWN` → `exportable=false`.

## Gate

`MANUFACTURING_INTENT`: semantic roles complete, operations resolved, unknown_operations = 0, explicit overrides recorded. Any `UNKNOWN` → **BLOCKED**.
