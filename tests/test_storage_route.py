"""Storage boxes with drawers, compartments or levels go to the box engine, not the small model."""

import os
import tempfile
import unittest
from unittest import mock

import llm_client
from ai_cache import parse_storage_request


class ParseTests(unittest.TestCase):
    def test_drawers_compartments_and_levels(self):
        one = parse_storage_request("çekmeceli kutu 200x150x80")
        self.assertEqual((one["x"], one["y"], one["h"], one["shelves"], one["drawers"], one["lid"]), (200, 150, 80, 0, True, "finger"))
        self.assertEqual(parse_storage_request("2 çekmeceli masaüstü düzenleyici")["shelves"], 1)
        self.assertEqual(parse_storage_request("box with two drawers 30x20x15 cm")["x"], 300)
        tea = parse_storage_request("çay poşeti kutusu, 6 bölmeli, kapaklı")
        self.assertEqual((tea["dividers_x"], tea["dividers_y"], tea["drawers"], tea["lid"]), (2, 1, False, "finger"))
        self.assertEqual(parse_storage_request("3 bölmeli kalemlik")["dividers_x"], 2)
        jewel = parse_storage_request("takı kutusu, içi 2 katlı")
        self.assertEqual((jewel["x"], jewel["shelves"], jewel["drawers"]), (160, 1, True))

    def test_everything_else_stays_with_the_model(self):
        for prompt in (
            "120x80x60 kapaklı kutu",                         # plain box: its own route
            "desk organizer with 3 compartments and a drawer",  # both: the engine cannot do it
            "çekmeceli robot kutusu, motor ve tekerlek",
            "Arduino için 3 bölmeli kutu, LED delikli",
            "gözlük kutusu",
            "telefon standı",
        ):
            self.assertIsNone(parse_storage_request(prompt), prompt)


class RouteTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"MCP_DATA_DIR": tempfile.mkdtemp(prefix="storage-route-")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_drawer_box_is_built_without_a_model_call(self):
        import workshop

        with mock.patch("llm_client.plan_primitives_with_llm") as model:
            reply = workshop.create_studio_ai({"prompt": "2 çekmeceli masaüstü düzenleyici", "thickness": 3}, client_ip="t")
            model.assert_not_called()
        self.assertEqual(reply["plan_job"]["method"], "studio_box")
        self.assertNotIn(str(reply.get("final_status")), {"BLOCKED", "FAIL"})
        self.assertGreaterEqual(len(reply["assembly"]["panels"]), 9)


class PartFactTests(unittest.TestCase):
    def test_part_names_are_not_read_as_sizes(self):
        text = llm_client.request_text("16x2 LCD ekran için ön panelli kutu", 3)
        self.assertIn("board 80x36 mm", text)
        self.assertTrue(text.endswith("\nMaterial thickness_mm=3.0"))
        self.assertIn("SG90 servo", llm_client.request_text("SG90 servo için braket"))
        self.assertEqual(llm_client.request_text(llm_client.request_text("SG90 braket")).count("SG90 servo:"), 1)
        self.assertNotIn("Part sizes", llm_client.request_text("120x80x60 kutu"))


if __name__ == "__main__":
    unittest.main()
