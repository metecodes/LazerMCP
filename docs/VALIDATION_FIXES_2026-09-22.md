# Validation fixes — 22 September 2026

Validation: 334 unittest tests passed. The original audit probe was rerun; see
`VALIDATION_RETEST_2026-09-22.results.json`. These are local results, not remote
deployment verification. Original audit results are retained for comparison.

## Addressed

- Coplanar overlapping explicit panels cannot obtain finger-joint MATCH or
  PROTOTYPE READY. The supported finger compiler requires perpendicular faces.
- Rails and user-named allowed-contact parts no longer exempt entire solids
  from slide collision tests. Clearance cannot hide penetration. Touching
  support surfaces remain allowed. Corrected the old positive fixture whose
  rails previously occupied the lid volume; added independent negative tests.
- Engraving containment subtracts internal CUT holes and checks their edges.
  Removed the bounding rectangle fallback. For genuine holding nicks, rebuild
  the actual contour from ordered strokes and bounded bridges instead.
- Identical unnamed engraving geometry is rejected as duplicate engraving.
- Malformed and empty CUT paths fail topology, including paths carrying nick
  metadata. Nick metadata no longer bypasses parsing and topology inspection.
- engraving_layout no longer overrides physical part count to one.
- DXF export rejects unresolved text/image/use elements instead of silently
  omitting them. Existing generated text outlines continue to export. This is
  fail-closed handling, not general SVG text shaping or raster conversion.
- Post-save reviewer failure revokes previous final status/export authorization.
- Default engraving intent is 2x cutting speed and 0.30x cutting power, one pass:
  with the user's 30 / 50% baseline, this gives 60 / 15%. The relative profile
  does not establish speed units or program the laser controller. Physical
  calibration remains required; NaN/infinite settings are rejected.

## Remaining audit work

The full geometric engine is not certified by these fixes. In particular:

- Authoritative shared finger profiles and adaptive port keep-out placement.
- Collision checks between all physical groups and exact solids instead of
  AABB approximations; detailed intended-contact regions.
- Actual minimum-clearance measurement and proof of complete removal.
- Arbitrary unnamed engraving intersections beyond exact duplicates, complete
  ownership information, and structured DXF layer/entity consistency checks.
- General SVG text shaping/import conversion and end-to-end Studio edit tests.
- Live deployment and remote downloadable-artifact verification.
