import unittest

from design_engine import compile_design
from review import review_built


class StandaloneFinalGateTests(unittest.TestCase):
    def test_single_engraving_panel_is_prototype_ready(self):
        built = compile_design(preset="engraving_layout", parameters={
            "width_mm": 200, "height_mm": 230,
            "items": [{"kind": "text", "value": "PAYAS STEM", "x": 100, "y": 115, "height": 14}],
        })
        report = review_built(built)
        self.assertEqual(report["assembly_mode"], "standalone")
        self.assertEqual(report["final_status"], "PROTOTYPE READY")
        for key in ("Connections", "Assembly", "Collision", "Kinematics", "Tab-Slot Geometry", "3D Assembly", "Assembled Preview"):
            self.assertEqual(report["scorecard"]["digital"][key], "N/A")
        self.assertEqual(report["scorecard"]["physical"]["Physical Engraving Test"], "NOT_VERIFIED")
        self.assertEqual(report["production_export"], "BLOCKED")

    def test_alphabet_board_engraving_objects_are_not_parts(self):
        items = []
        for i in range(26):
            col, row = i % 6, i // 6
            x, y = 20 + col * 32, 205 - row * 43
            items.extend([
                {"kind": "text", "value": chr(65 + i), "x": x, "y": y, "height": 7},
                {"kind": "text", "value": f"WORD{i+1}", "x": x, "y": y - 10, "height": 3},
                {"kind": "icon", "icon": "heart", "x": x, "y": y - 18, "width": 5},
            ])
        report = review_built(compile_design(preset="engraving_layout", parameters={"width_mm": 200, "height_mm": 230, "items": items}))
        self.assertEqual(report["assembly_mode_report"]["physical_part_count"], 1)
        self.assertEqual(report["final_status"], "PROTOTYPE READY")
        self.assertEqual(report["categories"]["ENGRAVE_GEOMETRY"]["status"], "PASS")
        self.assertEqual(report["categories"]["OPERATION_SEPARATION"]["status"], "PASS")

    def test_mechanical_box_keeps_assembly_required(self):
        built = compile_design(primitives=[{"type": "box", "x": 80, "y": 60, "h": 50, "bottom": True}], parameters={})
        report = review_built(built)
        self.assertEqual(report["assembly_mode"], "mechanical")
        self.assertTrue(report["categories"]["ASSEMBLY"]["required"])
        self.assertTrue(report["categories"]["3D_ASSEMBLY"]["required"])
        self.assertTrue(report["categories"]["CONNECTIONS"]["required"])

    def test_puzzle_requires_mechanical_fit(self):
        built = compile_design(preset="number_match_puzzle", parameters={"count": 2})
        report = review_built(built)
        self.assertEqual(report["assembly_mode"], "mechanical")
        self.assertTrue(report["categories"]["ASSEMBLY"]["required"])
        self.assertTrue(report["categories"]["TAB_SLOT_GEOMETRY"]["required"])

    def test_fake_standalone_is_rejected_from_physical_part_count(self):
        built = compile_design(primitives=[
            {"type": "panel", "label": "base", "w": 100, "h": 100, "edges": "eeee"},
            {"type": "panel", "label": "piece", "w": 20, "h": 20, "edges": "eeee", "role": "removable"},
        ], parameters={"assembly_mode": "standalone"})
        report = review_built(built)
        self.assertEqual(report["assembly_mode"], "mechanical")
        self.assertEqual(report["categories"]["ASSEMBLY_MODE"]["status"], "FAIL")
        self.assertEqual(report["final_status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
