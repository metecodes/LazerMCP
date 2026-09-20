import unittest

from linear_motion import validate
from topology import inspect_topology
from nesting import nest_svg


def panel(label, w, h, origin, moving=False):
    return {"type": "panel", "label": label, "w": w, "h": h, "edges": "eeee", "moving": moving,
            "placement": {"origin": list(origin), "u": [1, 0, 0], "v": [0, 1, 0]}}


class PrecisionValidationTests(unittest.TestCase):
    def test_continuous_slide_finds_collision_between_sample_positions(self):
        parts = [panel("moving", 10, 10, (0, 0, 0), True), panel("thin-obstacle", 2, 10, (17, 0, 0))]
        params = {"connections": [{"id": "slide", "type": "linear_slide", "moving_part": "moving",
                                    "rails": ["rail"], "axis": [1, 0, 0], "travel_mm": 100,
                                    "clearance_mm": 0}],}
        parts.append(panel("rail", 110, 2, (0, 20, 0)))
        result = validate(parts, params, 3)
        self.assertEqual(result["status"], "FAIL")
        hit = next(c for c in result["slides"][0]["collisions"] if c["part"] == "thin-obstacle")
        self.assertEqual(hit["kind"], "continuous-static-moving")
        self.assertTrue(hit["travel_range_mm"][0] < 17 < hit["travel_range_mm"][1])

    def test_topology_checks_every_subpath_and_adaptive_curves(self):
        svg = b'''<svg xmlns="http://www.w3.org/2000/svg"><path data-operation="CUT" data-operation-source="explicit" stroke="#FF0000"
          d="M0 0 L10 0 L10 10 L0 10 Z M20 0 C40 30 0 30 20 0 Z M50 0 L55 0"/></svg>'''
        result = inspect_topology(svg)
        self.assertFalse(result["ok"])
        self.assertEqual(result["open_cuts"][0]["subpath"], 3)

    def test_nesting_rotates_a_part_that_only_fits_at_ninety_degrees(self):
        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="70mm" height="40mm" viewBox="0 0 70 40">
          <g data-panel="long"><path data-operation="CUT" d="M0 0 L70 0 L70 40 L0 40 Z"/></g></svg>'''
        out, info = nest_svg(svg, bed_width=60, bed_height=100, gap=3, margin=5, panel_names=["long"])
        self.assertTrue(info["ok"], info.get("errors"))
        self.assertEqual(info["placements"][0]["rotation_deg"], 90)
        self.assertLessEqual(info["occupied_mm"][0], 60)
        self.assertLessEqual(info["occupied_mm"][1], 100)
        self.assertIn(b'data-panel="long"', out)


if __name__ == "__main__":
    unittest.main()
