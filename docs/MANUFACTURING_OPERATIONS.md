# Manufacturing operations

Manufacturing intent is a first-class field on every geometry primitive. Stroke color is presentation only.

## Data model

Every primitive and nested feature (`holes`, `slots`, `markings`) carries:

| Field | Meaning |
| --- | --- |
| `semantic_role` | Why the geometry exists |
| `operation` | How it is manufactured |
| `operation_source` | `explicit` (designer set it), `default` (from role), or `inferred` (keywords / group / color hint) |

Operations: `CUT` | `ENGRAVE` | `SCORE` | `GUIDE` | `LABEL`.

Role defaults (general, not product-specific):

| Role | Default operation |
| --- | --- |
| `outer_contour`, `hole`, `slot`, `finger_joint`, `tab` | `CUT` |
| `text`, `logo`, `texture`, `decorative_detail` | `ENGRAVE` |
| `construction_guide` | `GUIDE` |
| `score` | `SCORE` |
| `label` | `LABEL` |

A designer may mark text, logo, or decor as `CUT`. That must be an explicit `operation` and is logged as an auditable WARNING. Implicit text `CUT` is a critical FAIL.

## Pipeline

1. Boxes.py (or a kit) draws geometry. Etch uses the Boxes.py green layer; cuts use black/blue.
2. `stamp_source_operations` records `data-operation` from group id, keywords, then Boxes.py color. Color is last.
3. `prepare_lasercad_svg` remaps colors for LaserCAD. Existing `data-operation` is kept.
4. `apply_manufacturing_svg` writes the five layer groups (`CUT`, `ENGRAVE`, `SCORE`, `GUIDE`, `LABEL`), stamps every drawable, and applies presentation colors.
5. `nick_cut_svg` nicks only `CUT` paths. Holding nicks stay `CUT` and are closed topology, not open-path errors.
6. `validate_svg_operations` / `validate_primitives` run in the reviewer. Critical FAIL blocks the final gate (`MANUFACTURING` → `BLOCKED`).

DXF export reads `data-operation` (and ancestor group), not stroke color alone. `GUIDE` is omitted from the cut file.

## Validator

| Condition | Result |
| --- | --- |
| Missing or unknown operation | FAIL (critical) |
| Text `CUT` without `operation_source=explicit` | FAIL |
| Text / logo `CUT` when explicit | WARNING (auditable) |
| Texture / decorative `CUT` | WARNING |
| Guide `CUT` | FAIL |
| Outer contour not `CUT` | FAIL |
| Slot / hole not `CUT` | FAIL |
| Holding nick not `CUT` | FAIL |
| No `CUT` on the sheet, or a missing operation group | FAIL |

## What this is not

Rules are role- and operation-based. Windmill, house, traffic light, Ferris wheel, and robot kit are regression fixtures only — none of them have special-case code in the manufacturing layer.
