import unittest
from copy import deepcopy
from unittest.mock import patch
from design_contract import snapshot, compare
from connection_validation import validate
from pipeline import run_pipeline


class DesignContractTests(unittest.TestCase):
    def test_dimensions_and_identity_are_product_independent(self):
        import random
        rng = random.Random(2026)
        for index in range(100):
            part = {"type":"panel", "label":f"part-{index}", "w":rng.uniform(20,800),
                    "h":rng.uniform(20,800), "ports":[{"id":"connector", "x":rng.uniform(5,15)}]}
            baseline = snapshot([part])
            self.assertEqual(compare(baseline, [deepcopy(part)])["status"], "PASS")
            altered = deepcopy(part)
            altered["ports"][0]["x"] += 1
            self.assertEqual(compare(baseline, [altered])["status"], "FAIL")

    def test_feature_migration_and_dimension_changes_are_detected(self):
        original = [{"type":"panel","label":"one","w":96,"ports":[{"id":"usb","x":20}]},
                    {"type":"panel","label":"two","w":115,"ports":[]}]
        altered = deepcopy(original)
        altered[1]["ports"] = altered[0].pop("ports")
        altered[0]["w"] = 115
        report = compare(snapshot(original), altered)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual({c["field"] for c in report["changes"]}, {"ports", "w"})

    def test_generated_cut_geometry_does_not_change_intent(self):
        original = [{"type":"panel","label":"one","w":100,"h":70}]
        altered = deepcopy(original)
        altered[0].update(edges="fFeF", _cut_geometry={"points":[[1,2]]})
        self.assertEqual(compare(snapshot(original), altered)["status"], "PASS")

    def test_unknown_connection_cannot_disappear_from_gate(self):
        report = validate([], {"connections":[{"type":"unimplemented_hinge"}]}, {}, {})
        self.assertTrue(any(c["status"] == "FAIL" and "UNSUPPORTED_CONNECTION_TYPE" in c["note"] for c in report["checks"]))

    def test_pipeline_rejects_repair_that_moves_a_port(self):
        parts = [{"type":"panel","label":"board","w":90,"h":60,"ports":[{"id":"usb","x":20}]}]
        altered = deepcopy(parts)
        altered[0]["ports"][0]["x"] = 40
        report = {"final_status":"BLOCKED","counts":{"pass":0,"warning":0,"fail":1,"not_verified":0}}
        with patch("toolbox.render_toolbox", return_value={"primitives":parts}), patch("review.review_built", return_value=report), patch("repair.repair_primitives", return_value=(altered,[{"fix":"move_port"}])):
            built = run_pipeline(parts)
        self.assertEqual(built["primitives"], parts)
        self.assertEqual(built["final_status"], "BLOCKED")
        self.assertEqual(built["pipeline"]["iterations"][-1]["contract"]["status"], "FAIL")
