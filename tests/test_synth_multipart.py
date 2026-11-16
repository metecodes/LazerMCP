"""Kits expand to designs the real gate accepts, and the synthetic requests use them."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import panel_kits as pk
import synth_multipart as sm


class KitTests(unittest.TestCase):
    def test_each_kit_passes_the_gate(self):
        cases = {
            "300x150x400 mm 3 raflı kitaplık": {"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 3},
            "400x120x200 mm duvara monte, vida delikli duvar rafı": {"type": "shelf_unit", "w": 400, "d": 120, "h": 200, "shelves": 1, "top": False, "wall_holes": True},
            "300x120x150 mm sehpa, üstünde 'Ada' yazan": {"type": "bench", "w": 300, "d": 120, "h": 150, "back_brace": True, "text": "Ada"},
            "240x120x60 mm 3 bölmeli masaüstü düzenleyici": {"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 3},
        }
        for prompt, kit in cases.items():
            with self.subTest(prompt):
                plan = {"primitives": [kit], "parameters": {"thickness": 3.0}, "summary": prompt}
                self.assertEqual(sm.check(prompt, plan, 3.0), [])

    def test_expansion_counts_and_leaves_input_alone(self):
        kit = {"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 3}
        box = {"type": "box", "x": 50, "y": 50, "h": 30}
        parts, params = pk.expand_kits([kit, box], {"thickness": 3})
        self.assertEqual([p.get("label") for p in parts[:-1]], ["bottom", "top", "left", "right", "back", "shelf-1", "shelf-2"])
        self.assertIs(parts[-1], box)
        self.assertEqual(len(params["connections"]), 8)
        self.assertEqual(kit, {"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 3})
        self.assertEqual(pk.expand_kits([box], None), ([box], None))

    def test_furniture_stands_up_in_the_viewer_frame(self):
        parts, _ = pk.expand_kits([{"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 2}], {"thickness": 3})
        pose = {p["label"]: p["placement"] for p in parts}
        self.assertEqual(pose["top"]["origin"][1], 394)            # height runs along y (inner height)
        self.assertEqual(pose["back"]["v"], [0, 1, 0])
        self.assertEqual(pose["back"]["origin"][2], 0)             # back wall away from the viewer
        self.assertEqual(pose["bottom"]["origin"][2], 147)         # open front towards the viewer
        self.assertEqual(pose["shelf-1"]["origin"][1], 197)
        tray, _ = pk.expand_kits([{"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 2}], {"thickness": 3})
        self.assertEqual(next(p for p in tray if p["label"] == "bottom")["placement"]["v"], [0, 1, 0])

    def test_walls_sit_outside_the_inner_volume_so_joints_meet_exactly(self):
        import payas_cad

        kits = (
            {"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 3},
            {"type": "bench", "w": 300, "d": 120, "h": 150, "back_brace": True},
            {"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 3},
        )
        for kit in kits:
            with self.subTest(kit=kit["type"]):
                built = payas_cad.create_design(primitives=[kit], parameters={"thickness": 3})
                joints = built["assembly"]["explicit_panel_assembly"]["joints"]
                self.assertTrue(joints)
                # Mating edges coincide: no wall is shifted by its own thickness.
                self.assertEqual(max(j["world_edge_error_mm"] for j in joints), 0)
                tabs = [d for d in built.get("tab_slot_debug") or [] if d.get("tab_id")]
                self.assertTrue(all(d["result"] == "PASS" and abs(d["insertion_depth_mm"] - 3) < 0.01 for d in tabs))
        # The outer size is the size that was asked for.
        parts, _ = pk.expand_kits([{"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 1}], {"thickness": 3})
        size = {p["label"]: (p["w"], p["h"]) for p in parts}
        self.assertEqual(size["bottom"], (294, 147))               # 300 - 2 walls, 150 - back
        self.assertEqual(size["left"], (147, 394))                 # 400 - bottom - top

    def test_the_viewer_outline_shows_the_finger_joints(self):
        import payas_cad
        from assembly_result import panels_for_viewer

        built = payas_cad.create_design(primitives=[{"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 2}], parameters={"thickness": 3})
        points = {p["label"]: len(p["outline_local_mm"]) for p in panels_for_viewer(built["assembly_result"])["panels"]}
        for wall in ("bottom", "top", "left", "right", "back"):
            self.assertGreater(points[wall], 40, wall)

    def test_two_kits_keep_their_labels_apart(self):
        kits = [{"type": "bench", "w": 300, "d": 120, "h": 150}, {"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 2}]
        parts, _ = pk.expand_kits(kits, {})
        labels = [p["label"] for p in parts]
        self.assertEqual(len(labels), len(set(labels)))
        mates = [s["mate"]["part"] for p in parts for s in p.get("slots") or []]
        self.assertTrue(mates and all(m.startswith("k2-") for m in mates))

    def test_impossible_kits_are_refused(self):
        bad = (
            {"type": "shelf_unit", "w": 300, "d": 150, "h": 100, "shelves": 8},
            {"type": "organizer", "w": 60, "d": 80, "h": 50, "compartments": 6},
            {"type": "bench", "w": 300, "d": 0, "h": 100},
            {"type": "bench", "w": 300, "h": 100},
        )
        for kit in bad:
            with self.subTest(kit=kit):
                with self.assertRaises(ValueError):
                    pk.expand_kits([kit], {"thickness": 3})

    def test_the_filter_judges_what_a_kit_becomes(self):
        import train

        kit = [{"type": "organizer", "w": 240, "d": 120, "h": 60, "compartments": 3}]
        self.assertEqual(train.shape_problems("3 bölmeli masaüstü düzenleyici", kit), [])
        self.assertTrue(train.shape_problems("kitaplık", [{"type": "bench", "w": 300, "h": 100}]))

    def test_requests_are_single_kits(self):
        rng = random.Random(3)
        made = [m for m in (sm.make(rng) for _ in range(40)) if m]
        self.assertGreater(len(made), 30)
        for prompt, plan in made:
            self.assertEqual(len(plan["primitives"]), 1, prompt)
            self.assertIn(plan["primitives"][0]["type"], pk.KIT_TYPES)
            self.assertNotIn("connections", plan["parameters"])


if __name__ == "__main__":
    unittest.main()
