"""Studio AI quality/cost routing and the Studio gap fixes (form restore, quotas, chat)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tests.test_llm_guard import APPROVED, ASK, DESIGN, GATE, PLAN, _Iso

BLOCKED = {"success": True, "final_status": "BLOCKED", "file_id": "b.svg", "look_again": ["edge f has no F partner"]}


class RoutingTests(_Iso):
    def _run(self, body, design=DESIGN, **kwargs):
        from workshop import create_studio_ai

        made = patch("payas_cad.create_design", side_effect=design if isinstance(design, list) else None,
                     return_value=None if isinstance(design, list) else design)
        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), made as cd, \
                patch("assembly_result.panels_for_viewer", return_value={"success": True, "panels": []}), \
                patch("llm_client.plan_primitives_with_llm", return_value=PLAN) as llm:
            return create_studio_ai(body, client_ip="203.0.113.7", **kwargs), llm, cd

    def test_plain_box_never_reaches_a_model(self):
        self.sign_in(APPROVED)
        out, llm, _ = self._run({"prompt": "180x120x70 kutu"})
        llm.assert_not_called()
        self.assertEqual(out["source"], "prompt")
        self.assertTrue(any("$0" in note for note in out["look_again"]))

    def test_plain_box_in_a_chat_turn_or_forced_llm_still_uses_the_model(self):
        self.sign_in(APPROVED)
        _, llm, _ = self._run({"prompt": "180x120x70 kutu", "messages": [{"role": "user", "text": "180x120x70 kutu"}, {"role": "assistant", "text": "Hazır"},
                                                                    {"role": "user", "text": "kapak sürgülü olsun"}]})
        llm.assert_called_once()
        _, llm, _ = self._run({"prompt": "200x100x50 kutu", "planner": "llm"})
        llm.assert_called_once()

    def test_same_request_is_served_from_the_draft_cache(self):
        self.sign_in(APPROVED)
        _, first, _ = self._run({"prompt": ASK, "thickness": 3})
        first.assert_called_once()
        out, again, made = self._run({"prompt": "  Telefon  standı ve KARTVİZİTLİK ", "thickness": 3})
        again.assert_not_called()
        made.assert_called_once()
        self.assertEqual(out["plan_job"]["method"], "workshop_llm_cache")
        self.assertEqual(out["plan_job"]["usage"]["usd"], 0.0)
        # Another thickness is another design: it is drafted again.
        _, other, _ = self._run({"prompt": ASK, "thickness": 4})
        other.assert_called_once()

    def test_blocked_draft_is_not_cached(self):
        self.sign_in(APPROVED)
        os.environ["LASERMCP_AI_AUTO_REPAIR"] = "0"
        self.addCleanup(os.environ.pop, "LASERMCP_AI_AUTO_REPAIR", None)
        self._run({"prompt": ASK}, design=BLOCKED)
        _, llm, _ = self._run({"prompt": ASK}, design=BLOCKED)
        llm.assert_called_once()

    def test_one_automatic_repair_after_a_blocked_draft(self):
        self.sign_in(APPROVED)
        out, llm, made = self._run({"prompt": ASK}, design=[BLOCKED, DESIGN])
        self.assertEqual(llm.call_count, 2)
        self.assertEqual(made.call_count, 2)
        self.assertEqual(llm.call_args_list[0].kwargs["effort"], "low")
        self.assertEqual(llm.call_args_list[1].kwargs["effort"], "medium")
        repair_text = llm.call_args_list[1].args[0]
        self.assertIn("edge f has no F partner", repair_text)
        self.assertIn('"type":"box"', repair_text)
        self.assertEqual(out["final_status"], "PROTOTYPE READY")
        self.assertTrue(out["export_allowed"])
        # Studio says "found it, fixed it" from this; the block itself is never shown.
        self.assertEqual(out["auto_repair"], {"attempted": 1, "fixed": True, "issues": ["edge f has no F partner"]})
        self.assertTrue(out["look_again"][0].startswith("Auto-repair:"))
        self.assertFalse(any(str(x).startswith("BLOCKED") for x in out["look_again"]))
        self.assertEqual(out["plan_job"]["usage"]["calls"], 2)
        self.assertEqual(out["plan_job"]["usage"]["output_tokens"], 2000)

    def test_second_repair_thinks_harder_and_sees_the_latest_notes(self):
        self.sign_in(APPROVED)
        still = {**BLOCKED, "look_again": ["slot overlaps hole"]}
        out, llm, _ = self._run({"prompt": ASK}, design=[BLOCKED, still, DESIGN])
        self.assertEqual([c.kwargs["effort"] for c in llm.call_args_list], ["low", "medium", "high"])
        self.assertIn("slot overlaps hole", llm.call_args_list[2].args[0])
        self.assertEqual(out["auto_repair"]["attempted"], 2)
        self.assertTrue(out["auto_repair"]["fixed"])

    def test_blocked_local_draft_is_repaired_by_the_model(self):
        self.sign_in(APPROVED)
        out, llm, _ = self._run({"prompt": "180x120x70 kutu"}, design=[BLOCKED, DESIGN])
        llm.assert_called_once()
        self.assertEqual(llm.call_args.kwargs["effort"], "medium")
        self.assertTrue(out["auto_repair"]["fixed"])
        self.assertEqual(out["final_status"], "PROTOTYPE READY")

    def test_guest_local_draft_is_not_repaired_with_the_paid_model(self):
        out, llm, _ = self._run({"prompt": "180x120x70 kutu"}, design=[BLOCKED])
        llm.assert_not_called()
        self.assertEqual(out["auto_repair"]["attempted"], 0)
        self.assertFalse(out["auto_repair"]["fixed"])
        self.assertFalse(out["export_allowed"])

    def test_repair_is_bounded_and_can_be_switched_off(self):
        self.sign_in(APPROVED)
        out, llm, _ = self._run({"prompt": ASK}, design=[BLOCKED, BLOCKED, BLOCKED])
        self.assertEqual(llm.call_count, 3)  # one draft + two repairs, never a loop
        self.assertEqual(out["auto_repair"]["attempted"], 2)
        self.assertFalse(out["auto_repair"]["fixed"])
        self.assertFalse(out["export_allowed"])
        os.environ["LASERMCP_AI_REPAIR_ATTEMPTS"] = "1"
        self.addCleanup(os.environ.pop, "LASERMCP_AI_REPAIR_ATTEMPTS", None)
        _, llm, _ = self._run({"prompt": ASK + " 1"}, design=[BLOCKED, BLOCKED])
        self.assertEqual(llm.call_count, 2)
        os.environ["LASERMCP_AI_AUTO_REPAIR"] = "0"
        self.addCleanup(os.environ.pop, "LASERMCP_AI_AUTO_REPAIR", None)
        _, llm, _ = self._run({"prompt": ASK + " 2"}, design=[BLOCKED])
        llm.assert_called_once()

    def test_repair_counts_against_the_daily_cap(self):
        self.sign_in(APPROVED)
        os.environ["LASERMCP_AI_DAILY_PER_IP"] = "1"
        _, llm, _ = self._run({"prompt": ASK}, design=[BLOCKED, DESIGN])
        llm.assert_called_once()

    def test_chat_thread_is_stored_with_the_version(self):
        self.sign_in(APPROVED)
        messages = [{"role": "user", "text": "kalemlik"}, {"role": "system", "text": "gate note"},
                    {"role": "assistant", "text": "Hazır"}]
        _, _, made = self._run({"prompt": ASK, "messages": messages})
        stored = made.call_args.kwargs["parameters"]["studio_chat"]
        self.assertEqual(stored, [{"role": "user", "text": "kalemlik"}, {"role": "assistant", "text": "Hazır"}])


class ModelChoiceTests(_Iso):
    def test_default_prefers_the_cheapest_model_with_a_key(self):
        from llm_guard import default_model, repair_model

        self.assertEqual(default_model(), "gpt-4o-mini")  # only an OpenAI key here
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-not-a-real-key"
        self.assertEqual(default_model(), "claude-haiku-5-5")
        self.assertEqual(repair_model("claude-haiku-5-5"), "claude-haiku-5-5")
        os.environ["LASERMCP_LLM_REPAIR_MODEL"] = "claude-sonnet-5-5"
        self.addCleanup(os.environ.pop, "LASERMCP_LLM_REPAIR_MODEL", None)
        self.assertEqual(repair_model("claude-haiku-5-5"), "claude-sonnet-5-5")
        os.environ["LASERMCP_LLM_REPAIR_MODEL"] = "not-allowed-model"
        self.assertEqual(repair_model("claude-haiku-5-5"), "claude-haiku-5-5")

    def test_cache_reads_bill_at_a_tenth(self):
        from ai_cost import usage_cost

        plain = usage_cost("claude-haiku-5-5", 3000, 1000)
        cached = usage_cost("claude-haiku-5-5", 0, 1000, cache_read_tokens=3000)
        self.assertAlmostEqual(plain, 0.0008)
        self.assertAlmostEqual(cached, 0.00053)


class SimpleBoxTests(unittest.TestCase):
    def test_only_plain_boxes_with_three_sizes(self):
        from ai_cache import simple_box_request

        for text in ("180x120x70 kutu", "200 × 150 × 80 mm box", "kutu 10cm x 8cm x 5cm"):
            self.assertTrue(simple_box_request(text), text)
        for text in ("kutu", "180x120 kutu", "180x120x70 kalemlik", "180x120x70 kuş evi kutusu",
                     "180x120x70 kutu, çekmeceli", "180x120x70 kutu üstüne isim yaz"):
            self.assertFalse(simple_box_request(text), text)


class LocalDraftTests(_Iso):
    """Real local drafts (no mocked create_design): what Studio does without a model key."""

    def _ai(self, prompt):
        from workshop import create_studio_ai

        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE):
            return create_studio_ai({"prompt": prompt}, client_ip="203.0.113.7")

    def test_plain_box_keeps_the_typed_sizes_and_passes(self):
        out = self._ai("180x120x70 kutu")
        self.assertEqual(out["final_status"], "PROTOTYPE READY")
        self.assertTrue(out["export_allowed"])
        self.assertEqual(out["plan_job"]["method"], "studio_box")
        self.assertIn("180×120×70 mm", out["plan_job"]["summary"])

    def test_typed_prompt_is_not_treated_as_a_photo_job(self):
        out = self._ai("kapaklı kalemlik 3 bölmeli")
        self.assertNotIn("REFERENCE_FIDELITY is NOT VERIFIED — cannot mark PASS", out.get("look_again") or [])
        self.assertEqual(out["final_status"], "PROTOTYPE READY")

    def test_undrawable_prompt_says_what_to_do_instead(self):
        out = self._ai("telefon standı")
        self.assertFalse(out["ok"])
        self.assertTrue(any("180x120x70 kapaklı kutu" in line for line in out["look_again"]))
        self.assertFalse(any("photo" in line for line in out["look_again"]))


class QuietDraftTests(_Iso):
    """Real compiles: a repaired request leaves one project version and one quota use."""

    def test_only_the_shown_draft_is_recorded(self):
        from metering import designs_this_month
        from projects import list_projects
        from workshop import create_studio_ai

        self.sign_in(APPROVED)
        bad = {"primitives": [{"type": "panel", "label": "a", "w": 100, "h": 40, "edges": "FFFF"},
                              {"type": "panel", "label": "b", "w": 100, "h": 40, "edges": "FFFF"}],
               "parameters": {}, "summary": "bad", "usage": {"input_tokens": 10, "output_tokens": 10}}
        good = {**PLAN, "summary": "good"}
        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), \
                patch("llm_client.plan_primitives_with_llm", side_effect=[bad, good]) as llm:
            out = create_studio_ai({"prompt": ASK}, client_ip="203.0.113.7")
        self.assertEqual(llm.call_count, 2, out.get("look_again"))
        self.assertTrue(out["auto_repair"]["fixed"])
        self.assertEqual(out["final_status"], "PROTOTYPE READY")
        projects = list_projects(limit=None)
        self.assertEqual(len(projects), 1)
        self.assertEqual((projects[0].get("latest") or {}).get("n"), 1)
        self.assertEqual(designs_this_month(APPROVED["id"]), 1)


class ParseBoxTests(unittest.TestCase):
    def test_sizes_unit_and_lid(self):
        from ai_cache import parse_box_request

        self.assertEqual(parse_box_request("180x120x70 kutu"), {"x": 180, "y": 120, "h": 70, "unit": "mm", "lid": "open"})
        self.assertEqual(parse_box_request("kapaklı kutu 20cm x 15,5cm x 8cm")["unit"], "cm")
        self.assertEqual(parse_box_request("kapaklı kutu 20cm x 15,5cm x 8cm")["y"], 15.5)
        self.assertEqual(parse_box_request("kapaklı kutu 20cm x 15cm x 8cm")["lid"], "finger")
        self.assertEqual(parse_box_request("200x100x60 kayar kapaklı kutu")["lid"], "sliding")
        self.assertEqual(parse_box_request("200x100x60 açık kutu")["lid"], "open")
        self.assertIsNone(parse_box_request("telefon standı"))
        self.assertIsNone(parse_box_request("180x120x70 kutu çekmeceli"))


class StudioFormTests(unittest.TestCase):
    def test_form_is_whitelisted_and_stored_with_the_box(self):
        from studio_box import build_studio_box, studio_form_snapshot

        form = {"x": "180", "lid": "sliding", "dividerXPos": [40, "evil", 80], "lockedCellsX": {"0": 30, "1": "x"},
                "evil": "<script>", "unit": "m" * 200, "part_labels": True}
        clean = studio_form_snapshot(form)
        self.assertNotIn("evil", clean)
        self.assertEqual(clean["dividerXPos"], [40, 80])
        self.assertEqual(clean["lockedCellsX"], {"0": 30})
        self.assertEqual(len(clean["unit"]), 40)
        built = build_studio_box({"x": 180, "y": 120, "h": 70, "studio_form": form, "project_id": "box-ab12"})
        self.assertEqual(built["parameters"]["studio_form"], clean)
        self.assertEqual(built["parameters"]["project_id"], "box-ab12")
        self.assertNotIn("studio_form", build_studio_box({"x": 180, "y": 120, "h": 70})["parameters"])


class GuestQuotaTests(_Iso):
    def test_each_guest_address_has_its_own_count(self):
        from metering import anon_id_for, anon_identity, designs_this_month, record_usage

        a, b = anon_id_for("198.51.100.1"), anon_id_for("198.51.100.2")
        self.assertNotEqual(a, b)
        self.assertNotIn("198.51", a)
        token = anon_identity.set(a)
        try:
            record_usage(None, "studio", {"file_id": "x.svg"})
            self.assertEqual(designs_this_month(None), 1)
        finally:
            anon_identity.reset(token)
        token = anon_identity.set(b)
        try:
            self.assertEqual(designs_this_month(None), 0)
        finally:
            anon_identity.reset(token)

    def test_full_quota_keeps_preview_and_stops_the_save(self):
        from workshop import create_studio_box

        closed = {"success": True, "ok": False, "look_again": ["quota used"]}
        with patch("plans.gate_job", return_value=closed):
            preview = create_studio_box({"x": 120, "y": 80, "h": 50, "preview": True})
            saved = create_studio_box({"x": 120, "y": 80, "h": 50})
        self.assertTrue(preview["success"])
        self.assertTrue(preview["preview"])
        self.assertEqual(saved, closed)


if __name__ == "__main__":
    unittest.main()
