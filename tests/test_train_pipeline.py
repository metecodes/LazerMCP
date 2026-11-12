"""The tuned-model pipeline: prompts, teacher collection, training files, and serving."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import ai_eval
import train
import train_prompts
from ai_cache import _normalize, match_maker, simple_box_request

BOX = {
    "primitives": [{"type": "box", "x": 120, "y": 80, "h": 60, "lid": False}],
    "parameters": {"thickness": 3},
    "summary": "kutu",
    "usage": {"input_tokens": 100, "output_tokens": 50},
}
TUNED = "ft:gpt-4o-mini:Org:lasermcp:AbC1"


def _teacher(*_a, **_k):
    return json.loads(json.dumps(BOX))


class PromptTests(unittest.TestCase):
    def test_prompts_are_distinct_stable_and_need_a_model(self):
        rows = train_prompts.make_prompts(300)
        self.assertEqual(rows, train_prompts.make_prompts(300))
        self.assertEqual(len({r["prompt"] for r in rows}), 300)
        for row in rows:
            self.assertIsNone(match_maker(row["prompt"]), row["prompt"])
            self.assertFalse(simple_box_request(row["prompt"]), row["prompt"])

    def test_benchmark_prompts_are_never_training_prompts(self):
        held_out = {_normalize(r["prompt"]) for r in ai_eval.load_prompts()}
        got = {_normalize(r["prompt"]) for r in train_prompts.make_prompts(2000)}
        self.assertFalse(held_out & got)


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="train-test-")
        env = {"MCP_DATA_DIR": tempfile.mkdtemp(prefix="train-data-"), "LASERMCP_AI_CACHE_DAYS": "0"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_approved_draft_becomes_an_example_in_the_live_request_format(self):
        row = {"id": "t1-00001", "prompt": "kalemlik 3 bölmeli", "thickness": 3.0}
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=_teacher):
            examples, usd, why = train.collect_one(row, "gpt-5.5")
        self.assertEqual(why, "")
        self.assertEqual([e["kind"] for e in examples], ["draft"])
        self.assertIn("Studio chat so far:\nUser: kalemlik 3 bölmeli", examples[0]["user"])
        self.assertTrue(examples[0]["user"].endswith("Material thickness_mm=3.0"))
        self.assertEqual(json.loads(examples[0]["assistant"])["primitives"], BOX["primitives"])
        self.assertGreater(usd, 0)

    def test_provider_error_keeps_nothing(self):
        row = {"id": "t1-00001", "prompt": "kalemlik", "thickness": 3.0}
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=ValueError("LLM HTTP 401")):
            examples, _usd, why = train.collect_one(row, "gpt-5.5")
        self.assertEqual(examples, [])
        self.assertTrue(why.startswith("error:"))

    def test_collect_needs_spend_then_writes_and_resumes(self):
        self.assertEqual(train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "3"]), 2)
        self.assertFalse((Path(self.tmp) / train.EXAMPLES).exists())
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=_teacher) as teacher:
            self.assertEqual(train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "3", "--spend"]), 0)
            self.assertEqual(teacher.call_count, 3)
            self.assertEqual(train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "2", "--spend"]), 0)
        # Five different requests were tried; each is either kept or recorded as rejected.
        rows = train._read_jsonl(Path(self.tmp) / train.EXAMPLES) + train._read_jsonl(Path(self.tmp) / train.REJECTED)
        self.assertEqual(len({r["prompt_id"] for r in rows}), 5)

    def test_budget_stops_the_run(self):
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=_teacher) as teacher:
            train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "50", "--max-usd", "0.000001", "--spend"])
        self.assertEqual(teacher.call_count, 1)

    def test_five_provider_errors_in_a_row_stop_the_run(self):
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=ValueError("LLM HTTP 401")) as teacher:
            train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "50", "--spend"])
        self.assertEqual(teacher.call_count, 5)


class ReportTests(unittest.TestCase):
    """What comes back from the training machine must be enough to diagnose a bad run."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="train-report-")
        env = {"MCP_DATA_DIR": tempfile.mkdtemp(prefix="train-data-"), "LASERMCP_AI_CACHE_DAYS": "0"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_refused_draft_is_recorded_with_its_gate_notes_and_the_draft(self):
        bad = {"primitives": [{"type": "panel", "label": "a", "w": 80, "h": 60, "edges": "FFFF"}, {"type": "panel", "label": "b", "w": 80, "h": 60, "edges": "ffff"}], "parameters": {}, "summary": "", "usage": {}}
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=lambda *a, **k: json.loads(json.dumps(bad))):
            train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "2", "--spend"])
        rows = train._read_jsonl(Path(self.tmp) / train.REJECTED)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["notes"])
        self.assertIn("FFFF", rows[0]["draft"])
        report = (Path(self.tmp) / train.REPORT).read_text(encoding="utf-8")
        self.assertIn("kept: 0   rejected: 2   yield: 0%", report)
        self.assertIn("why drafts were refused", report)

    def test_provider_errors_are_logged_but_stay_retryable(self):
        with mock.patch("llm_client.plan_primitives_with_llm", side_effect=ValueError("LLM reply was not JSON")):
            train.main(["--out", self.tmp, "collect", "--teacher", "gpt-5.5", "--count", "2", "--spend"])
        self.assertEqual(train._read_jsonl(Path(self.tmp) / train.REJECTED), [])
        self.assertEqual(len(train._read_jsonl(Path(self.tmp) / train.ERRORS)), 2)
        self.assertIn("LLM reply was not JSON", train.build_report(Path(self.tmp)))

    def test_report_on_an_empty_folder_does_not_fail(self):
        self.assertEqual(train.main(["--out", self.tmp, "report"]), 0)


class BuildTests(unittest.TestCase):
    def _examples(self, n):
        rows = []
        for i in range(n):
            rows.append({"prompt_id": f"p{i}", "kind": "draft", "user": f"istek {i}", "assistant": train.answer_json(BOX)})
            if i % 4 == 0:
                rows.append({"prompt_id": f"p{i}", "kind": "repair", "user": f"istek {i} BLOCKED", "assistant": train.answer_json(BOX)})
        return rows

    def test_split_keeps_a_repair_with_its_draft_and_drops_bad_rows(self):
        rows = self._examples(40)
        rows.append({"prompt_id": "bad", "user": "x", "assistant": "not json"})
        rows.append({"prompt_id": "empty", "user": "x", "assistant": json.dumps({"primitives": []})})
        rows.append(dict(rows[0]))  # exact duplicate
        tr, va = train.split(rows)
        self.assertEqual(len(tr) + len(va), 50)
        self.assertEqual(len({e["prompt_id"] for e in va}), 4)
        self.assertFalse({e["prompt_id"] for e in tr} & {e["prompt_id"] for e in va})

    def test_build_writes_chat_files_with_the_serving_system_prompt(self):
        from llm_client import tuned_system_prompt

        tmp = Path(tempfile.mkdtemp(prefix="train-build-"))
        self.assertEqual(train.main(["--out", str(tmp), "build"]), 1)
        for ex in self._examples(30):
            train._append(tmp / train.EXAMPLES, ex)
        self.assertEqual(train.main(["--out", str(tmp), "build"]), 0)
        first = json.loads((tmp / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual([m["role"] for m in first["messages"]], ["system", "user", "assistant"])
        self.assertEqual(first["messages"][0]["content"], tuned_system_prompt())
        self.assertTrue((tmp / "valid.jsonl").read_text(encoding="utf-8").strip())

    def test_start_needs_spend_and_never_calls_the_provider_without_it(self):
        tmp = Path(tempfile.mkdtemp(prefix="train-start-"))
        (tmp / "train.jsonl").write_text(json.dumps({"messages": []}) + "\n", encoding="utf-8")
        with mock.patch("train._api") as api:
            self.assertEqual(train.main(["--out", str(tmp), "start"]), 2)
            api.assert_not_called()

    def test_start_uploads_then_creates_the_job(self):
        tmp = Path(tempfile.mkdtemp(prefix="train-start-"))
        (tmp / "train.jsonl").write_text(json.dumps({"messages": []}) + "\n", encoding="utf-8")
        calls = []

        def api(method, path, **kw):
            calls.append((method, path, kw))
            return {"id": "file-1"} if path == "/files" else {"id": "ftjob-1", "status": "validating_files"}

        with mock.patch("train._api", side_effect=api):
            self.assertEqual(train.main(["--out", str(tmp), "start", "--spend"]), 0)
        self.assertEqual([c[1] for c in calls], ["/files", "/fine_tuning/jobs"])
        self.assertIn(b"fine-tune", calls[0][2]["body"])
        spec = json.loads(calls[1][2]["body"])
        self.assertEqual((spec["model"], spec["training_file"]), (train.DEFAULT_BASE, "file-1"))
        self.assertEqual(json.loads((tmp / "job.json").read_text(encoding="utf-8"))["id"], "ftjob-1")


class ServingTests(unittest.TestCase):
    def test_tuned_model_is_offered_only_once_configured(self):
        import llm_guard

        with mock.patch.dict(os.environ, {"LASERMCP_TUNED_MODEL": ""}):
            self.assertNotIn("lasermcp-tuned", llm_guard.allowed_models())
        with mock.patch.dict(os.environ, {"LASERMCP_TUNED_MODEL": TUNED}):
            self.assertIn("lasermcp-tuned", llm_guard.allowed_models())
            self.assertNotEqual(llm_guard.allowed_models()[0], "lasermcp-tuned")

    def test_tuned_call_uses_the_provider_id_and_the_short_prompt(self):
        import llm_client

        sent = {}

        def http(url, *, headers, body, timeout=45.0):
            sent.update(body)
            return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {}}

        with mock.patch.dict(os.environ, {"LASERMCP_TUNED_MODEL": TUNED}), mock.patch("llm_client._http_json", side_effect=http):
            llm_client._openai_chat("k", "lasermcp-tuned", "telefon standı")
        self.assertEqual(sent["model"], TUNED)
        self.assertEqual(sent["messages"][0]["content"], llm_client.tuned_system_prompt())
        self.assertNotIn("Primitive grammar", sent["messages"][0]["content"])
        self.assertIn("max_tokens", sent)

    def test_tuned_call_without_configuration_fails_before_any_request(self):
        import llm_client

        with mock.patch.dict(os.environ, {"LASERMCP_TUNED_MODEL": ""}), mock.patch("llm_client._http_json") as http:
            with self.assertRaises(ValueError):
                llm_client._openai_chat("k", "lasermcp-tuned", "x")
            http.assert_not_called()


class LocalModelTests(unittest.TestCase):
    """A model on the operator's own machine: no provider key, no bill, no --spend."""

    def _http(self, sent):
        def http(url, *, headers, body, timeout=45.0):
            sent.update({"url": url, "timeout": timeout, **body})
            return {"choices": [{"message": {"content": json.dumps(BOX)}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 900, "completion_tokens": 300}}

        return http

    def test_local_model_calls_the_local_server_with_the_full_grammar(self):
        import llm_client

        sent = {}
        with mock.patch.dict(os.environ, {"LASERMCP_LOCAL_BASE_URL": "", "OPENAI_API_KEY": ""}), mock.patch("llm_client._http_json", side_effect=self._http(sent)):
            plan = llm_client.plan_primitives_with_llm("telefon standı", model="local:lasermcp-teacher", thickness=3)
        self.assertEqual(sent["url"], "http://127.0.0.1:11434/v1/chat/completions")
        self.assertEqual(sent["model"], "lasermcp-teacher")
        self.assertIn("Primitive grammar", sent["messages"][0]["content"])
        self.assertGreater(sent["timeout"], 100)
        self.assertEqual(plan["provider"], "local")

    def test_local_tokens_cost_nothing(self):
        from ai_cost import usage_cost

        self.assertEqual(usage_cost("local:lasermcp-teacher", 100000, 100000), 0.0)
        self.assertGreater(usage_cost("gpt-4o-mini", 100000, 100000), 0.0)

    def test_tuned_model_can_be_served_from_the_operators_machine(self):
        import llm_client

        sent = {}
        env = {"LASERMCP_TUNED_MODEL": "lasermcp", "LASERMCP_TUNED_BASE_URL": "https://tunnel.example/v1/", "OPENAI_API_KEY": ""}
        with mock.patch.dict(os.environ, env), mock.patch("llm_client._http_json", side_effect=self._http(sent)):
            llm_client.plan_primitives_with_llm("telefon standı", model="lasermcp-tuned")
            from ai_cost import usage_cost

            self.assertEqual(usage_cost("lasermcp-tuned", 1000, 1000), 0.0)
        self.assertEqual(sent["url"], "https://tunnel.example/v1/chat/completions")
        self.assertEqual(sent["model"], "lasermcp")
        self.assertEqual(sent["messages"][0]["content"], llm_client.tuned_system_prompt())

    def test_a_browser_cannot_pick_a_local_model(self):
        import llm_guard

        with mock.patch.dict(os.environ, {"LASERMCP_LLM_MODELS": "", "LASERMCP_LLM_DEFAULT_MODEL": ""}):
            self.assertFalse(llm_guard.resolve_model("local:anything").startswith("local:"))

    def test_local_teacher_collects_without_spend(self):
        tmp = tempfile.mkdtemp(prefix="train-local-")
        sent = {}
        env = {"MCP_DATA_DIR": tempfile.mkdtemp(prefix="train-data-"), "OPENAI_API_KEY": ""}
        with mock.patch.dict(os.environ, env), mock.patch("llm_client._http_json", side_effect=self._http(sent)):
            self.assertEqual(train.main(["--out", tmp, "collect", "--count", "1"]), 0)
        rows = train._read_jsonl(Path(tmp) / train.EXAMPLES)
        self.assertEqual((len(rows), rows[0]["teacher"], rows[0]["usd"]), (1, "local:lasermcp-teacher", 0.0))


if __name__ == "__main__":
    unittest.main()
