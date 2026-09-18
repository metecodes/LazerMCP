# House pencil holder diagnosis and repair

Source: create-design-20260918-111746-d06e69b6.svg, project payas-stem-house-pencil-holder-p-fb28.

The stored recipe created a complete finger-jointed box plus two decorative house contours and an unconnected divider. The reference needs the house contours to act as the actual front/back walls. The original what_you_see text explicitly moved slots to contours to avoid wall bounds checks. Contours had no bounds/partner validation, allowing misleading assembly PASS. Slot thickness alone was also incorrectly recorded as a matched joint. A bounding check used the largest rectangle dimension as a radius, incorrectly rejecting long thin slots near an edge.

The repair composes six structural contour panels with large rectangular tabs and a separate raised star: front/back, left/right, floor and divider. Eleven receiving slots refer to concrete partner tabs. The checker validates outline containment, actual tab geometry, orthonormal placements and extrusion alignment. Negative-coordinate contours now draw features with the same coordinate translation as the perimeter. Slot dimensions are checked per axis. Contour dimensions are shown read-only in the editor instead of silently changing unused w/h fields. Label changes update mating references.

Monte görünüm displays the nominal upright assembly derived from the same panel points, openings, placements and 3 mm material. It is an SVG projection, not a physics simulation or a photographed finished object. Unverified/missing placements never produce an invented assembled model. render_preview(view="assembled") and assembled_preview_url distinguish assembly from the laser cutting sheet. Geometry generation exceptions preserve success=false instead of being rewritten to success=true.

The corrected prototype keeps the original design's 130 mm width, 90 mm outer depth, 180 mm height and 3 mm material. Exact photo dimensions were not supplied. Windows and divider hole are nominal reference adaptations. The raised star is a separate cut panel with explicitly planned adhesive contact; this glue attachment is not claimed as a verified tab connection. Physical kerf, dry-fit, adhesive requirements and load/use still require actual testing. Production export remains blocked.

Validation: 89 focused Python tests; real compiler yields seven panels, eleven paired tab slots and a separate planned adhesive ornament with no duplicates/self intersections; browser checks upright/cutting view switching and loading/retry/expiry/sign-in behavior.
