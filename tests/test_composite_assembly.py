import unittest

from assembly import check_assembly
from linear_motion import validate as validate_linear_motion
from composite_assembly import expand


def panel(label, w, h, origin, *, moving=False):
    return {
        "type": "panel", "label": label, "w": w, "h": h, "edges": "eeee", "moving": moving,
        "placement": {"origin": list(origin), "u": [1, 0, 0], "v": [0, 1, 0]},
    }


class CompositeAssemblyTests(unittest.TestCase):
    def test_unplaced_box_expands_to_verified_physical_panels(self):
        source = [{"type": "box", "label": "main-bin-body", "x": 394, "y": 394, "h": 697, "bottom": True}]
        result = check_assembly(source, thickness=3)
        ids = [p["id"] for p in result["physical_parts"]]
        self.assertEqual(ids, [
            "main-bin-body/bottom", "main-bin-body/front", "main-bin-body/back",
            "main-bin-body/left", "main-bin-body/right",
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(result["finger_pairs"], 8)
        self.assertEqual(len(result["derived_constraints"]), 8)
        self.assertTrue(all(p["placement_source"] == "derived" for p in result["physical_parts"]))
        self.assertTrue(all(p["outer_cut"]["source"] == "boxes.py f/F compiled edge contract" for p in result["physical_parts"]))
        self.assertTrue(all(len(p["outer_cut"]["points"]) > 4 for p in result["physical_parts"]))
        self.assertFalse(result["ambiguous_parts"])
        self.assertFalse(result["unresolved_parts"])
        self.assertFalse(result["illegal_collisions"])
        self.assertEqual(len(result["intended_contacts"]), 8)
        self.assertIsNotNone(result["assembled_preview_svg"])

    def test_box_transform_validation_rejects_displaced_wall(self):
        source=[{"type":"box","label":"body","x":100,"y":80,"h":50,"bottom":True,
                 "child_placements":{"front":{"origin":[0,5,3],"u":[1,0,0],"v":[0,0,1]}}}]
        result=check_assembly(source,thickness=3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["transform_validation"]["status"],"FAIL")
        self.assertTrue(any(c.get("type")=="JOINT_TRANSFORM" and c.get("status")=="FAIL" for c in result["transform_validation"]["checks"]))

    def test_two_level_sliding_lid_uses_expanded_box_and_sampled_sweep(self):
        source = [
            {"type": "box", "label": "main-bin-body", "x": 394, "y": 394, "h": 697, "bottom": True},
            panel("top-lid-fixed", 394, 197, (0, 197, 706)),
            panel("top-lid-sliding", 394, 190, (0, 0, 700), moving=True),
            # Three-mm rails support the lid at Z=700, without occupying it.
            panel("lid-rail-left", 200, 8, (0, -3, 697)),
            panel("lid-rail-right", 200, 8, (194, 389, 697)),
        ]
        params = {"connections": [{
            "id": "lid-slide", "type": "linear_slide", "moving_part": "top-lid-sliding",
            "rails": ["lid-rail-left", "lid-rail-right"], "axis": [0, 1, 0],
            "travel_mm": 170, "clearance_mm": 0.1,
        }]}
        expanded = expand(source, 3)["physical_parts"]
        motion = validate_linear_motion(expanded, params, 3)
        self.assertEqual(motion["status"], "PASS")
        self.assertEqual([p["travel_mm"] for p in motion["slides"][0]["positions"]], [0, 42.5, 85, 127.5, 170])
        self.assertFalse(motion["slides"][0]["collisions"])


if __name__ == "__main__":
    unittest.main()
