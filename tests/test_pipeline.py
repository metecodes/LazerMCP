"""Photo → plan → design must not silently draw the wrong thing."""

from __future__ import annotations

import os
import tempfile
import unittest


class PlannerPhotoTests(unittest.TestCase):
    def test_photo_without_parts_is_not_traced(self):
        from job_planner import plan_laser_job

        plan = plan_laser_job("bunu kes", has_photo=True)
        self.assertNotEqual(plan.get("next_tool"), "create_from_reference")
        self.assertEqual(plan.get("next_tool"), "plan_laser_job")
        self.assertIn("what_you_see", str(plan.get("look_again") or "").lower() + str(plan.get("summary") or "").lower())

    def test_photo_of_open_box_composes(self):
        from job_planner import plan_laser_job

        plan = plan_laser_job(
            "180 mm açık kutu",
            what_you_see="dört duvar ve taban, kapak yok",
            has_photo=True,
        )
        self.assertEqual(plan.get("next_tool"), "create_design")
        self.assertEqual(plan.get("method"), "compose_primitives")
        prims = (plan.get("next_arguments") or {}).get("primitives") or []
        self.assertTrue(any(isinstance(p, dict) and p.get("type") == "box" for p in prims))

    def test_named_kit_beats_photo_trace(self):
        from job_planner import plan_laser_job

        plan = plan_laser_job("robot kumbara fotoğrafı", what_you_see="para yarığı ve LED", has_photo=True)
        self.assertEqual(plan.get("next_tool"), "create_robot_bank")

    def test_logo_photo_may_trace(self):
        from job_planner import plan_laser_job

        plan = plan_laser_job("sadece logo 2d iz", has_photo=True)
        self.assertEqual(plan.get("next_tool"), "create_from_reference")

    def test_compact_mill_is_not_a_disc(self):
        from seen import check_what_you_see

        notes = check_what_you_see(
            [{"type": "disc", "d": 80}],
            "fotoğrafta 4 kanatlı pervane ve eğimli çatı",
        )
        self.assertTrue(any(n["status"] == "FAIL" for n in notes))


class SimpleDesignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = self.tmp

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MCP_DATA_DIR", None)
        else:
            os.environ["MCP_DATA_DIR"] = self.old

    def test_simple_open_box_is_prototype(self):
        from payas_cad import create_design

        result = create_design(
            primitives=[{"type": "box", "x": 180, "y": 120, "h": 80, "bottom": True}],
            parameters={"material": "poplar_3mm", "machine": "payas_workshop", "what_you_see": "dört duvar ve taban"},
            public_base_url="http://127.0.0.1:8000",
        )
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("final_status"), "PROTOTYPE READY")
        self.assertEqual(result["review"]["categories"]["ASSEMBLY"]["status"], "PASS")
        self.assertEqual(result["review"]["categories"]["3D_ASSEMBLY"]["status"], "PASS")
        self.assertIsNotNone(result["assembly"].get("assembled_preview_svg"))
        self.assertNotEqual(result.get("final_status"), "PRODUCTION READY")
        self.assertTrue(result.get("file_id"))

    def test_door_photo_without_slot_is_blocked(self):
        from payas_cad import create_design

        result = create_design(
            primitives=[{"type": "box", "x": 70, "y": 50, "h": 80, "bottom": True}],
            parameters={"what_you_see": "ön yüzde kapı var"},
            public_base_url="http://127.0.0.1:8000",
        )
        self.assertTrue(result.get("success"))
        looks = " ".join(str(x) for x in (result.get("look_again") or []))
        self.assertTrue(looks or result.get("final_status") == "BLOCKED")
