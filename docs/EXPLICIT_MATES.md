# Explicit contour/panel mates

Optional `part_id` and `connectors` bind declarations to existing manufacturing
CUT geometry. They never add, move or resize tabs, slots or ports.

Each connector has a globally unique `id`, reciprocal `mate_id`, owning
`part_id`, `type`, local `position` (feature volume centre), local insertion
`axis`, and positive `width_mm`, `depth_mm`, `thickness_mm`. A 2D position uses
half material thickness for its third coordinate. Alternatively declare
`mates: [{connector_id, target_connector}]` on each side.

Implemented physical interfaces: rectangular tab/slot and finger/finger_socket.
Both must resolve uniquely to actual contour features or inner CUT slots.
Full transformed prism alignment, nominal solid interference and continuous
translational insertion against already installed parts are checked. The
sequence uses physical IDs in `parameters.assembly_order`; if omitted, a
deterministic graph order is attempted. Failed insertion is not evidence that
no alternative assembly order exists. No failed sequence produces steps.

Outputs include `canonical_mates.connections[].checks`, per-connector errors,
verified locked mates, sequence and targeted repair scope. Legacy broad repair
is disabled for explicit connectors to avoid changing verified interfaces.
Slight rounded frame error is normalized; parallel/skewed axes fail. Scaling
changes dimensions and positions, never insertion direction vectors.

## Limits

Pin/hole, edge/edge, hinge/hinge, axle/bearing, rail/slider and custom connector
adapters are not implemented in this new connector API. Compatible type names
alone return `MATE_GEOMETRY_UNSUPPORTED`. Existing `parameters.connections`
shaft/slide validators continue to operate. Mixed composite/explicit sequences
are not automatically merged into this new insertion graph. Group insertion,
rotation during insertion and automatic search across assembly orders are not
implemented. Legacy inferred mates carry GEOMETRY_VERIFIED and insertion
NOT_VERIFIED; they must not be advertised as continuously swept assemblies.

## Exact v18 regression

`tests/fixtures/house_lamp_v18.json` preserves the supplied recipe unchanged.
It produces 12 physical parts. Independent house/roof panels no longer receive
box-face transform rules. Unmatched slots can no longer hide behind passing
box joints. Coincident male tabs fail NON_COMPLEMENTARY_JOINT/MATE_COLLISION.

The supplied recipe has no explicit connector declarations and its geometry
still fails fit: bottom tabs and roof slots do not coincide in world space;
corner male tabs overlap. Its correct outcome is BLOCKED. See
`HOUSE_LAMP_V18_RETEST.json` for numeric candidate diagnostics (nearest candidate
is not an accepted mate). The report is a local regression, not a live claim.
Physical manufacturing/assembly remain NOT_VERIFIED.
