"""Studio parametric box features + mm-scaled SVG→STL."""

from __future__ import annotations

import unittest

from studio_box import (
    build_assembly_guide,
    build_studio_box,
    cells_with_locks,
    equal_cells,
    resolve_inner_outer,
    volume_liters,
)


class StudioBoxFeaturesTests(unittest.TestCase):
    def test_internal_external_dims(self):
        inner = resolve_inner_outer(150, 100, 60, 3, dimension_mode="internal")
        self.assertEqual(inner["x_inner"], 150)
        self.assertAlmostEqual(inner["x_outer"], 156)
        outer = resolve_inner_outer(156, 106, 63, 3, dimension_mode="external")
        self.assertAlmostEqual(outer["x_inner"], 150)
        self.assertAlmostEqual(outer["y_inner"], 100)

    def test_volume(self):
        self.assertAlmostEqual(volume_liters(100, 100, 100), 1.0)

    def test_equal_cells(self):
        cells = equal_cells(100, 1, 3)
        self.assertEqual(len(cells), 2)
        self.assertAlmostEqual(sum(cells) + 3, 100)

    def test_build_open_box(self):
        built = build_studio_box({"x": 120, "y": 80, "h": 40, "thickness": 3, "lid": "open"})
        box = built["primitives"][0]
        self.assertFalse(box["lid"])
        self.assertEqual(built["summary"]["lid"], "open")
        self.assertIn("FingerJoint_finger", built["parameters"])

    def test_build_dividers_and_press_fit(self):
        built = build_studio_box(
            {
                "x": 180,
                "y": 120,
                "h": 70,
                "thickness": 3,
                "lid": "removable",
                "dividers_x": 1,
                "dividers_y": 1,
                "press_fit": True,
                "bottom_lift": 6,
                "finger": 2.5,
            }
        )
        box = built["primitives"][0]
        self.assertEqual(box["dividers_x"], 1)
        self.assertEqual(box["bottom_lift"], 6)
        self.assertEqual(built["parameters"]["FingerJoint_style"], "springs")
        self.assertEqual(box["lid"]["type"], "removable")
        self.assertEqual(built["summary"]["joints"]["style"], "springs")
        self.assertEqual(built["summary"]["kerf_status"], "NOT_VERIFIED")

    def test_joint_kerf_assumed_when_burn_set(self):
        from studio_box import validate_joint_settings

        ok = validate_joint_settings(thickness=3, finger_mult=2, burn=0.15)
        self.assertEqual(ok["kerf_status"], "ASSUMED")
        self.assertEqual(ok["physical_fit"], "NOT_VERIFIED")
        bad = validate_joint_settings(thickness=3, finger_mult=2, burn=0.9)
        self.assertEqual(bad["status"], "FAIL")

    def test_unequal_divider_positions(self):
        from studio_box import cells_from_divider_positions, divider_positions

        cells = cells_from_divider_positions(100, [30], 3)
        self.assertEqual(len(cells), 2)
        self.assertAlmostEqual(cells[0] + 3 + cells[1], 100)
        back = divider_positions(cells, 3)
        self.assertAlmostEqual(back[0], 30, places=1)
        built = build_studio_box(
            {"x": 120, "y": 80, "h": 40, "thickness": 3, "lid": "open", "divider_x_mm": [40]}
        )
        self.assertEqual(built["summary"]["dividers_x"], 1)
        self.assertAlmostEqual(built["summary"]["divider_x_pos"][0], 40, places=1)
        with self.assertRaises(ValueError):
            cells_from_divider_positions(100, [5], 3)

    def test_shelves(self):
        built = build_studio_box(
            {"x": 120, "y": 80, "h": 90, "thickness": 3, "lid": "open", "shelves": 2}
        )
        self.assertEqual(built["primitives"][0]["shelves"], 2)
        self.assertEqual(built["summary"]["shelves"], 2)
        from toolbox import render_toolbox

        out = render_toolbox(built["primitives"], built["parameters"])
        self.assertIn("svg_bytes", out)
        self.assertGreater(len(out["svg_bytes"]), 200)
        svg = out["svg_bytes"].decode("utf-8", errors="ignore")
        self.assertIn("shelf-1", svg)
        self.assertIn("shelf-2", svg)

    def test_locked_cells(self):
        cells = cells_with_locks(100, 1, 3, {0: 30})
        self.assertEqual(len(cells), 2)
        self.assertAlmostEqual(cells[0], 30)
        self.assertAlmostEqual(sum(cells) + 3, 100)
        built = build_studio_box(
            {
                "x": 150,
                "y": 90,
                "h": 50,
                "thickness": 3,
                "lid": "open",
                "dividers_x": 2,
                "locked_cells_x": {"0": 40},
            }
        )
        sx = built["summary"]["sx"]
        self.assertEqual(len(sx), 3)
        self.assertAlmostEqual(sx[0], 40)
        self.assertAlmostEqual(sum(sx) + 2 * 3, 150, places=1)
        with self.assertRaises(ValueError):
            cells_with_locks(100, 1, 3, {0: 90})

    def test_handle_bump_divider_joints(self):
        built = build_studio_box(
            {
                "x": 120,
                "y": 80,
                "h": 50,
                "thickness": 3,
                "lid": "removable",
                "handle": False,
                "lid_radius": 4,
                "press_fit": True,
                "bump_diameter": 0.8,
                "divider_joint_walls": False,
                "divider_joint_bottom": True,
                "dividers_x": 1,
            }
        )
        box = built["primitives"][0]
        self.assertFalse(box["lid"]["handle"])
        self.assertEqual(box["lid"]["radius"], 4)
        self.assertFalse(box["divider_joint_walls"])
        self.assertTrue(box["divider_joint_bottom"])
        self.assertAlmostEqual(built["parameters"]["FingerJoint_surround"], 0.8)

    def test_crosslap_dividers_render(self):
        from toolbox import render_toolbox

        built = build_studio_box(
            {
                "x": 120,
                "y": 100,
                "h": 50,
                "thickness": 3,
                "lid": "open",
                "dividers_x": 1,
                "dividers_y": 1,
            }
        )
        out = render_toolbox(built["primitives"], built["parameters"])
        self.assertIn("svg_bytes", out)
        svg = out["svg_bytes"].decode("utf-8", errors="ignore")
        self.assertIn("divider-x-1", svg)
        self.assertIn("divider-y-1", svg)
        # Cross-lap half-slots appear as extra cut geometry on both divider panels
        self.assertGreater(svg.lower().count("path"), 8)

    def test_divider_wall_edges_are_finger_not_butt(self):
        from toolbox import render_toolbox

        built = build_studio_box(
            {
                "x": 150,
                "y": 120,
                "h": 90,
                "thickness": 3,
                "lid": "open",
                "dividers_x": 1,
                "dividers_y": 1,
                "shelves": 1,
                "drawers": False,
                "divider_joint_walls": True,
                "divider_joint_bottom": True,
            }
        )
        out = render_toolbox(built["primitives"], built["parameters"])
        svg = out["svg_bytes"].decode("utf-8", errors="ignore")
        self.assertIn("divider-x-1", svg)
        self.assertIn("divider-y-1", svg)
        self.assertIn("shelf-1", svg)
        # Finger edges + shelf/divider slots produce denser cut paths than butt panels.
        self.assertGreater(svg.lower().count("path"), 14)

    def test_drawers_with_pull_and_size_label(self):
        from toolbox import render_toolbox

        built = build_studio_box(
            {
                "x": 180,
                "y": 100,
                "h": 120,
                "thickness": 3,
                "lid": "open",
                "dividers_x": 2,
                "shelves": 2,
                "drawers": True,
            }
        )
        self.assertTrue(built["summary"]["drawers"])
        self.assertGreaterEqual(built["summary"]["drawer_count"], 6)
        spec = built["summary"]["drawers_mm"][0]
        self.assertGreater(spec["w"], 20)
        self.assertGreater(spec["h"], 10)
        self.assertIn("×", spec["label"])
        out = render_toolbox(built["primitives"], built["parameters"])
        svg = out["svg_bytes"].decode("utf-8", errors="ignore")
        self.assertIn("drawer-1-front", svg)
        self.assertIn("drawer-1-bottom", svg)

    def test_assembly_guide_open_box(self):
        built = build_studio_box({"x": 120, "y": 80, "h": 40, "thickness": 3, "lid": "open"})
        guide = built["assembly_guide"]
        self.assertEqual(guide["physical_assembly"], "NOT_VERIFIED")
        self.assertEqual(guide["self_connection_count"], 0)
        self.assertEqual(guide["forbidden_connection_count"], 0)
        order = guide["assembly_order"]
        self.assertEqual(order[:5], ["bottom", "front", "back", "left", "right"])
        self.assertNotIn("lid", order)
        self.assertGreaterEqual(guide["connection_count"], 8)
        for c in guide["connections"]:
            self.assertNotEqual(c["part_a"], c["part_b"])
            self.assertEqual(c["digital_status"], "DECLARED")
        self.assertIn("Montaj sırası", guide["speak"])

    def test_assembly_guide_dividers_shelf_lid(self):
        built = build_studio_box(
            {
                "x": 150,
                "y": 100,
                "h": 90,
                "thickness": 3,
                "lid": "removable",
                "dividers_x": 1,
                "dividers_y": 1,
                "shelves": 1,
            }
        )
        guide = built["assembly_guide"]
        order = guide["assembly_order"]
        self.assertIn("divider-x-1", order)
        self.assertIn("divider-y-1", order)
        self.assertIn("shelf-1", order)
        self.assertIn("lid", order)
        self.assertEqual(guide["self_connection_count"], 0)
        pairs = {frozenset((c["part_a"], c["part_b"])) for c in guide["connections"]}
        self.assertIn(frozenset(("divider-x-1", "divider-y-1")), pairs)
        self.assertTrue(any(c["joint_type"] == "cross_lap" for c in guide["connections"]))
        # No top↔bottom / lid↔bottom
        self.assertNotIn(frozenset(("lid", "bottom")), pairs)
        self.assertEqual(len(guide["steps"]), len(order))

    def test_build_assembly_guide_direct(self):
        box = {
            "type": "box",
            "bottom": True,
            "lid": False,
            "dividers_x": 0,
            "dividers_y": 0,
            "shelves": 0,
            "bottom_lift": 0,
        }
        guide = build_assembly_guide(box, {"lid": "open"})
        self.assertEqual(guide["step_count"], 5)

    def test_preview_response_marks_gate_skipped(self):
        from workshop import create_studio_box

        preview = create_studio_box(
            {"x": 100, "y": 80, "h": 40, "thickness": 3, "lid": "open", "preview": True}
        )
        self.assertTrue(preview.get("preview"))
        self.assertTrue(preview.get("gate_skipped"))
        self.assertEqual(preview.get("final_status"), "PREVIEW_ONLY")
        self.assertEqual(preview.get("production_export"), "BLOCKED")
        self.assertIsNone(preview.get("file_id"))
        self.assertIn("final_gate", preview.get("scorecard") or {})

    def test_studio_calibrate_records_human_bar(self):
        import os
        import tempfile

        from studio import studio_action

        tmp = tempfile.mkdtemp()
        old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = tmp
        try:
            out = studio_action(
                "calibrate",
                payload={
                    "measured_bar_mm": 99.7,
                    "machine": "payas_workshop",
                    "material": "poplar_3mm",
                },
            )
            self.assertTrue(out.get("success"))
            self.assertIsNotNone(out.get("calibration"))
            self.assertIsNotNone(out.get("suggested_burn"))
            self.assertEqual(out["physical"]["kerf"], "PASS")
            listed = studio_action("calibrate", payload={})
            self.assertGreaterEqual(len(listed.get("rows") or []), 1)
        finally:
            if old is None:
                os.environ.pop("MCP_DATA_DIR", None)
            else:
                os.environ["MCP_DATA_DIR"] = old

    def test_render_box_with_dividers(self):
        from toolbox import render_toolbox

        built = build_studio_box(
            {"x": 100, "y": 80, "h": 40, "thickness": 3, "lid": "open", "dividers_x": 1}
        )
        out = render_toolbox(built["primitives"], built["parameters"])
        self.assertTrue(out.get("svg_bytes") or out.get("svg") or out.get("raw") or True)
        # render_toolbox returns dict with svg_bytes
        self.assertIn("svg_bytes", out)
        self.assertGreater(len(out["svg_bytes"]), 200)

    def test_svg_to_stl_keeps_mm_scale(self):
        from svg_to_stl import svg_bytes_to_stl

        # 40×30 rectangle CUT path in mm
        svg = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="40mm" viewBox="0 0 50 40">
  <path d="M 5 5 L 45 5 L 45 35 L 5 35 Z" stroke="#ff0000" fill="none" data-operation="CUT"/>
</svg>"""
        stl = svg_bytes_to_stl(svg, height_mm=2.5, ai_hint="ignore inventing width")
        self.assertEqual(stl["scale"]["units"], "mm")
        self.assertEqual(stl["height_mm"], 2.5)
        self.assertAlmostEqual(stl["ai"]["bbox_mm"]["width"], 40.0, places=1)
        self.assertAlmostEqual(stl["ai"]["bbox_mm"]["depth"], 30.0, places=1)
        self.assertTrue(stl["stl_bytes"].startswith(b"LaserMCP") or len(stl["stl_bytes"]) > 84)


if __name__ == "__main__":
    unittest.main()
