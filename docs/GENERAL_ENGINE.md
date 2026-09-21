# General LaserMCP engine contract

Products are recipes composed from physical parts, manufacturing operations,
connections and mechanisms. Product names are not proof of geometry or fit.

## Implemented preservation boundary

`design_contract.py` records recipe intent after explicit scaling and before
assembly preparation. Dimensions, identity, features, placement and markings
are compared after compilation. Final Gate requires DESIGN_CONTRACT when this
evidence is available. The response persists the report for inspection.

Automatic repairs cannot change protected fields, move ports, duplicate holes,
resize panels or invent parts. Rejected repair proposals remain in pipeline
diagnostics. Edge profile corrections can still be proposed. The resulting
geometry must independently pass the existing assembly validators.

Unregistered connection types fail explicitly. A new mechanism must supply its
own geometric validation before it may be treated as supported.

## Remaining architectural work (not certified by this change)

- Replace separately generated assembly outlines with the actual emitted CUT
  geometry, preserving physical IDs through nesting, SVG and DXF.
- Explicit finger joints currently choose f/F edge letters, but the reported
  shared pitch/count is not yet the authoritative generator input. They need
  a single joint geometry compiler and independent paired-profile comparison.
- Port keep-out currently rejects unsafe edge proximity; reducing finger count
  and shifting fingers around ports is not implemented.
- Reference port checks currently inspect recipe fields. Add exported SVG/DXF
  geometry comparison against an immutable feature inventory.
- Replace bounding-box-only engraving containment fallback with reconstructed
  actual contours. Do not use a bbox to certify concave shapes.
- Introduce independent swept-solid collision and assembly/removal path tests
  for every supported mechanism.
- Remote schema discovery, deployment health and downloaded-artifact checks
  must run after publication; a local unit test is not a deployment test.

## Acceptance for a new supported capability

Use arbitrary names and dimensions, multiple material thicknesses and rotated
placements. Test malformed and missing input, geometry corruption after export,
unknown connections, port migration, clashes and physical test status. Compare
actual exported geometry rather than expecting a status from the same metadata
that generated it. Production authorization requires physical evidence.

This document does not claim universal product support. Unsupported geometry
and mechanisms must remain visible as failures or unverified capability.
