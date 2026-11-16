"""The Studio agent loop: real server tools, a scripted model, no network."""

import json
import os
import tempfile
import unittest

os.environ.setdefault("MCP_DATA_DIR", tempfile.mkdtemp(prefix="lasermcp-agent-test-"))

import studio_agent as sa

SHELF = {"primitives": [{"type": "shelf_unit", "w": 300, "d": 150, "h": 400, "shelves": 3}],
         "parameters": {"thickness": 3, "holding_nicks": False, "surface_texts": []}}


def scripted(*turns):
    """A model that plays back fixed turns and records what it was shown."""
    seen = []
    queue = list(turns)

    def step(model, system, transcript, tools, key_owner=""):
        seen.append({"transcript": json.loads(json.dumps(transcript)), "tools": [t["name"] for t in tools], "system": system})
        return queue.pop(0)

    step.seen = seen
    return step


def say(text):
    return {"text": text, "calls": [], "usage": {"input_tokens": 10, "output_tokens": 5}}


def call(name, arguments, text="", call_id="c1"):
    return {"text": text, "calls": [{"id": call_id, "name": name, "arguments": arguments}], "usage": {"input_tokens": 10, "output_tokens": 5}}


class ToolLayerTests(unittest.TestCase):
    def test_the_model_sees_the_servers_own_tools(self):
        import asyncio

        import server

        names = [t["name"] for t in sa.tool_specs("all")]
        registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
        self.assertEqual(set(names), registered - sa.DENY)
        for must in ("plan_laser_job", "create_design", "validate_assembly", "render_preview", "import_dxf_design"):
            self.assertIn(must, names)
        self.assertFalse(set(names) & sa.DENY)
        self.assertTrue(all(t["parameters"].get("type") == "object" for t in sa.tool_specs("all")))
        self.assertLess(len(sa.tool_specs("core")), len(names))

    def test_denied_and_unknown_tools_answer_with_an_error(self):
        self.assertIn("error", sa.call_tool("studio", {"action": "keys", "name": "x"}))
        self.assertIn("error", sa.call_tool("no_such_tool", {}))

    def test_a_long_result_keeps_its_verdict(self):
        data = {"svg": "<svg>" + "x" * 50000, "parts": [{"n": i, "blob": "y" * 900} for i in range(200)],
                "look_again": ["slot leaves the wall"], "final_status": "BLOCKED", "file_id": "f.svg"}
        text = sa.result_text(data)
        self.assertLessEqual(len(text), sa.RESULT_CHARS + 20)
        self.assertLess(text.index("BLOCKED"), 200)
        self.assertIn("slot leaves the wall", text)
        self.assertNotIn("x" * 700, text)


class LoopTests(unittest.TestCase):
    def test_plan_build_and_answer_with_a_dxf(self):
        step = scripted(
            call("create_design", SHELF, text="Üç raflı bir kitaplık görüyorum; raf ünitesi kalıbıyla çizeceğim."),
            say("3 raflı kitaplık hazır: 300×150×400 mm, 7 parça."),
        )
        run = sa.run_agent("3 raflı kitaplık, 300x150x400 mm", model="local:test", step=step, thickness=3)
        self.assertTrue(run["success"], run)
        self.assertEqual(run["final_status"], "PROTOTYPE READY")
        self.assertTrue(str(run["dxf_url"]).endswith(".dxf"))
        self.assertEqual(run["message"], "3 raflı kitaplık hazır: 300×150×400 mm, 7 parça.")
        self.assertEqual([s.get("tool") or "say" for s in run["steps"]], ["say", "create_design"])
        self.assertEqual(run["turns"], 2)
        # The second turn was shown the tool's result, verdict first.
        fed_back = step.seen[1]["transcript"][-1]
        self.assertEqual(fed_back["role"], "tool")
        self.assertIn('"final_status":"PROTOTYPE READY"', fed_back["text"])
        self.assertIn("Material thickness_mm=3", step.seen[0]["transcript"][0]["text"])

    def test_a_blocked_design_is_read_and_repaired(self):
        bad = {"primitives": [{"type": "shelf_unit", "w": 300, "d": 150, "h": 100, "shelves": 8}], "parameters": SHELF["parameters"]}
        step = scripted(call("create_design", bad), call("create_design", SHELF, call_id="c2"), say("Düzelttim."))
        run = sa.run_agent("8 raflı kitaplık", model="local:test", step=step)
        self.assertTrue(run["success"])
        tools = [s for s in run["steps"] if s.get("tool")]
        self.assertFalse(tools[0]["ok"])
        self.assertTrue(tools[1]["ok"])
        self.assertIn("shelves do not fit", step.seen[1]["transcript"][-1]["text"])

    def test_questions_from_a_tool_reach_the_user(self):
        ask = {"primitives": SHELF["primitives"], "parameters": {"thickness": 3}}
        step = scripted(call("create_design", ask), say("Kesim noçlu mu olsun, noçsuz mu?"))
        run = sa.run_agent("kitaplık", model="local:test", step=step)
        self.assertFalse(run["success"])
        self.assertTrue(any(q.get("field") == "holding_nicks" for q in run["questions"]))
        self.assertIn("noç", run["message"])

    def test_choices_and_the_picture_go_with_the_first_message(self):
        step = scripted(say("Tamam."))
        image = {"media": "image/png", "data": "AAAA"}
        sa.run_agent("bunu çiz", model="local:test", step=step, image=image, choices={"holding_nicks": False})
        first = step.seen[0]["transcript"][0]
        self.assertEqual(first["image"], image)
        self.assertIn('"holding_nicks": false', first["text"])

    def test_choices_reach_the_design_tool_even_when_the_model_forgets_them(self):
        bare = {"primitives": SHELF["primitives"], "parameters": {"thickness": 3}}
        step = scripted(call("create_design", bare), say("Hazır."))
        run = sa.run_agent("kitaplık", model="local:test", step=step, choices={"holding_nicks": False, "surface_texts": []})
        self.assertTrue(run["success"], run["steps"])
        self.assertEqual(run["questions"], [])

    def test_an_unknown_tool_name_is_answered_not_run(self):
        step = scripted(call("delete_everything", {}), say("Peki."))
        run = sa.run_agent("x", model="local:test", step=step)
        self.assertIn("unknown tool", step.seen[1]["transcript"][-1]["text"])
        self.assertFalse(run["success"])

    def test_an_empty_turn_gets_one_plain_reminder(self):
        step = scripted(say(""), call("create_design", SHELF), say("Hazır."))
        run = sa.run_agent("kitaplık", model="local:test", step=step)
        self.assertTrue(run["success"])
        self.assertIn("Continue", step.seen[1]["transcript"][-1]["text"])

    def test_the_step_limit_stops_a_model_that_never_answers(self):
        os.environ["LASERMCP_AGENT_MAX_STEPS"] = "3"
        try:
            step = scripted(*[call("payas_defaults", {}, call_id=f"c{i}") for i in range(5)])
            run = sa.run_agent("x", model="local:test", step=step)
        finally:
            del os.environ["LASERMCP_AGENT_MAX_STEPS"]
        self.assertEqual(run["stopped"], "step limit 3 reached")
        self.assertEqual(len(step.seen), 3)


class WireFormatTests(unittest.TestCase):
    TRANSCRIPT = [
        {"role": "user", "text": "çiz", "image": {"media": "image/png", "data": "AAAA"}},
        {"role": "assistant", "text": "planlıyorum", "calls": [{"id": "a", "name": "create_design", "arguments": {"x": 1}}, {"id": "b", "name": "payas_defaults", "arguments": {}}]},
        {"role": "tool", "id": "a", "name": "create_design", "text": "{}"},
        {"role": "tool", "id": "b", "name": "payas_defaults", "text": "{}"},
    ]

    def test_openai_messages(self):
        msgs = sa._openai_messages("SYS", self.TRANSCRIPT)
        self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant", "tool", "tool"])
        self.assertEqual(msgs[1]["content"][1]["image_url"]["url"], "data:image/png;base64,AAAA")
        self.assertEqual(json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"]), {"x": 1})
        self.assertEqual(msgs[3]["tool_call_id"], "a")

    def test_anthropic_messages_group_the_results_of_one_turn(self):
        msgs = sa._anthropic_messages(self.TRANSCRIPT)
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user"])
        self.assertEqual(msgs[0]["content"][0]["type"], "image")
        self.assertEqual([b["type"] for b in msgs[1]["content"]], ["text", "tool_use", "tool_use"])
        self.assertEqual([b["tool_use_id"] for b in msgs[2]["content"]], ["a", "b"])


class StudioRouteTests(unittest.TestCase):
    """create_studio_ai with agent=true hands the request to the loop and shapes the reply."""

    def run_route(self, body, step, guard=None):
        from unittest import mock

        import workshop

        guard = guard or {"allow": True, "model": "local:test", "provider": "local", "own_key": False, "key_owner": ""}
        ok = {"ok": True}
        with mock.patch("llm_guard.authorize", return_value=guard), mock.patch("studio_agent.model_step", step),                 mock.patch("plans.gate_job", return_value=ok), mock.patch("plans.entitled", return_value=True):
            return workshop.create_studio_ai(body, public_base_url="http://x")

    def test_a_built_design_comes_back_as_a_studio_result(self):
        step = scripted(call("create_design", SHELF, text="Planım: raf ünitesi."), say("Kitaplık hazır."))
        reply = self.run_route({"prompt": "3 raflı kitaplık", "agent": True, "thickness": 3}, step)
        self.assertTrue(reply["ok"], reply.get("look_again"))
        self.assertEqual(reply["plan_job"]["method"], "studio_agent")
        self.assertTrue(str(reply["dxf_url"]).endswith(".dxf"))
        self.assertEqual(reply["agent"]["message"], "Kitaplık hazır.")
        self.assertEqual(reply["look_again"][0], "Kitaplık hazır.")
        self.assertGreaterEqual(len(reply["assembly"]["panels"]), 7)

    def test_a_picture_is_shown_to_the_model(self):
        step = scripted(say("Bu bir kutu; ölçü verir misin?"))
        reply = self.run_route({"prompt": "", "agent": True, "image_base64": "data:image/png;base64,AAAA"}, step)
        self.assertFalse(reply["ok"])
        self.assertEqual(step.seen[0]["transcript"][0]["image"], {"media": "image/png", "data": "AAAA"})
        self.assertEqual(reply["look_again"], ["Bu bir kutu; ölçü verir misin?"])

    def test_without_a_model_the_user_is_told_why(self):
        step = scripted()
        reply = self.run_route({"prompt": "kutu", "agent": True}, step, guard={"allow": False, "reason": "no_key", "note": "AI kapalı"})
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["look_again"], ["AI kapalı"])
        self.assertEqual(step.seen, [])

    def test_the_old_path_is_untouched_without_the_flag(self):
        import workshop

        self.assertFalse(workshop._agent_requested({"prompt": "kutu"}))
        self.assertFalse(workshop._agent_requested({"agent": "false"}))
        self.assertTrue(workshop._agent_requested({"agent": 1}))


if __name__ == "__main__":
    unittest.main()
