"""Parametric studio makers — must not use AI / LLM."""

from __future__ import annotations

import unittest

from studio_makers import MAKERS, build_maker, list_makers


class StudioMakersTest(unittest.TestCase):
    def test_catalog_is_not_ai(self):
        rows = list_makers()
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertFalse(row.get("ai"))
            self.assertIn(row["id"], MAKERS)

    def test_name_ornament_primitives(self):
        built = build_maker("isim", {"text": "Ayşe", "width": 100, "height": 36, "thickness": 3})
        self.assertEqual(built["mode"], "primitives")
        self.assertFalse(built["summary"]["ai"])
        panel = built["primitives"][0]
        self.assertEqual(panel["type"], "panel")
        self.assertTrue(panel["holes"])
        self.assertEqual(panel["markings"][0]["value"], "Ayşe")
        self.assertEqual(panel["markings"][0]["operation"], "engrave")

    def test_birdhouse_generator(self):
        built = build_maker("kus_evi", {"x": 100, "y": 90, "h": 80, "thickness": 3})
        self.assertEqual(built["mode"], "generator")
        self.assertEqual(built["generator"], "BirdHouse")
        self.assertFalse(built["summary"]["ai"])
        self.assertIn("roof_overhang", built["parameters"])

    def test_christmas_star_contour(self):
        built = build_maker("christmas", {"shape": "star", "size": 70, "text": "2026"})
        self.assertEqual(built["mode"], "primitives")
        part = built["primitives"][0]
        self.assertEqual(part["type"], "contour")
        self.assertGreaterEqual(len(part["points"]), 10)
        self.assertTrue(part["holes"])
        self.assertEqual(part["markings"][0]["value"], "2026")

    def test_christmas_circle(self):
        built = build_maker("xmas", {"shape": "circle", "size": 60})
        part = built["primitives"][0]
        self.assertEqual(part["type"], "contour")
        self.assertGreaterEqual(len(part["points"]), 24)

    def test_unknown_maker(self):
        with self.assertRaises(ValueError):
            build_maker("unicorn", {})


if __name__ == "__main__":
    unittest.main()
