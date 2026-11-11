"""Cost guards in front of the workshop LLM key: who may spend it, on which model, how often."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

_ENV = (
    "MCP_DATA_DIR", "MCP_ENV", "VERCEL", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY", "MCP_AUTH_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "LASERMCP_OPENAI_API_KEY", "LASERMCP_ANTHROPIC_API_KEY", "LASERMCP_LLM_MODELS", "LASERMCP_LLM_DEFAULT_MODEL",
    "LASERMCP_AI_DAILY_PER_IP", "LASERMCP_AI_DAILY_GLOBAL", "LASERMCP_LLM_MAX_OUTPUT_TOKENS",
)

APPROVED = {"id": "u-ok", "organization_id": "org-ok", "provider": "password", "approval_status": "approved"}
PENDING = {"id": "u-wait", "organization_id": "org-wait", "provider": "google", "approval_status": "pending"}
GATE = {"ok": True, "plan": "pro", "plan_name": "Pro", "used": 0, "quota": 400}
PLAN = {
    "primitives": [{"type": "box", "x": 180, "y": 120, "h": 70}],
    "parameters": {},
    "summary": "box",
    "usage": {"input_tokens": 400, "output_tokens": 1000},
}
DESIGN = {"success": True, "final_status": "PROTOTYPE READY", "file_id": "t.svg", "look_again": []}
# Not a plain box: plain "W×D×H kutu" prompts are drafted locally at $0 and never reach a model.
ASK = "telefon standı ve kartvizitlik"
# Not a plain box either, but one the local planner can still draft when no model answers.
LOCAL_OK = "kapaklı kalemlik 3 bölmeli"


class _Iso(unittest.TestCase):
    def setUp(self):
        from persist.rate_limit import reset

        self.old = {key: os.environ.get(key) for key in _ENV}
        for key in _ENV:
            os.environ.pop(key, None)
        os.environ["MCP_DATA_DIR"] = tempfile.mkdtemp()
        os.environ["OPENAI_API_KEY"] = "sk-test-not-a-real-key-000000"
        reset()
        self._auth = None
        accounts = patch("keys.auth_required", return_value=True)
        accounts.start()
        self.addCleanup(accounts.stop)

    def tearDown(self):
        from persist.rate_limit import reset

        if self._auth is not None:
            self._auth[0].reset(self._auth[1])
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset()

    def sign_in(self, principal):
        # Looked up at call time: test_auth reloads keys, which replaces the context variable.
        import keys

        self._auth = (keys.current_auth, keys.current_auth.set(principal))


class ModelAllowlistTests(_Iso):
    def test_unknown_or_missing_model_becomes_the_default(self):
        from llm_guard import default_model, resolve_model

        self.assertEqual(default_model(), "gpt-4o-mini")
        self.assertEqual(resolve_model("claude-sonnet-4.5"), "claude-sonnet-4.5")
        self.assertEqual(resolve_model("claude-fable-5-1"), "gpt-4o-mini")
        self.assertEqual(resolve_model(""), "gpt-4o-mini")

    def test_operator_picks_the_default_and_the_list(self):
        from llm_guard import allowed_models, resolve_model

        os.environ["LASERMCP_LLM_DEFAULT_MODEL"] = "claude-sonnet-5-5"
        self.assertEqual(resolve_model(""), "claude-sonnet-5-5")
        self.assertIn("gpt-4o-mini", allowed_models())
        os.environ["LASERMCP_LLM_MODELS"] = "claude-haiku-5-5, claude-sonnet-5-5"
        self.assertEqual(allowed_models(), ["claude-haiku-5-5", "claude-sonnet-5-5"])
        self.assertEqual(resolve_model("gpt-4o"), "claude-sonnet-5-5")

    def test_new_model_reaches_its_own_provider_and_price(self):
        from ai_cost import usage_cost
        from llm_keys import provider_for_model

        self.assertEqual(provider_for_model("claude-sonnet-5-5"), "anthropic")
        self.assertEqual(provider_for_model("claude-some-later-model"), "anthropic")
        self.assertEqual(provider_for_model("gpt-6-astra"), "openai")
        self.assertAlmostEqual(usage_cost("claude-fable-5-1", 400, 1000), 0.054)


class AccessTests(_Iso):
    def test_guest_and_pending_never_reach_the_key(self):
        from llm_guard import access

        self.assertEqual(access("gpt-4o-mini")["reason"], "signin")
        self.sign_in(PENDING)
        with patch("supabase_auth.user_by_id", return_value=None):
            verdict = access("gpt-4o-mini")
        self.assertFalse(verdict["allow"])
        self.assertEqual(verdict["reason"], "pending")

    def test_approval_is_read_again_from_the_account_record(self):
        from llm_guard import access

        self.sign_in({**PENDING, "approval_status": "approved"})
        with patch("supabase_auth.user_by_id", return_value={**PENDING, "approval_status": "denied"}):
            self.assertEqual(access("")["reason"], "pending")

    def test_approved_caller_with_key_is_allowed(self):
        from llm_guard import access

        self.sign_in(APPROVED)
        self.assertTrue(access("")["allow"])
        os.environ.pop("OPENAI_API_KEY")
        self.assertEqual(access("")["reason"], "no_key")

    def test_install_without_accounts_keeps_working(self):
        from llm_guard import access

        with patch("keys.auth_required", return_value=False):
            self.assertTrue(access("")["allow"])


class DailyCapTests(_Iso):
    def test_ten_calls_per_address_per_day(self):
        from llm_guard import authorize

        self.sign_in(APPROVED)
        for _ in range(10):
            self.assertTrue(authorize("", client_ip="203.0.113.7")["allow"])
        blocked = authorize("", client_ip="203.0.113.7")
        self.assertFalse(blocked["allow"])
        self.assertEqual(blocked["reason"], "ip_limit")
        self.assertIn("10", blocked["note"])
        self.assertTrue(authorize("", client_ip="203.0.113.8")["allow"])

    def test_site_wide_cap_stops_every_address(self):
        from llm_guard import authorize

        os.environ["LASERMCP_AI_DAILY_GLOBAL"] = "2"
        self.sign_in(APPROVED)
        self.assertTrue(authorize("", client_ip="203.0.113.1")["allow"])
        self.assertTrue(authorize("", client_ip="203.0.113.2")["allow"])
        self.assertEqual(authorize("", client_ip="203.0.113.3")["reason"], "global_limit")

    def test_refused_callers_do_not_use_up_the_cap(self):
        from llm_guard import authorize

        os.environ["LASERMCP_AI_DAILY_PER_IP"] = "1"
        self.assertEqual(authorize("", client_ip="203.0.113.9")["reason"], "signin")
        self.sign_in(APPROVED)
        self.assertTrue(authorize("", client_ip="203.0.113.9")["allow"])

    def test_zero_turns_the_provider_off(self):
        from llm_guard import authorize

        os.environ["LASERMCP_AI_DAILY_PER_IP"] = "0"
        self.sign_in(APPROVED)
        self.assertFalse(authorize("", client_ip="203.0.113.9")["allow"])


class StudioAiTests(_Iso):
    def _run(self, body, **kwargs):
        from workshop import create_studio_ai

        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), \
                patch("payas_cad.create_design", return_value=DESIGN), \
                patch("assembly_result.panels_for_viewer", return_value={"success": True, "panels": []}), \
                patch("llm_client.plan_primitives_with_llm", return_value=PLAN) as llm:
            return create_studio_ai(body, **kwargs), llm

    def test_guest_prompt_is_served_by_the_local_planner(self):
        out, llm = self._run({"prompt": LOCAL_OK, "model": "gpt-4o"}, client_ip="203.0.113.7")
        llm.assert_not_called()
        self.assertEqual(out["source"], "prompt")
        self.assertTrue(any("Sign in" in note for note in out["look_again"]))

    def test_approved_prompt_uses_an_allowed_model_only(self):
        self.sign_in(APPROVED)
        out, llm = self._run({"prompt": ASK, "model": "claude-opus-4.5"}, client_ip="203.0.113.7")
        self.assertEqual(llm.call_args.kwargs["model"], "gpt-4o-mini")
        self.assertEqual(out["source"], "prompt_llm")
        self.assertEqual(out["plan_job"]["model"], "gpt-4o-mini")
        self.assertEqual(out["plan_job"]["usage"]["output_tokens"], 1000)
        self.assertAlmostEqual(out["plan_job"]["usage"]["usd"], 0.00066)

    def test_eleventh_prompt_of_the_day_falls_back_without_a_charge(self):
        self.sign_in(APPROVED)
        for n in range(10):
            # Distinct prompts: a repeated one would be served from the draft cache for free.
            _, llm = self._run({"prompt": f"{ASK} {n}"}, client_ip="203.0.113.7")
            llm.assert_called_once()
        out, llm = self._run({"prompt": LOCAL_OK}, client_ip="203.0.113.7")
        llm.assert_not_called()
        self.assertEqual(out["source"], "prompt")
        self.assertTrue(out["look_again"][0].startswith("Daily AI limit reached"))

    def test_limit_note_leads_a_blocked_draft(self):
        from workshop import create_studio_ai

        os.environ["LASERMCP_AI_DAILY_PER_IP"] = "0"
        self.sign_in(APPROVED)
        blocked = {"success": True, "final_status": "BLOCKED", "look_again": ["a", "b", "c"]}
        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), \
                patch("payas_cad.create_design", return_value=blocked), \
                patch("assembly_result.panels_for_viewer", return_value={"success": True, "panels": []}), \
                patch("llm_client.plan_primitives_with_llm", return_value=PLAN) as llm:
            out = create_studio_ai({"prompt": LOCAL_OK}, client_ip="203.0.113.7")
        llm.assert_not_called()
        self.assertIn("limit", out["look_again"][0])
        self.assertTrue(out["look_again"][1].startswith("BLOCKED"))

    def test_uploads_and_forced_local_do_not_count(self):
        os.environ["LASERMCP_AI_DAILY_PER_IP"] = "1"
        self.sign_in(APPROVED)
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 3"><path d="M0 0 H4 V3 H0 Z"/></svg>'
        _, llm = self._run({"svg": svg}, client_ip="203.0.113.7")
        llm.assert_not_called()
        _, llm = self._run({"prompt": ASK, "planner": "local"}, client_ip="203.0.113.7")
        llm.assert_not_called()
        _, llm = self._run({"prompt": ASK}, client_ip="203.0.113.7")
        llm.assert_called_once()

    def test_public_quote_says_nothing_about_the_key_itself(self):
        from workshop import estimate_ai_prompt_cost

        quote = estimate_ai_prompt_cost({"prompt": "180x120x70 kutu", "model": "gpt-4o"})
        self.assertNotIn("sk-", str(quote))
        self.assertEqual(set(quote["workshop_llm_keys"][0]), {"provider", "configured"})
        self.assertFalse(quote["llm_access"]["eligible"])
        self.assertEqual(quote["studio_ai"]["usd"]["total"], 0.0)
        self.assertEqual(quote["studio_models"]["default"], "gpt-4o-mini")
        self.sign_in(APPROVED)
        quote = estimate_ai_prompt_cost({"prompt": "180x120x70 kutu", "model": "gpt-4o"})
        self.assertTrue(quote["llm_access"]["eligible"])
        self.assertEqual(quote["llm_access"]["daily_per_ip"], 10)
        self.assertGreater(quote["studio_ai"]["usd"]["total"], 0.0)


class RouteTests(_Iso):
    def test_route_hands_the_caller_address_to_the_guard(self):
        from mcp.server.transport_security import TransportSecuritySettings
        from starlette.testclient import TestClient

        import server

        app = server.mcp.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        with patch("workshop.create_studio_ai", return_value={"success": True}) as made, TestClient(app) as client:
            self.assertEqual(client.post("/api/studio/ai", json={"prompt": "kutu"}).status_code, 200)
            self.assertEqual(client.get("/api/studio/ai?prompt=kutu").status_code, 200)
        self.assertEqual(made.call_count, 2)
        for call in made.call_args_list:
            self.assertTrue(call.kwargs["client_ip"])


class OperatorKeyTests(_Iso):
    def _client(self):
        from mcp.server.transport_security import TransportSecuritySettings
        from starlette.testclient import TestClient

        import server

        app = server.mcp.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        return TestClient(app)

    def test_users_cannot_read_or_add_provider_keys(self):
        user = {"id": "u-ok", "email": "student@example.com", "approval_status": "approved"}
        with patch("supabase_auth.session_user", return_value=user), \
                patch("supabase_auth.user_by_id", return_value=user), self._client() as client:
            client.cookies.set("lmcp_sid", "x")
            self.assertEqual(client.get("/api/account/llm-keys").status_code, 403)
            posted = client.post("/api/account/llm-keys", json={"provider": "openai", "key": "sk-user-key-1234567890"})
            self.assertEqual(posted.status_code, 403)
            self.assertNotIn("sk-", client.get("/api/account/llm-keys").text)
        from llm_keys import list_status

        self.assertFalse(any(row["source"] == "stored" for row in list_status()))

    def test_quote_does_not_send_users_to_add_a_key(self):
        from workshop import estimate_ai_prompt_cost

        os.environ.pop("OPENAI_API_KEY", None)
        quote = estimate_ai_prompt_cost({"prompt": "kutu"})
        self.assertNotIn("Hesap → LLM", str(quote))


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClientTests(_Iso):
    def test_provider_error_text_stays_out_of_the_reply(self):
        from llm_client import plan_primitives_with_llm

        body = b'{"error":{"message":"Incorrect API key provided: sk-test-****0000","code":"invalid_api_key"}}'
        denied = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(body))
        with patch("llm_client.urllib.request.urlopen", side_effect=denied), self.assertLogs("lasermcp.llm"):
            with self.assertRaises(ValueError) as raised:
                plan_primitives_with_llm("kutu", model="gpt-4o-mini")
        self.assertEqual(str(raised.exception), "LLM HTTP 401 (invalid_api_key)")

    def test_output_is_capped_and_usage_comes_back(self):
        import json

        from llm_client import plan_primitives_with_llm

        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-not-a-real-key"
        os.environ["LASERMCP_LLM_MAX_OUTPUT_TOKENS"] = "1200"
        sent = []
        text = '{"primitives":[{"type":"box","x":10,"y":10,"h":10}],"parameters":{}}'

        def reply(request, timeout=None):
            sent.append(json.loads(request.data))
            if "anthropic" in request.full_url:
                data = {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 11, "output_tokens": 22}}
            else:
                data = {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 5, "completion_tokens": 6}}
            return _Reply(json.dumps(data).encode())

        with patch("llm_client.urllib.request.urlopen", side_effect=reply):
            old = plan_primitives_with_llm("kutu", model="claude-haiku-4.5")
            new = plan_primitives_with_llm("kutu", model="claude-sonnet-5-5")
            mini = plan_primitives_with_llm("kutu", model="gpt-4o-mini")
        self.assertEqual(old["usage"], {"input_tokens": 11, "output_tokens": 22, "cache_read_tokens": 0, "cache_write_tokens": 0})
        self.assertEqual(mini["usage"], {"input_tokens": 5, "output_tokens": 6})
        self.assertEqual([row.get("max_tokens") for row in sent], [1200, 1200, 1200])
        self.assertIn("temperature", sent[0])
        self.assertEqual(sent[1]["model"], "claude-sonnet-5-5")
        self.assertNotIn("temperature", sent[1])
        # Current Claude models draft at low effort; the fixed system prompt is cacheable.
        self.assertEqual(sent[1]["output_config"], {"effort": "low"})
        self.assertNotIn("output_config", sent[0])
        self.assertEqual(sent[1]["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIn("Primitive grammar", sent[1]["system"][0]["text"])
        self.assertEqual(sent[1]["system"][0]["text"], sent[2]["messages"][0]["content"])

    def test_cut_off_reply_is_reported_as_the_cap(self):
        import json

        from llm_client import plan_primitives_with_llm

        data = {"choices": [{"finish_reason": "length", "message": {"content": '{"primitives":['}}]}
        with patch("llm_client.urllib.request.urlopen", return_value=_Reply(json.dumps(data).encode())):
            with self.assertRaises(ValueError) as raised:
                plan_primitives_with_llm("kutu", model="gpt-4o-mini")
        self.assertIn("LASERMCP_LLM_MAX_OUTPUT_TOKENS", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
