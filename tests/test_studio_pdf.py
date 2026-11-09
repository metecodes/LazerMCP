"""Control-print PDF is digital-only and does not claim physical PASS."""

from __future__ import annotations

import unittest

from studio_pdf import control_sheet_png, create_studio_pdf


class StudioPdfTests(unittest.TestCase):
    def test_png_and_pdf_bytes(self):
        png = control_sheet_png(
            summary={"x_inner_mm": 100, "y_inner_mm": 80, "h_inner_mm": 50,
                     "x_outer_mm": 106, "y_outer_mm": 86, "h_outer_mm": 56},
            nesting={"occupied_mm": [200, 120], "placements": [
                {"x": 0, "y": 0, "w": 100, "h": 50, "label": "bottom"},
                {"x": 106, "y": 0, "w": 80, "h": 50, "label": "front"},
            ]},
            file_id="demo.svg",
        )
        self.assertTrue(png.startswith(b"\x89PNG"))
        built = create_studio_pdf(
            summary={"x_outer_mm": 106, "y_outer_mm": 86, "h_outer_mm": 56},
            nesting={"occupied_mm": [200, 120], "placements": [{"x": 0, "y": 0, "w": 40, "h": 20}]},
            file_id="demo.svg",
        )
        self.assertTrue(built["success"])
        self.assertTrue(built["pdf_bytes"].startswith(b"%PDF"))
        self.assertEqual(built["physical"], "NOT_VERIFIED")
        self.assertIn("NOT_VERIFIED", built["note"])


if __name__ == "__main__":
    unittest.main()
