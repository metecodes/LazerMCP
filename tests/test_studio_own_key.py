"""Recipe routing, the free edge repair, and Studio AI on a user's own provider key."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tests.test_llm_guard import APPROVED, ASK, DESIGN, GATE, PENDING, PLAN, _Iso

OWN_KEY = "sk-own-test-not-a-real-key-0000000000"
BLOCKED = {"success": True, "final_status": "BLOCKED", "file_id": "b.svg", "look_again": ["x"]}


class RecipeTests(_Iso):
    def test_prompts_map_to_fixed_recipes(self):
        from ai_cache import match_maker

        self.assertEqual(match_maker("ön yüzünde giriş deliği olan kuş evi"), {"maker": "birdhouse"})
        self.assertEqual(
            match_maker("150x120x140 kuş evi 28 mm giriş"),
            {"maker": "birdhouse", "x": 150.0, "y": 120.0, "h": 140.0, "entrance_mm": 28.0},
        )
        self.assertEqual(match_maker("'Elif' yazan anahtarlık"), {"maker": "name_ornament", "text": "Elif"})
        self.assertEqual(match_maker("yılbaşı yıldız süsü 9 cm"), {"maker": "christmas", "shape": "star", "size": 90.0})
        self.assertEqual(match_maker("menteşeli kutu 140x90x50")["maker"], "flexible_box")
        gift = match_maker('"İyi ki doğdun" yazan hediye kutusu 12cm x 8cm x 5cm')
        self.assertEqual((gift["maker"], gift["text"], gift["x"]), ("named_gift", "İyi ki doğdun", 120.0))
        # No name to engrave, or more than the recipe draws: left to the model.
        self.assertIsNone(match_maker("isim süsü"))
        self.assertIsNone(match_maker("çekmeceli hediye kutusu"))
        self.assertIsNone(match_maker("telefon standı"))

    def test_recipe_prompt_never_reaches_a_model_and_passes(self):
        from workshop import create_studio_ai

        self.sign_in(APPROVED)
        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), \
                patch("llm_client.plan_primitives_with_llm", return_value=PLAN) as llm:
            # Studio sends the thread with the prompt as its single user turn.
            out = create_studio_ai({"prompt": "kuş evi", "messages": [{"role": "user", "text": "kuş evi"}]}, client_ip="203.0.113.7")
            again = create_studio_ai(
                {"prompt": "kuş evi", "messages": [{"role": "user", "text": "kuş evi"}, {"role": "assistant", "text": "Hazır"},
                                                   {"role": "user", "text": "çatıyı büyüt"}]},
                client_ip="203.0.113.7",
            )
        self.assertEqual(out["final_status"], "PROTOTYPE READY")
        self.assertEqual(out["plan_job"]["method"], "studio_maker")
        self.assertEqual(len(out["assembly"]["panels"]), 6)
        # A revision turn is a conversation: that one goes to the model.
        llm.assert_called_once()
        self.assertEqual(again["source"], "prompt_llm")


class FreeRepairTests(_Iso):
    def test_only_named_finger_edges_are_straightened(self):
        from workshop import _straighten_unmatched_edges

        parts = [{"type": "panel", "label": "A", "edges": "FfeF"}, {"type": "panel", "label": "b", "edges": "ffff"},
                 {"type": "box", "label": "c"}]
        notes = ["female edge a.bottom (100.0 mm) has no matching f fingers",
                 "male edge a.right (40.0 mm) has no matching F holes", "c role=structural has mates=[]"]
        fixed = _straighten_unmatched_edges(parts, notes)
        self.assertEqual(fixed[0]["edges"], "eeeF")
        self.assertEqual(fixed[1], parts[1])
        self.assertEqual(parts[0]["edges"], "FfeF")
        self.assertIsNone(_straighten_unmatched_edges(parts, ["slot on a has no explicit matching tab"]))

    def test_free_fix_is_used_before_a_paid_repair(self):
        from workshop import create_studio_ai

        self.sign_in(APPROVED)
        draft = {**PLAN, "primitives": [{"type": "panel", "label": "a", "w": 100, "h": 40, "edges": "Feee"}]}
        blocked = {**BLOCKED, "look_again": ["female edge a.bottom (100.0 mm) has no matching f fingers"]}
        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), \
                patch("payas_cad.create_design", side_effect=[blocked, DESIGN]) as made, \
                patch("assembly_result.panels_for_viewer", return_value={"success": True, "panels": []}), \
                patch("llm_client.plan_primitives_with_llm", return_value=draft) as llm:
            out = create_studio_ai({"prompt": ASK}, client_ip="203.0.113.7")
        llm.assert_called_once()  # the draft only: the fix cost nothing
        self.assertEqual(made.call_args_list[1].kwargs["primitives"][0]["edges"], "eeee")
        self.assertEqual(out["final_status"], "PROTOTYPE READY")
        self.assertTrue(out["auto_repair"]["fixed"])


class OwnKeyTests(_Iso):
    def setUp(self):
        super().setUp()
        self.sign_in(APPROVED)

    def _run(self, body, design=DESIGN):
        from workshop import create_studio_ai

        many = isinstance(design, list)
        with patch("plans.entitled", return_value=True), patch("plans.gate_job", return_value=GATE), \
                patch("payas_cad.create_design", side_effect=design if many else None, return_value=None if many else design), \
                patch("assembly_result.panels_for_viewer", return_value={"success": True, "panels": []}), \
                patch("llm_client.plan_primitives_with_llm", return_value=PLAN) as llm:
            return create_studio_ai(body, client_ip="203.0.113.7"), llm

    def test_key_is_stored_encrypted_and_never_listed(self):
        from llm_keys import _load_user, delete_user_key, get_user_key, save_user_key, user_status

        saved = save_user_key("u-ok", "openai", OWN_KEY)
        self.assertNotIn(OWN_KEY, str(saved))
        self.assertNotIn(OWN_KEY, str(_load_user("u-ok")))
        self.assertNotIn(OWN_KEY, str(user_status("u-ok")))
        self.assertEqual(get_user_key("u-ok", "openai"), OWN_KEY)
        self.assertIsNone(get_user_key("someone-else", "openai"))
        self.assertIsNone(get_user_key("u-ok", "anthropic"))  # no fallback to the workshop env key
        self.assertTrue(delete_user_key("u-ok", "openai")["deleted"])
        self.assertIsNone(get_user_key("u-ok", "openai"))
        with self.assertRaises(ValueError):
            save_user_key("u-ok", "openai", "short")

    def test_hosted_server_without_a_secret_refuses_to_store(self):
        from llm_keys import save_user_key

        os.environ["VERCEL"] = "1"
        with self.assertRaises(ValueError):
            save_user_key("u-ok", "openai", OWN_KEY)
        os.environ["LASERMCP_SECRETS_KEY"] = "a-real-secret"
        self.addCleanup(os.environ.pop, "LASERMCP_SECRETS_KEY", None)
        with patch("llm_keys._save_user"):
            self.assertTrue(save_user_key("u-ok", "openai", OWN_KEY)["success"])

    def test_own_key_opens_astra_without_the_site_caps(self):
        from llm_guard import access, authorize
        from llm_keys import save_user_key

        self.assertEqual(access("gpt-6-astra")["model"], "gpt-4o-mini")  # not allowed on the workshop key
        save_user_key("u-ok", "openai", OWN_KEY)
        os.environ["LASERMCP_AI_DAILY_PER_IP"] = "0"  # the workshop key is closed for the day
        verdict = authorize("", client_ip="203.0.113.7")
        self.assertTrue(verdict["allow"] and verdict["own_key"])
        self.assertEqual(verdict["model"], "gpt-6-astra")
        self.assertEqual(authorize("gpt-5.5", client_ip="203.0.113.7")["model"], "gpt-5.5")
        # A Claude model needs a Claude key: that request stays on the (closed) workshop path.
        self.assertFalse(authorize("claude-sonnet-5-5", client_ip="203.0.113.7").get("own_key"))

    def test_pending_account_cannot_use_a_stored_key(self):
        from llm_guard import access
        from llm_keys import save_user_key

        save_user_key("u-wait", "openai", OWN_KEY)
        self._auth[0].reset(self._auth[1])
        self.sign_in(PENDING)
        with patch("supabase_auth.user_by_id", return_value=None):
            self.assertFalse(access("gpt-6-astra")["allow"])

    def test_studio_ai_bills_the_users_key_and_repairs_on_the_same_model(self):
        from llm_keys import save_user_key

        save_user_key("u-ok", "openai", OWN_KEY)
        out, llm = self._run({"prompt": ASK, "model": "gpt-6-astra"}, design=[BLOCKED, DESIGN])
        self.assertEqual([c.kwargs["model"] for c in llm.call_args_list], ["gpt-6-astra", "gpt-6-astra"])
        self.assertEqual([c.kwargs["key_owner"] for c in llm.call_args_list], ["u-ok", "u-ok"])
        self.assertEqual(llm.call_args_list[0].kwargs["effort"], "medium")
        self.assertTrue(out["plan_job"]["own_key"])
        self.assertTrue(any("your own openai key" in line for line in out["look_again"]))
        self.assertNotIn(OWN_KEY, str(out))

    def test_client_sends_the_users_key_not_the_workshop_key(self):
        import json

        from llm_client import plan_primitives_with_llm
        from llm_keys import save_user_key
        from tests.test_llm_guard import _Reply

        save_user_key("u-ok", "openai", OWN_KEY)
        sent = []

        def reply(request, timeout=None):
            sent.append((request.get_header("Authorization"), json.loads(request.data)))
            text = '{"primitives":[{"type":"box","x":10,"y":10,"h":10}],"parameters":{}}'
            return _Reply(json.dumps({"choices": [{"message": {"content": text}}], "usage": {}}).encode())

        with patch("llm_client.urllib.request.urlopen", side_effect=reply):
            plan_primitives_with_llm("stand", model="gpt-6-astra", key_owner="u-ok", effort="high")
            with self.assertRaises(ValueError):
                plan_primitives_with_llm("stand", model="gpt-6-astra", key_owner="nobody")
        self.assertEqual(sent[0][0], "Bearer " + OWN_KEY)
        self.assertEqual(sent[0][1]["reasoning_effort"], "high")
        self.assertGreaterEqual(sent[0][1]["max_completion_tokens"], 8000)

    def test_quote_lists_the_models_the_key_opens(self):
        from llm_keys import save_user_key
        from workshop import estimate_ai_prompt_cost

        save_user_key("u-ok", "openai", OWN_KEY)
        quote = estimate_ai_prompt_cost({"prompt": ASK})
        ids = [m["id"] for m in quote["studio_models"]["allowed"]]
        self.assertTrue(quote["studio_models"]["own_key"])
        self.assertEqual(quote["studio_models"]["default"], "gpt-6-astra")
        self.assertEqual(ids[0], "gpt-6-astra")
        self.assertIn("gpt-4o-mini", ids)
        self.assertFalse(any(i.startswith("claude") for i in ids))
        self.assertTrue(quote["llm_access"]["own_key"])
        self.assertNotIn(OWN_KEY, str(quote))


class OwnKeyRouteTests(_Iso):
    def _client(self):
        from mcp.server.transport_security import TransportSecuritySettings
        from starlette.testclient import TestClient

        import server

        app = server.mcp.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        return TestClient(app)

    def test_route_needs_sign_in_verifies_and_hides_the_key(self):
        user = {**APPROVED, "email": "maker@example.com"}
        with self._client() as client:
            self.assertEqual(client.get("/api/account/my-llm-keys").status_code, 401)
            with patch("supabase_auth.session_user", return_value=user), patch("supabase_auth.user_by_id", return_value=user), \
                    patch("server.BearerGate._principal", return_value=user):
                with patch("server._verify_provider_key", return_value="bad"):
                    bad = client.post("/api/account/my-llm-keys", json={"provider": "openai", "key": OWN_KEY})
                self.assertEqual(bad.status_code, 400)
                with patch("server._verify_provider_key", return_value="ok"):
                    good = client.post("/api/account/my-llm-keys", json={"provider": "openai", "key": OWN_KEY})
                self.assertEqual(good.status_code, 200, good.text)
                self.assertTrue(good.json()["verified"])
                self.assertNotIn(OWN_KEY, good.text)
                listed = client.get("/api/account/my-llm-keys")
                self.assertNotIn(OWN_KEY, listed.text)
                self.assertTrue(listed.json()["keys"][0]["configured"])
                gone = client.request("DELETE", "/api/account/my-llm-keys", json={"provider": "openai"})
                self.assertTrue(gone.json()["deleted"])


if __name__ == "__main__":
    unittest.main()
