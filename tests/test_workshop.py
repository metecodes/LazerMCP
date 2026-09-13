import os
import tempfile
import unittest


class WorkshopLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = self.tmp

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MCP_DATA_DIR", None)
        else:
            os.environ["MCP_DATA_DIR"] = self.old

    def test_onboard_machine_then_material(self):
        from workshop import get_onboarding, save_onboarding

        first = save_onboarding(
            {"brand": "ACME", "model": "9060", "bed_w": 900, "bed_h": 600},
            {"id": "u1"},
        )
        self.assertEqual(first["next"], "material")
        self.assertEqual(first["onboarding"]["bed_w"], 900)
        mid = first["onboarding"]["machine"]
        second = save_onboarding({"machine": mid, "material": "mdf_3mm", "thickness": 3.1}, {"id": "u1"})
        self.assertEqual(second["onboarding"]["material"], "mdf_3mm")
        self.assertEqual(second["next"], "coupon")
        self.assertTrue(get_onboarding({"id": "u1"})["onboarding"]["machine"])

    def test_batch_kerf_is_human_only(self):
        from catalog import upsert_batch
        from profiles import resolve_material

        with self.assertRaises(ValueError):
            upsert_batch({"material": "mdf_3mm", "kerf": 2.0})
        batch = upsert_batch(
            {"id": "batch_21", "material": "mdf_3mm", "supplier": "X", "lot": "21", "measured_thickness": 2.8, "kerf": 0.22}
        )
        mat = resolve_material({"material": "mdf_3mm", "batch_id": batch["id"]})
        self.assertEqual(mat["thickness"], 2.8)
        self.assertEqual(mat["kerf"], 0.22)

    def test_feedback_does_not_invent_pass(self):
        from workshop import record_feedback

        out = record_feedback(
            {"fit": "seated", "project_id": "job-1", "machine": "payas_workshop", "material": "poplar_3mm"},
            {"id": "u1"},
        )
        self.assertFalse(out["feedback"]["physical_pass"])
        self.assertIn("not a software PASS", out["look_again"][0])

    def test_preflight_software_pass_human_unverified(self):
        from review import NOT_VERIFIED, PASS
        from workshop import preflight

        out = preflight(
            {
                "scorecard": {
                    "digital": {"Digital Geometry": PASS, "Connections": PASS},
                    "physical": {"Physical Kerf Test": NOT_VERIFIED},
                }
            }
        )
        self.assertEqual(out["result"], PASS)
        self.assertEqual(out["human"][0]["status"], NOT_VERIFIED)

    def test_revision_keeps_prior_version(self):
        from projects import project_history, save_version
        from workshop import apply_revision

        save_version(
            {"project": "mill", "project_id": "mill-aa"},
            {"file_id": "a.svg", "primitives": [{"type": "panel", "label": "front", "x": 80, "y": 40}]},
        )
        out = apply_revision({"project_id": "mill-aa", "part": "front", "op": "extend", "mm": 10, "dim": "x"})
        self.assertEqual(out["primitives"][0]["x"], 90)
        hist = project_history("mill-aa")
        self.assertGreaterEqual(len(hist["versions"]), 2)

    def test_revision_by_file_and_part_id(self):
        from projects import project_by_file, save_version
        from workshop import apply_revision, editor_context

        save_version(
            {"project": "mill", "project_id": "mill-file"},
            {"file_id": "cut-aa.svg", "primitives": [{"type": "panel", "label": "lid", "part_id": "P01", "x": 50, "y": 20}]},
        )
        hit = project_by_file("cut-aa.svg")
        self.assertEqual(hit["project_id"], "mill-file")
        ctx = editor_context("cut-aa.svg")
        self.assertTrue(ctx["editable"])
        self.assertEqual(ctx["parts"][0]["label"], "lid")
        out = apply_revision({"file_id": "cut-aa.svg", "part": "P01", "op": "extend", "mm": 5, "dim": "x"})
        self.assertEqual(out["primitives"][0]["x"], 55)

    def test_activation_binds_machine(self):
        from catalog import mint_activation, redeem_activation, upsert_machine

        upsert_machine({"id": "acme_9060", "brand": "ACME", "model": "9060", "bed_w": 900, "bed_h": 600}, owner="dealer")
        minted = mint_activation({"machine_id": "acme_9060", "code": "LM-TEST1"}, owner="dealer")
        hit = redeem_activation("lm-test1", owner="buyer")
        self.assertEqual(hit["machine"]["id"], "acme_9060")
        self.assertEqual(hit["trial_days"], 30)
        self.assertEqual(minted["code"], "LM-TEST1")

    def test_make_this_asks_for_confirm(self):
        from workshop import make_this

        out = make_this({"what_you_see": "4 duvar, eğimli çatı, pervane", "user_request": "yel değirmeni"})
        self.assertTrue(out["needs_confirm"])
        self.assertTrue(out["structure"])
        self.assertEqual(out["next_tool"], "create_design")

    def test_cost_estimate_from_parts(self):
        from workshop import estimate_cost

        out = estimate_cost(
            {
                "primitives": [{"type": "panel", "x": 100, "y": 80, "count": 4}],
                "material": "poplar_3mm",
                "machine": "payas_workshop",
            }
        )
        self.assertEqual(out["parts"], 4)
        self.assertGreater(out["area_m2"], 0)
        self.assertGreaterEqual(out["sheets"], 1)

    def test_studio_routes_workshop_verbs(self):
        from studio import studio_action

        cat = studio_action("catalog")
        self.assertTrue(cat.get("machines"))
        pf = studio_action("preflight", payload={})
        self.assertIn(pf.get("result"), {"PASS", "WARNING", "FAIL"})


if __name__ == "__main__":
    unittest.main()
