# Shared CUT gap repair

`create_design` exposes `repair_cut_gaps: boolean` (also accepted in parameters).
Use `holding_nicks:false` and `repair_cut_gaps:true` after the user requests
restoration of untagged imported CUT gaps. Tagged holding bridges are handled
by `holding_nicks:false` without the additional flag.

Import compilation repairs before manufacturing/review; the save path uses the
same idempotent implementation. SVG and DXF therefore share the repaired geometry.
The response includes `cut_gap_repair.closed_gaps` and `square_joins` for imports.

Only unique endpoint matches within 1.5 mm in one parent/style/identity scope
are accepted. Orthogonal offset runs get square joins; real slopes stay sloped.
Engraving, closed paths, material profiles and assembly gates are not changed.
Curved open paths, scaled/skewed coordinate frames, ambiguous or unmatched ends,
and failed post-repair topology checks are errors, never silent guesses.
Rotation/reflection/translation are allowed when millimetre distances are preserved.
Micro-return cleanup is limited to zero-area changes and 0.03 mm boundary deviation.

The checked-in house source retains its reviewed source-specific endpoint pairing;
its square-join and micro-return routines now come from this shared module.
The generic tool deliberately rejects ambiguous sources instead of reproducing
that source-specific pairing without review.
