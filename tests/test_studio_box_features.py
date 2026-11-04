"""Studio parametric box features + mm-scaled SVG→STL."""

from __future__ import annotations

import unittest

from studio_box import build_studio_box, equal_cells, resolve_inner_outer, volume_liters


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
