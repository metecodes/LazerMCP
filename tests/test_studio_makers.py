"""Parametric studio makers — must not use AI / LLM."""

from __future__ import annotations

import unittest

from studio_makers import MAKERS, build_maker, list_makers


class StudioMakersTest(unittest.TestCase):
    def test_catalog_is_not_ai(self):
        rows = list_makers()
        self.assertEqual(len(rows), 5)
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

    def test_birdhouse_is_a_gateable_box(self):
        built = build_maker("kus_evi", {"x": 100, "y": 90, "h": 80, "thickness": 3})
        self.assertEqual(built["mode"], "primitives")
        self.assertFalse(built["summary"]["ai"])
        box = built["primitives"][0]
        self.assertEqual(box["type"], "box")
        self.assertEqual(box["lid"], {"type": "removable"})
        hole = box["walls"]["front"]["holes"][0]
        self.assertLessEqual(hole["y"] + hole["d"] / 2, 80 - 3 * 3)

    def test_birdhouse_passes_final_gate(self):
        # The Boxes.py BirdHouse sheet was always BLOCKED; the box recipe must be downloadable.
        import os
        import tempfile
        from unittest.mock import patch

        from assembly import check_assembly

        built = build_maker("birdhouse", {"x": 120, "y": 100, "h": 100, "thickness": 3})
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"MCP_DATA_DIR": tmp, "SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}
        ):
            result = check_assembly(built["primitives"], thickness=3)
        self.assertTrue(result["ok"], result.get("look_again"))
        self.assertEqual((result.get("transform_validation") or {}).get("status"), "PASS")

    def test_undeclared_front_hole_still_needs_coaxial_back_hole(self):
        # Only declared openings skip the shaft rule; a bare hole is still an axle.
        from assembly import check_assembly

        built = build_maker("birdhouse", {"x": 120, "y": 100, "h": 100, "thickness": 3})
        built["primitives"][0]["walls"]["front"]["holes"][0].pop("purpose")
        result = check_assembly(built["primitives"], thickness=3)
        self.assertFalse(result["ok"])
        self.assertTrue(any("coaxial back hole" in str(x) for x in result.get("look_again") or []))

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

    def test_flexible_and_named_gift(self):
        flex = build_maker("esnek_kutu", {"x": 140, "y": 90, "h": 50, "thickness": 3})
        self.assertEqual(flex["summary"]["maker"], "flexible_box")
        self.assertFalse(flex["summary"]["ai"])
        self.assertEqual(flex["primitives"][0]["type"], "box")
        gift = build_maker("hediye", {"text": "Ayşe", "x": 120, "y": 80, "h": 45})
        self.assertEqual(gift["summary"]["maker"], "named_gift")
        self.assertEqual(gift["summary"]["text"], "Ayşe")
        texts = gift["parameters"].get("surface_texts") or []
        self.assertTrue(texts)
        self.assertEqual(texts[0]["text"], "Ayşe")

    def test_unknown_maker(self):
        with self.assertRaises(ValueError):
            build_maker("unicorn", {})


if __name__ == "__main__":
    unittest.main()
