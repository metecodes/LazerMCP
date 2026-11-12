"""The Studio AI benchmark: its scoring, and the free routes its prompt set pins down."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import ai_eval
from ai_cache import match_maker, simple_box_request


def _reply(status="PROTOTYPE READY", method="workshop_llm", panels=4, repair=None, usd=0.01, maker=None):
    job = {"method": method, "usage": {"usd": usd}}
    if maker:
        job["maker"] = maker
    return {
        "success": True,
        "final_status": status,
        "plan_job": job,
        "assembly": {"panels": [{}] * panels},
        "auto_repair": repair or {"attempted": 0, "fixed": False, "issues": []},
    }


class ScoreTests(unittest.TestCase):
    def test_clean_first_draft_passes(self):
        got = ai_eval.score({"id": "a", "category": "c", "prompt": "p", "min_panels": 2, "max_panels": 6}, _reply())
        self.assertTrue(got["passed"] and got["first_pass"] and got["paid"])
        self.assertEqual(got["usd"], 0.01)

    def test_blocked_draft_fails(self):
        got = ai_eval.score({"id": "a", "category": "c", "prompt": "p"}, _reply(status="BLOCKED"))
        self.assertFalse(got["passed"])
        self.assertIn("blocked", got["problems"])

    def test_repaired_draft_passes_but_is_not_first_pass(self):
        got = ai_eval.score({"id": "a", "category": "c", "prompt": "p"}, _reply(repair={"attempted": 1, "fixed": True, "issues": ["x"]}))
        self.assertTrue(got["passed"] and got["repaired"])
        self.assertFalse(got["first_pass"])

    def test_gate_pass_with_wrong_part_count_fails(self):
        got = ai_eval.score({"id": "a", "category": "c", "prompt": "p", "min_panels": 8}, _reply(panels=5))
        self.assertTrue(got["gate_ok"])
        self.assertFalse(got["passed"])

    def test_paid_call_for_a_recipe_or_plain_box_fails(self):
        row = {"id": "a", "category": "c", "prompt": "p", "expect_method": "studio_maker", "expect_maker": "birdhouse"}
        self.assertFalse(ai_eval.score(row, _reply())["passed"])
        self.assertTrue(ai_eval.score(row, _reply(method="studio_maker", maker="birdhouse", usd=0))["passed"])
        self.assertFalse(ai_eval.score({**row, "expect_method": "local"}, _reply())["passed"])

    def test_summary_counts_and_cost(self):
        rows = [
            ai_eval.score({"id": "a", "category": "x", "prompt": "p"}, _reply(usd=0.02)),
            ai_eval.score({"id": "b", "category": "x", "prompt": "p"}, _reply(status="BLOCKED", usd=0.04)),
        ]
        block = ai_eval.summarize(rows)["by_category"]["x"]
        self.assertEqual((block["n"], block["passed"], block["usd"], block["usd_per_request"]), (2, 1, 0.06, 0.03))

    def test_model_run_needs_spend_flag(self):
        self.assertEqual(ai_eval.main(["--model", "gpt-4o-mini", "--limit", "1"]), 2)


class PromptSetTests(unittest.TestCase):
    def setUp(self):
        self.rows = ai_eval.load_prompts()

    def test_ids_are_unique(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 50)

    def test_recipe_prompts_reach_their_recipe(self):
        for row in self.rows:
            if row.get("expect_method") == "studio_maker":
                self.assertEqual((match_maker(row["prompt"]) or {}).get("maker"), row["expect_maker"], row["prompt"])

    def test_plain_boxes_stay_free(self):
        for row in self.rows:
            if row.get("expect_method") == "local":
                self.assertTrue(simple_box_request(row["prompt"]), row["prompt"])

    def test_everything_else_reaches_the_model(self):
        # A box with dividers, holes or a handle must not be answered with an empty plain box.
        for row in self.rows:
            if not row.get("expect_method"):
                self.assertIsNone(match_maker(row["prompt"]), row["prompt"])
                self.assertFalse(simple_box_request(row["prompt"]), row["prompt"])


if __name__ == "__main__":
    unittest.main()
