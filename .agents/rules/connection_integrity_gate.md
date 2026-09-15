# CONNECTION INTEGRITY GATE — REQUIRED

The mechanical reviewer must validate connection identity, topology, direction, ownership, and intended function. Matching edge length or matching f/F geometry alone is not sufficient to authorize a connection.

## 1. SELF-CONNECTION PROHIBITION

A part must never be reported as connected to itself unless the primitive explicitly declares a valid self-folding or living-hinge operation.

Invalid examples:
* front ↔ front
* back ↔ back
* top_panel ↔ top_panel

If connection.a_part_id == connection.b_part_id and no explicit self_joint declaration exists:
* connection status = FAIL
* CONNECTIONS category = FAIL
* ASSEMBLY category = FAIL
* final_status = BLOCKED
* authorized_output = NONE

## 2. EXPLICIT PART ROLES

Every structural part must have one explicit assembly role:
* bottom
* front_wall
* back_wall
* left_wall
* right_wall
* top_panel
* internal_support
* moving_part
* decorative_part
* calibration_coupon

The reviewer must not infer the role only from dimensions.

## 3. EXPECTED BOX TOPOLOGY

For a six-sided rectangular enclosure, the permitted structural relationships are:
* bottom ↔ front_wall
* bottom ↔ back_wall
* bottom ↔ left_wall
* bottom ↔ right_wall
* front_wall ↔ left_wall
* front_wall ↔ right_wall
* back_wall ↔ left_wall
* back_wall ↔ right_wall
* top_panel ↔ front_wall
* top_panel ↔ back_wall
* top_panel ↔ left_wall
* top_panel ↔ right_wall

Forbidden relationships include:
* top_panel ↔ bottom
* front_wall ↔ front_wall
* back_wall ↔ back_wall
* left_wall ↔ left_wall
* right_wall ↔ right_wall

A top panel intended to close the enclosure must connect to the four side walls. It must not be matched to the bottom merely because their edge lengths are equal.

## 4. UNIQUE EDGE OWNERSHIP

Every joint edge must contain:
* part_id
* edge_id
* edge_role
* gender
* nominal_length_mm
* position
* orientation
* expected_mate_part_id
* expected_mate_edge_id
* connection_id

Each male finger edge must match exactly one female edge.

The reviewer must FAIL when:
* one edge has multiple possible mates
* an edge is paired more than once
* the expected mate is missing
* the paired parts have incompatible roles
* orientations are incompatible
* a structural edge remains orphaned

## 5. JOINT MATCH CONDITIONS

A finger-joint connection is PASS only when all conditions are true:
* different part IDs
* opposite genders: f ↔ F
* matching nominal lengths within tolerance
* compatible edge orientations
* compatible assembly roles
* matching connection_id
* reciprocal expected mate declarations
* exactly one mate per joint edge

Do not create a connection based only on equal edge length.

## 6. SHAFT AND HOLE SEMANTICS

Never infer a shaft, pivot, axle, dowel, bearing, or coaxial connection only because two or more holes have the same diameter.

A shaft connection may exist only when all related features explicitly contain:
* interface_type: shaft
* shared shaft_id
* intended_axis
* expected_mate_part_id
* diameter_mm
* functional_role

Ordinary motor screw holes, cable holes, ventilation holes and mounting holes must not generate shaft connections or shaft-related BOM items.

If `interface_type: shaft` is absent, treat the geometry as independent holes.

## 7. FUNCTIONAL COMPONENT VALIDATION

Motor, battery holder and switch openings must include:
* component_type
* component_id
* opening dimensions
* mounting method
* host_part_id
* required clearance
* cable exit or routing information

The reviewer must report whether every component is:
* retained
* accessible
* electrically routable
* clear of structural joints
* clear of neighbouring components

An internal support part must not be labelled decorative when it retains a motor or battery holder.

## 8. BOM SOURCE CONTROL

Generate BOM items only from explicitly declared hardware and interfaces.

Do not add:
* shaft
* dowel
* bearing
* screw
* spacer
* adhesive

unless that item is explicitly required by a primitive, component definition or validated connection.

Every BOM line must contain `source_feature_id`. A BOM line without a valid source feature must be removed and reported as WARNING.

## 9. REPORT CONSISTENCY AUDIT

Before issuing the final gate result, cross-check:
* connection report
* design map
* assembly sequence
* BOM
* topology report
* scorecard

If one section claims a connection that contradicts another section, set:
* REPORT_CONSISTENCY = FAIL
* final_status = BLOCKED
* authorized_output = NONE

The scorecard must never report Connections PASS when self-connections, forbidden topology, duplicate mates or orphan structural edges exist.

## 10. FAIL-CLOSED AUTHORIZATION

PROTOTYPE READY may be returned only when:
* zero self-connections
* zero forbidden connections
* zero duplicate mates
* zero orphan required edges
* all required structural relationships are satisfied
* report consistency passes
* SVG geometry passes
* manufacturing geometry passes

Otherwise return:
FINAL STATUS: BLOCKED

Include the exact failing part IDs, edge IDs, expected mate and actual detected mate. Do not repair the report by relabelling an incorrect connection as PASS.

## 11. REQUIRED CONNECTION REPORT FORMAT

For every connection return:
* connection_id
* part_a_id
* part_a_role
* edge_a_id
* part_b_id
* part_b_role
* edge_b_id
* joint_type
* expected_relationship
* detected_relationship
* geometry_match
* semantic_match
* unique_mate
* status
* reason

Also return these summary fields:
* self_connection_count
* forbidden_connection_count
* duplicate_mate_count
* orphan_required_edge_count
* inferred_shaft_count
* unsupported_bom_item_count
* report_consistency_status

Any non-zero critical count must prevent authorization.
