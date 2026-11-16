"""The image benchmark's pure parts: validating the set and scoring one picture."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import vision_eval as ve

ROW = {"id": "photo-01", "file": "a.jpg", "kind": "photo", "about": "3 raflı kitaplık", "min_panels": 6, "max_panels": 9,
       "types": ["shelf_unit"], "size_mm": [300, 150, 400], "text": "Ada"}
GOOD = {"primitives": [{"type": "shelf_unit", "w": 320, "d": 140, "h": 380, "shelves": 3, "text": "Ada"}]}


class ScoreTests(unittest.TestCase):
    def test_a_faithful_design_passes(self):
        verdict = ve.score(ROW, GOOD, gate_ok=True, panels=7)
        self.assertTrue(verdict["passed"], verdict["problems"])

    def test_each_expectation_can_fail_on_its_own(self):
        cases = {
            "blocked": dict(plan=GOOD, gate_ok=False, panels=0),
            "parts:5<6": dict(plan=GOOD, gate_ok=True, panels=5),
            "parts:12>9": dict(plan=GOOD, gate_ok=True, panels=12),
            "type:box": dict(plan={"primitives": [{"type": "box", "x": 300, "y": 150, "h": 400, "note": "Ada"}]}, gate_ok=True, panels=7),
            "size": dict(plan={"primitives": [{"type": "shelf_unit", "w": 90, "d": 60, "h": 100, "text": "Ada"}]}, gate_ok=True, panels=7),
            "text": dict(plan={"primitives": [{"type": "shelf_unit", "w": 300, "d": 150, "h": 400}]}, gate_ok=True, panels=7),
        }
        for problem, case in cases.items():
            with self.subTest(problem):
                self.assertEqual(ve.score(ROW, **case)["problems"], [problem])

    def test_a_model_error_is_reported_not_scored_as_blocked(self):
        verdict = ve.score(ROW, None, gate_ok=False, panels=0, error="HTTP 500")
        self.assertEqual(verdict["problems"], ["error:HTTP 500"])

    def test_optional_fields_are_optional(self):
        row = {"id": "s", "file": "s.png", "kind": "sketch", "about": "kutu", "min_panels": 5, "max_panels": 6}
        self.assertTrue(ve.score(row, {"primitives": [{"type": "box", "x": 1, "y": 1, "h": 1}]}, True, 5)["passed"])


class SetTests(unittest.TestCase):
    def test_the_shipped_set_is_valid(self):
        self.assertEqual(ve.check_rows(ve.load_rows(), ve.SET_DIR / "images"), [])

    def test_bad_rows_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "a.jpg").write_bytes(b"x")
            (folder / "b.gif").write_bytes(b"x")
            rows = [
                dict(ROW),
                {**ROW, "id": "photo-01"},
                {**ROW, "id": "p3", "kind": "painting"},
                {**ROW, "id": "p4", "file": "missing.jpg"},
                {**ROW, "id": "p5", "file": "b.gif"},
                {**ROW, "id": "p6", "min_panels": 4, "max_panels": 2},
                {**ROW, "id": "p7", "size_mm": [300, 150]},
                {**ROW, "id": "p8", "about": " "},
            ]
            text = "\n".join(ve.check_rows(rows, folder))
        for needle in ("photo-01: id is missing or repeated", "p3: kind must be", "p4: image file", "p5: .gif", "p6: min_panels", "p7: size_mm", "p8: about"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
