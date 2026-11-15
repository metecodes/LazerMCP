"""Gate-approved is not the same as faithful: what may become a training example."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import train

EXAMPLE_BOX = {"type": "box", "x": 180, "y": 120, "h": 70, "lid": True, "edges": "ffff"}
EXAMPLE_PANEL = {"type": "panel", "w": 100, "h": 40, "edges": "eeee", "holes": [{"x": 50, "y": 34, "d": 4}], "markings": [{"kind": "text", "value": "Name"}]}


class QualityTests(unittest.TestCase):
    def test_the_system_prompt_example_is_not_an_answer(self):
        self.assertIn("copies the example box from the system prompt", train.quality_problems("takı kutusu istiyorum", [EXAMPLE_BOX]))
        got = train.quality_problems("büyük bebek evi sandalyesi", [EXAMPLE_BOX, EXAMPLE_PANEL])
        self.assertIn("copies the example panel from the system prompt", got)
        self.assertIn("copies the example text Name", got)

    def test_the_same_box_is_fine_when_it_was_asked_for(self):
        self.assertEqual(train.quality_problems("180x120x70 kutu", [EXAMPLE_BOX]), [])

    def test_stated_sizes_must_show_up_in_the_design(self):
        self.assertEqual(train.quality_problems("küçük 9.5x7x8 cm mumluk", [{"type": "box", "x": 95, "y": 70, "h": 80}]), [])
        self.assertTrue(train.quality_problems("küçük 9.5x7x8 cm mumluk", [{"type": "box", "x": 9.5, "y": 7, "h": 8}]))
        self.assertTrue(train.quality_problems("dollhouse chair, 60 mm tall", [{"type": "box", "x": 120, "y": 80, "h": 120}]))
        # Inner vs outer size and a flat part that uses two of three sizes still count.
        self.assertEqual(train.quality_problems("140x110x70 mm kutu", [{"type": "box", "x": 134, "y": 104, "h": 67}]), [])
        self.assertEqual(train.quality_problems("195x15x275 mm fotoğraf çerçevesi", [{"type": "panel", "w": 195, "h": 275}]), [])

    def test_material_thickness_is_not_a_size_to_honour(self):
        table = [{"type": "panel", "w": 80, "h": 50, "edges": "eeee"}, {"type": "panel", "w": 40, "h": 45, "count": 4, "label": "leg"}]
        self.assertEqual(train.quality_problems("3 mm MDF bebek evi masası", table), [])

    def test_requested_text_must_be_engraved(self):
        plate = {"type": "panel", "w": 220, "h": 70}
        self.assertTrue(train.quality_problems("üzerinde 'Atölye' yazan kapı isimliği yap", [plate]))
        marked = {**plate, "markings": [{"kind": "text", "value": "ATÖLYE"}]}
        self.assertEqual(train.quality_problems("üzerinde 'Atölye' yazan kapı isimliği yap", [marked]), [])


class ShapeTests(unittest.TestCase):
    """Pilot rows that the gate and the size check kept, but that teach the wrong thing."""

    PLAIN = {"type": "box", "x": 110, "y": 100, "h": 80, "lid": False, "edges": "ffff"}

    def test_a_lone_box_is_not_a_stand_shelf_chair_or_bridge(self):
        for prompt in ("11x10x8 cm telefon standı çiz", "bir 615x225x345 mm ayakkabılık rafı yap", "35x55x80 mm bebek evi sandalyesi", "110 mm yükseklik köprü maketi lazım", "pinwheel stand, 110 mm wide", "masaüstü düzenleyici"):
            with self.subTest(prompt=prompt):
                self.assertTrue(any(p.startswith("draws a single box") for p in train.quality_problems(prompt, [self.PLAIN])))

    def test_word_bounds_keep_box_objects_box(self):
        # "fotoğraf" is not "raf", "masaüstü" not "masa", "card" not "car", "design" not "sign".
        for prompt in ("fotoğraf kutusu", "masaüstü kalemlik", "playing card box", "jewelry box design", "8.5x8x3 cm Arduino Uno kutusu"):
            with self.subTest(prompt=prompt):
                self.assertEqual(train.shape_problems(prompt, [{"type": "box", "x": 85, "y": 80, "h": 30}]), [])

    def test_one_flat_sheet_is_not_a_3d_object_but_a_sign_may_be(self):
        sheet = [{"type": "panel", "w": 1200, "h": 300, "edges": "eeee"}]
        self.assertIn("draws one flat part for a 3D object", train.shape_problems("masaüstü düzenleyici", sheet))
        self.assertIn("draws one flat part for a 3D object", train.shape_problems("15 derece eğimli telefon standı", sheet))
        self.assertEqual(train.shape_problems("kapı isimliği", [{"type": "panel", "w": 220, "h": 70}]), [])

    def test_requested_features_must_be_in_the_design(self):
        self.assertIn("is one part, but the request needs more (compartments, shelves, a drawer, hooks or a support)", train.shape_problems("tool tray with 6 compartments", [self.PLAIN]))
        self.assertIn("has no hole, slot or port although one was asked for", train.shape_problems("arkasında kablo deliği olan kalemlik", [self.PLAIN]))
        self.assertIn("has no lid", train.shape_problems("kapaklı takı kutusu", [self.PLAIN]))
        self.assertIn("has no wheel", train.shape_problems("4 tekerlekli oyuncak araba", [self.PLAIN, {"type": "panel", "w": 40, "h": 20}]))
        self.assertNotIn("has no wheel", train.shape_problems("pinwheel stand", [self.PLAIN]))
        holed = {**self.PLAIN, "walls": {"back": {"holes": [{"x": 50, "y": 20, "d": 8, "purpose": "cable"}]}}}
        self.assertEqual(train.shape_problems("arkasında kablo deliği olan kalemlik", [holed]), [])
        trays = [self.PLAIN, {"type": "panel", "w": 104, "h": 74, "count": 5, "label": "divider"}]
        self.assertEqual(train.shape_problems("tool tray with 6 compartments", trays), [])
        self.assertEqual(train.shape_problems("kapaklı takı kutusu", [{**self.PLAIN, "lid": True}]), [])
        self.assertIn("has no lid", train.shape_problems("kapaklı takı kutusu", [{**self.PLAIN, "lid": "false"}]))

    def test_broken_parts_never_train(self):
        got = train.quality_problems("takı kutusu", ["box", {"type": "box", "x": 175, "y": 0, "h": 175}])
        self.assertIn("has a part that is not an object with a type", got)
        self.assertIn("has a box with y = 0", got)
        row = {"prompt": "takı kutusu", "user": "u", "assistant": json.dumps({"primitives": ["box"]})}
        self.assertFalse(train.usable(row))


class LockTests(unittest.TestCase):
    def test_a_second_collect_on_the_same_folder_is_refused(self):
        out = Path(tempfile.mkdtemp(prefix="train-lock-"))
        first = train._take_lock(out)
        self.assertIsNotNone(first)
        self.assertIsNone(train._take_lock(out))
        first.unlink()
        again = train._take_lock(out)
        self.assertIsNotNone(again)
        again.unlink()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="train-quality-")
        patcher = mock.patch.dict(os.environ, {"MCP_DATA_DIR": tempfile.mkdtemp(prefix="train-data-"), "LASERMCP_AI_CACHE_DAYS": "0"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_parroted_draft_passes_the_gate_but_is_not_collected(self):
        plan = {"primitives": [dict(EXAMPLE_BOX)], "parameters": {}, "summary": "", "usage": {}}
        row = {"id": "t1-00001", "prompt": "bana bir duvar rafı", "thickness": 3.0}
        detail = {}
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=lambda *a, **k: json.loads(json.dumps(plan))):
            examples, _usd, why = train.collect_one(row, "gpt-5.5", "medium", detail)
        self.assertEqual(examples, [])
        self.assertTrue(why.startswith("quality:"))
        self.assertTrue(detail["notes"][0].startswith("quality: copies the example box"))

    def test_rows_collected_before_the_check_are_left_out_of_training_and_reported(self):
        good = {"prompt_id": "a", "prompt": "bana bir kalemlik", "kind": "draft", "user": "u1", "assistant": train.answer_json({"primitives": [{"type": "box", "x": 300, "y": 100, "h": 120}]})}
        bad = {"prompt_id": "b", "prompt": "takı kutusu istiyorum", "kind": "draft", "user": "u2", "assistant": train.answer_json({"primitives": [EXAMPLE_BOX]})}
        self.assertTrue(train.usable(good))
        self.assertFalse(train.usable(bad))
        for row in (good, bad):
            train._append(Path(self.tmp) / train.EXAMPLES, row)
        report = train.build_report(Path(self.tmp))
        self.assertIn("faithful to the request: 1 of 2", report)
        self.assertIn("takı kutusu istiyorum: copies the example box", report)


if __name__ == "__main__":
    unittest.main()
