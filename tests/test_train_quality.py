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
        self.assertEqual(train.quality_problems("3 mm MDF bebek evi masası", [{"type": "panel", "w": 80, "h": 50}]), [])

    def test_requested_text_must_be_engraved(self):
        plate = {"type": "panel", "w": 220, "h": 70}
        self.assertTrue(train.quality_problems("üzerinde 'Atölye' yazan kapı isimliği yap", [plate]))
        marked = {**plate, "markings": [{"kind": "text", "value": "ATÖLYE"}]}
        self.assertEqual(train.quality_problems("üzerinde 'Atölye' yazan kapı isimliği yap", [marked]), [])


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
        good = {"prompt_id": "a", "prompt": "bana bir duvar rafı", "kind": "draft", "user": "u1", "assistant": train.answer_json({"primitives": [{"type": "box", "x": 300, "y": 100, "h": 120}]})}
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
