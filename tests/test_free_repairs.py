"""Code-only repairs for the mistakes a small model makes most (found in the first pilot run)."""

import os
import tempfile
import unittest
from unittest import mock

import llm_client
import seen
import workshop

HOLE_NOTE = "hole on P01/front at 3.0,3.0 d=4.0 leaves the wall"
AXLE_NOTE = "front hole d=4.0 y=3.0 has no coaxial back hole (same d, same height)"


def _box(**walls):
    return {"type": "box", "x": 120, "y": 80, "h": 60, "lid": False, "walls": walls}


class PullInsideTests(unittest.TestCase):
    def test_hole_on_the_edge_moves_inside_and_good_holes_stay(self):
        prims = [_box(front={"holes": [{"x": 3, "y": 3, "d": 4}, {"x": 60, "y": 30, "d": 4}]})]
        fixed = workshop._pull_features_inside(prims, [HOLE_NOTE], 3.0)
        holes = fixed[0]["walls"]["front"]["holes"]
        self.assertEqual((holes[0]["x"], holes[0]["y"]), (7.5, 7.5))
        self.assertEqual((holes[1]["x"], holes[1]["y"]), (60, 30))
        self.assertEqual(prims[0]["walls"]["front"]["holes"][0]["x"], 3)  # the draft itself is not edited

    def test_side_walls_use_depth_and_bottom_uses_the_footprint(self):
        prims = [{**_box(left={"holes": [{"x": 200, "y": 30, "d": 4}]}), "bottom": {"holes": [{"x": 0, "y": 200, "d": 6}]}}]
        fixed = workshop._pull_features_inside(prims, ["hole on P01/bottom leaves its actual outline"], 3.0)
        self.assertEqual(fixed[0]["walls"]["left"]["holes"][0]["x"], 80 - 5.5 - 2)
        self.assertEqual(fixed[0]["bottom"]["holes"][0], {"x": 8.5, "y": 80 - 8.5, "d": 6})

    def test_slot_wider_than_its_wall_is_cut_down(self):
        prims = [_box(front={"slots": [{"x": 50, "y": 50, "w": 160, "h": 10}]})]
        slot = workshop._pull_features_inside(prims, ["slot on P01/front at 50.0,50.0 160.0×10.0 leaves the wall"], 3.0)[0]["walls"]["front"]["slots"][0]
        self.assertEqual((slot["w"], slot["x"], slot["h"]), (109.0, 60.0, 10))

    def test_feature_that_cannot_fit_is_left_out(self):
        prims = [{"type": "panel", "w": 12, "h": 12, "edges": "eeee", "holes": [{"x": 6, "y": 6, "d": 8}]}]
        fixed = workshop._pull_features_inside(prims, ["hole on plate leaves its actual outline"], 3.0)
        self.assertEqual(fixed[0]["holes"], [])

    def test_nothing_changes_without_a_matching_gate_note(self):
        prims = [_box(front={"holes": [{"x": 3, "y": 3, "d": 4}]})]
        self.assertIsNone(workshop._pull_features_inside(prims, ["P02 role=structural has mates=[]"], 3.0))
        ok = [_box(front={"holes": [{"x": 60, "y": 30, "d": 4}]})]
        self.assertIsNone(workshop._pull_features_inside(ok, [HOLE_NOTE], 3.0))


class MountHoleTests(unittest.TestCase):
    def test_bare_front_hole_becomes_a_mounting_hole_when_nothing_turns(self):
        prims = [_box(front={"holes": [{"x": 20, "y": 20, "d": 4}, {"x": 40, "y": 20, "d": 4, "purpose": "vent"}]})]
        holes = workshop._declare_mount_holes(prims, [AXLE_NOTE], "vida delikli devre kutusu")[0]["walls"]["front"]["holes"]
        self.assertEqual([h["purpose"] for h in holes], ["mount", "vent"])

    def test_requests_with_a_turning_part_are_left_to_the_model(self):
        prims = [_box(front={"holes": [{"x": 20, "y": 20, "d": 4}]})]
        for request in ("4 tekerlekli oyuncak araba", "toy car with turning wheels", "motor tutucu"):
            self.assertIsNone(workshop._declare_mount_holes(prims, [AXLE_NOTE], request), request)

    def test_only_applies_to_the_axle_note(self):
        prims = [_box(front={"holes": [{"x": 20, "y": 20, "d": 4}]})]
        self.assertIsNone(workshop._declare_mount_holes(prims, [HOLE_NOTE], "kutu"))


class GateTests(unittest.TestCase):
    """The same drafts through the real compiler and gate: refused before, approved after."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"MCP_DATA_DIR": tempfile.mkdtemp(prefix="free-repair-")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _repair(self, prims, request):
        drafts = workshop._PaidDrafts(thickness=3, parameters={"project": "t", "thickness": 3.0}, base="")
        plan = {"primitives": prims, "parameters": {}}
        first = drafts.design(plan)
        self.assertTrue(workshop._draft_blocked(first))
        with mock.patch("llm_client.plan_primitives_with_llm") as model:
            _plan, result, info = drafts.repair(request, plan, first, model_id="gpt-4o-mini", client_ip="t")
            model.assert_not_called()
        return result, info

    def test_edge_hole_on_a_screw_box_is_fixed_without_a_model_call(self):
        result, info = self._repair([_box(front={"holes": [{"x": 3, "y": 3, "d": 4}]})], "M3 vida delikli devre kutusu")
        self.assertFalse(workshop._draft_blocked(result))
        self.assertEqual((info["fixed"], info.get("free"), info["attempted"]), (True, True, 0))

    def test_drain_holes_outside_the_bottom_are_fixed_without_a_model_call(self):
        box = {"type": "box", "x": 120, "y": 120, "h": 100, "lid": False, "bottom": {"holes": [{"x": 0, "y": 0, "d": 6}, {"x": 120, "y": 120, "d": 6}]}}
        result, info = self._repair([box], "altı delikli saksı kılıfı")
        self.assertFalse(workshop._draft_blocked(result))
        self.assertTrue(info.get("free"))


class DoorSignTests(unittest.TestCase):
    def _fails(self, text):
        return [r for r in seen.check_what_you_see([{"type": "panel", "w": 200, "h": 60, "edges": "eeee"}], text) if r["status"] == "FAIL"]

    def test_a_door_sign_is_not_a_request_for_a_door(self):
        for text in ("iki vida delikli kapı isimliği", "door sign for the workshop", "kapı askısı"):
            self.assertEqual(self._fails(text), [], text)

    def test_a_real_door_or_window_still_needs_an_opening(self):
        for text in ("kapı girişli kedi evi", "pencereli periskop gövdesi", "night light box with windows"):
            self.assertTrue(self._fails(text), text)


class RequestTextTests(unittest.TestCase):
    def test_centimetre_sizes_get_a_millimetre_line(self):
        self.assertIn("\nSizes in mm: 275x30x105", llm_client.request_text("küçük 27.5x3x10.5 cm anahtar askılığı yap"))
        self.assertIn("\nSizes in mm: 120x80x60", llm_client.request_text("12cm x 8cm x 6cm kutu"))

    def test_millimetre_and_unitless_sizes_are_left_alone(self):
        for prompt in ("140x110x70 mm kontrol kutusu", "telefon standı", "120x80x60 kutu"):
            self.assertNotIn("Sizes in mm", llm_client.request_text(prompt), prompt)

    def test_thickness_line_stays_last_and_the_hint_is_added_once(self):
        text = llm_client.request_text("lamp body, 11x16x24.5 cm", 3)
        self.assertTrue(text.endswith("\nMaterial thickness_mm=3.0"))
        self.assertEqual(llm_client.request_text(text).count("Sizes in mm"), 1)


if __name__ == "__main__":
    unittest.main()
