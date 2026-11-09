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

    def test_box_dividers_and_shelves_get_placements(self):
        source = [{
            "type": "box",
            "label": "tray",
            "x": 120,
            "y": 90,
            "h": 60,
            "bottom": True,
            "lid": False,
            "dividers_x": 1,
            "dividers_y": 1,
            "shelves": 1,
            "sx": [58.5, 58.5],
            "sy": [43.5, 43.5],
        }]
        result = check_assembly(source, thickness=3)
        ids = [p["id"] for p in result["physical_parts"]]
        self.assertIn("tray/divider-x-1", ids)
        self.assertIn("tray/divider-y-1", ids)
        self.assertIn("tray/shelf-1", ids)
        self.assertFalse(result["illegal_collisions"])
        placed = {p["id"]: p for p in result["physical_parts"]}
        self.assertTrue(placed["tray/divider-x-1"].get("placement"))
        self.assertEqual(placed["tray/divider-x-1"]["placement_source"], "derived")
        self.assertTrue(result["ok"])
        internal = [
            c for c in result["derived_constraints"]
            if str(c.get("joint_type") or "") in {"finger_slot", "cross_lap"}
        ]
        self.assertGreaterEqual(len(internal), 10)
        self.assertTrue(all(c.get("result") == "MATCH" for c in internal))
        pairs = {frozenset((c["part_a"], c["part_b"])) for c in internal}
        self.assertIn(frozenset(("tray/divider-x-1", "tray/bottom")), pairs)
        self.assertIn(frozenset(("tray/shelf-1", "tray/front")), pairs)
        self.assertIn(frozenset(("tray/divider-x-1", "tray/divider-y-1")), pairs)
        tv = result.get("transform_validation") or {}
        self.assertEqual(tv.get("status"), "PASS")
        self.assertTrue(any(c.get("type") == "INTERNAL_FITTING" for c in tv.get("checks") or []))

    def test_drawers_seat_in_cubbies_with_finger_dividers(self):
        from studio_box import build_drawer_specs, seat_drawer_specs, drawer_cell_heights

        sx = [58.5, 58.5]
        sy = [90.0]
        cell_h = drawer_cell_heights(90, 0, 1, 3, 0)
        drawers = seat_drawer_specs(
            build_drawer_specs(sx=sx, sy=sy, cell_heights=cell_h, thickness=3),
            sx=sx,
            sy=sy,
            raised=0,
            shelves=1,
            h=90,
            thickness=3,
        )
        source = [{
            "type": "box",
            "label": "cubby",
            "x": 120,
            "y": 90,
            "h": 90,
            "bottom": True,
            "lid": False,
            "dividers_x": 1,
            "shelves": 1,
            "sx": sx,
            "sy": sy,
            "drawers": True,
            "drawer_specs": drawers,
            "divider_joint_walls": True,
            "divider_joint_bottom": True,
        }]
        result = check_assembly(source, thickness=3)
        ids = [p["id"] for p in result["physical_parts"]]
        self.assertIn("cubby/divider-x-1", ids)
        self.assertIn("cubby/shelf-1", ids)
        self.assertIn("cubby/drawer-1-front", ids)
        self.assertIn("cubby/drawer-1-bottom", ids)
        placed = {p["id"]: p for p in result["physical_parts"]}
        self.assertTrue(placed["cubby/drawer-1-front"].get("placement"))
        prims = {p["physical_part_id"]: p for p in result["_physical_primitives"]}
        self.assertEqual(str(prims["cubby/divider-x-1"].get("edges") or "")[0], "f")
        self.assertFalse(result["illegal_collisions"])
        self.assertTrue(result["ok"], result.get("look_again"))
        fingerish = [
            c for c in result["derived_constraints"]
            if str(c.get("joint_type") or "") in {"finger_slot", "cross_lap"}
        ]
        self.assertTrue(fingerish)
        self.assertTrue(all(c.get("result") == "MATCH" for c in fingerish))
        # Drawer cabinet: no front wall; each tray slides on its floor with proven free space.
        self.assertNotIn("cubby/front", ids)
        slides = [c for c in result["derived_constraints"] if c.get("joint_type") == "drawer_slide"]
        self.assertEqual(len(slides), 5 * len(drawers))
        self.assertTrue(all(c.get("result") == "MATCH" for c in slides))
        proofs = {c["drawer_slide"]["drawer"]: c["drawer_slide"] for c in slides}
        for proof in proofs.values():
            self.assertEqual(proof["status"], "PASS", proof["reason"])
            self.assertGreaterEqual(proof["side_clearance_mm"], 0.2)
            self.assertFalse(proof["path_collisions"])
        self.assertEqual({p["support"] for p in proofs.values()}, {"bottom", "shelf-1"})

    def _drawer_box(self, **overrides):
        from studio_box import build_studio_box

        body = {"x": 180, "y": 120, "h": 70, "thickness": 3, "lid": "open", "dividers_x": 1,
                "shelves": 1, "drawers": True, "name": "cab", **overrides}
        return build_studio_box(body)["primitives"]

    def _slide_proofs(self, primitives):
        result = check_assembly(primitives, thickness=3)
        checks = (result.get("transform_validation") or {}).get("checks") or []
        return result, {c["drawer"]: c for c in checks if c.get("type") == "DRAWER_SLIDE"}

    def test_drawer_slide_passes_for_every_lid_and_grid(self):
        for lid in ("open", "finger", "removable", "sliding", "hinged", "double_door"):
            for dx, shelves, dy in ((0, 0, 0), (1, 1, 0), (2, 2, 1)):
                with self.subTest(lid=lid, dx=dx, shelves=shelves, dy=dy):
                    result, proofs = self._slide_proofs(self._drawer_box(lid=lid, dividers_x=dx, shelves=shelves, dividers_y=dy))
                    self.assertTrue(result["ok"], result.get("look_again"))
                    self.assertTrue(proofs)
                    self.assertTrue(all(p["status"] == "PASS" for p in proofs.values()))

    def test_oversized_drawer_is_caught(self):
        prims = self._drawer_box()
        prims[0]["drawer_specs"][0]["w_mm"] += 4  # wider than its cubby → hits the divider
        result, proofs = self._slide_proofs(prims)
        self.assertFalse(result["ok"])
        self.assertEqual(proofs["drawer-1"]["status"], "FAIL")
        self.assertIn("divider-x-1", proofs["drawer-1"]["reason"])

    def test_floating_drawer_is_caught(self):
        from composite_assembly import validate_drawer_slide, expand

        parts = [p for p in expand(self._drawer_box(), 3)["physical_parts"] if p.get("composite_parent") == "cab"]
        for p in parts:  # lift tray 1 two millimetres off the bottom: nothing carries it
            if str(p.get("composite_role")).startswith("drawer-1-"):
                p["placement"]["origin"][2] += 2
        proof = validate_drawer_slide(parts, "drawer-1", 3)
        self.assertEqual(proof["status"], "FAIL")
        self.assertIn("no floor", proof["reason"])

    def test_blocked_pull_out_path_is_caught(self):
        from composite_assembly import validate_drawer_slide, expand

        parts = expand(self._drawer_box(dividers_x=0, shelves=0), 3)["physical_parts"]
        # A plate across the open front, in front of the tray, blocks the pull-out sweep.
        blocker = {"composite_parent": "cab", "composite_role": "front-bar", "physical_part_id": "cab/front-bar",
                   "w": 180, "h": 10, "edges": "eeee", "type": "panel",
                   "placement": {"origin": [0, -20, 20], "u": [1, 0, 0], "v": [0, 0, 1]}}
        proof = validate_drawer_slide([p for p in parts if p.get("composite_parent") == "cab"] + [blocker], "drawer-1", 3)
        self.assertEqual(proof["status"], "FAIL")
        self.assertEqual([h["part"] for h in proof["path_collisions"]], ["front-bar"])

    def test_removable_lid_seat_is_internal_fitting(self):
        source = [{
            "type": "box",
            "label": "bin",
            "x": 100,
            "y": 80,
            "h": 50,
            "bottom": True,
            "lid": {"type": "removable"},
        }]
        result = check_assembly(source, thickness=3)
        self.assertTrue(result["ok"])
        self.assertEqual((result.get("transform_validation") or {}).get("status"), "PASS")
        lid_joints = [
            c for c in result["derived_constraints"]
            if "lid" in str(c.get("part_a")) or "lid" in str(c.get("part_b"))
        ]
        self.assertTrue(lid_joints)
        self.assertTrue(all(c.get("joint_type") == "removable_lid" for c in lid_joints))
        self.assertTrue(all(c.get("result") == "MATCH" for c in lid_joints))

    def test_hinged_doors_seat_on_front_rim(self):
        # Plain "eeee" doors cannot pass an f/F finger edge mate; they must be proven as a rim seat.
        for doors, names in ((1, {"lid"}), (2, {"lid-left", "lid-right"})):
            with self.subTest(doors=doors):
                source = [{
                    "type": "box", "label": "cab", "x": 180, "y": 120, "h": 70,
                    "bottom": True, "lid": {"type": "hinged", "doors": doors},
                }]
                result = check_assembly(source, thickness=3)
                self.assertEqual((result.get("transform_validation") or {}).get("status"), "PASS",
                                 result.get("look_again"))
                lid_joints = [c for c in result["derived_constraints"] if "/lid" in str(c.get("part_a"))]
                self.assertEqual({str(c["part_a"]).split("/")[-1] for c in lid_joints}, names)
                self.assertTrue(all(c.get("joint_type") == "hinged_lid" for c in lid_joints))
                self.assertTrue(all(c.get("result") == "MATCH" for c in lid_joints))
                self.assertTrue(result["ok"], result.get("look_again"))

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
