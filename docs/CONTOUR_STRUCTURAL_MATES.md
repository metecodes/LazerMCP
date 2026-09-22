# Contour structural mate inference

## Implementation

- `structural_mates.py`: `contour_candidates`, `infer_structural_mates`,
  `orthogonal_collision`. Extracts rectangular protrusions/recesses and actual
  inner CUT polygons; transforms full extruded candidate volumes to world space.
- `assembly.check_assembly`: inference runs before metadata-only slot failures;
  verified joints feed the existing graph and assembled preview. Inputs unchanged.
- `assembled_view.validate`: accepts only slots proven by that geometric stage;
  explicit slots keep the previous validator.
- `connection_validation.validate`: canonical coverage uses actual joint results;
  computes graph components and rejects disconnected structural parts.
- `review.review_built`: reciprocal design-map mates retain custom explicit fields;
  Connections status incorporates canonical coverage; debug returns canonical
  graph, inference evidence and components.

## Proof boundaries

Only orthogonal rectangular interfaces are inferred. Placement and names alone
are insufficient. The maximum positional/thickness tolerance is 0.05 mm.
The full tab prism must match the receiving void; positive-volume penetration
of the mating parts rejects the candidate. Non-unique feature matches block.
Existing composite box constraints retain their own solver. No geometry is changed.
Physical tests remain NOT VERIFIED.

## Regression

`tests/legacy_contour_fixture.py` constructs a synthetic 130×90×180 mm house,
24 mm interfaces, tested at 2.7 and 3 mm. Placements include material offsets;
the simplified origins in the request are not blindly treated as assembly proof.
No semantic tabs or slot mates remain in the fixture after compilation.
It yields 5 nodes, 8 unique edges, 1 component and PROTOTYPE READY.
All actual evidence/coordinates are in CONTOUR_MATE_REGRESSION.json.

10 new regression tests cover legacy geometry, outer recesses, arbitrary labels,
plain placement, misalignment/thickness/depth, collision, explicit preservation,
nonreciprocity, ambiguity, disconnected parts, full Final Gate, box and modern
11-pair tab-slot regression. Full suite: 365 tests PASS.

## Requested existing project

`create-design-20260922-160047-9334f8a1` was unavailable locally; remote SVG and
JSON URLs returned HTTP 404. Its exact geometry was not changed or regenerated.
That specific historical project's retest remains NOT VERIFIED pending its
original recipe/record. The synthetic fixture result must not be described as
that remote project's result.
