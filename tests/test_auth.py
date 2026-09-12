import os
import tempfile
import unittest


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = self.tmp
        for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "LASERMCP_ORG_DOMAINS", "LASERMCP_OAUTH_REDIRECT_HOSTS"):
            os.environ.pop(key, None)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MCP_DATA_DIR", None)
        else:
            os.environ["MCP_DATA_DIR"] = self.old
        for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "LASERMCP_ORG_DOMAINS", "LASERMCP_OAUTH_REDIRECT_HOSTS"):
            os.environ.pop(key, None)

    def test_redirect_helper_sets_location(self):
        from server import _redirect

        gone = _redirect("https://claude.ai/api/mcp/auth_callback")
        self.assertEqual(gone.status_code, 302)
        self.assertEqual(gone.headers["location"], "https://claude.ai/api/mcp/auth_callback")
        browser = _redirect("https://example.supabase.co/auth/v1/authorize", status=200)
        self.assertEqual(browser.status_code, 200)
        self.assertIn("example.supabase.co", browser.body.decode())

    def test_oauth_metadata(self):
        from oauth_mcp import metadata, resource_metadata

        meta = metadata("https://mcp.metehanavci.com")
        self.assertEqual(meta["authorization_endpoint"], "https://mcp.metehanavci.com/oauth/authorize")
        self.assertIn("S256", meta["code_challenge_methods_supported"])
        res = resource_metadata("https://mcp.metehanavci.com")
        self.assertEqual(res["resource"], "https://mcp.metehanavci.com/mcp")

    def test_pkce_token_roundtrip(self):
        import base64
        import hashlib

        from oauth_mcp import exchange_token, issue_code, resolve_oauth_token

        verifier = "a" * 43
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        code = issue_code(
            client_id="cli_test",
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            state="s",
            challenge=challenge,
            user={"id": "u1", "email": "a@b.com", "name": "A", "kind": "individual"},
        )
        tok = exchange_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            }
        )
        self.assertTrue(tok["access_token"].startswith("mcp_"))
        prin = resolve_oauth_token(tok["access_token"])
        self.assertEqual(prin["email"], "a@b.com")
        self.assertEqual(prin["kind"], "individual")

    def test_org_key_and_auth_required(self):
        from keys import auth_required, create_key, resolve_key
        from supabase_auth import can_mint_keys

        self.assertFalse(auth_required())
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "anon"
        from importlib import reload
        import supabase_auth
        import keys

        reload(supabase_auth)
        reload(keys)
        self.assertTrue(keys.auth_required())
        self.assertFalse(can_mint_keys({"kind": "org", "email": "x@y.com"}))
        os.environ["LASERMCP_ORG_DOMAINS"] = "y.com"
        self.assertTrue(can_mint_keys({"kind": "individual", "email": "x@y.com"}))
        self.assertFalse(can_mint_keys({"kind": "org", "email": "x@other.com"}))
        created = create_key("atolye", owner="u1", email="x@y.com", kind="org")
        self.assertTrue(created["token"].startswith("lzr_"))
        self.assertEqual(resolve_key(created["token"])["kind"], "org")

    def test_oauth_rejects_unknown_redirect(self):
        from oauth_mcp import issue_code, register_client

        with self.assertRaises(ValueError):
            issue_code(
                client_id="attacker",
                redirect_uri="https://evil.example/cb",
                state="s",
                challenge="abc",
                user={"id": "u1", "email": "a@b.com"},
            )
        with self.assertRaises(ValueError):
            register_client({"redirect_uris": ["https://evil.example/cb"]})

    def test_safe_next_path(self):
        from supabase_auth import safe_next_path

        origin = "https://mcp.metehanavci.com"
        self.assertEqual(safe_next_path("/connect", origins=[origin]), "/connect")
        self.assertEqual(
            safe_next_path("/oauth/authorize?client_id=x", origins=[origin]),
            "/oauth/authorize?client_id=x",
        )
        self.assertEqual(safe_next_path("https://evil.example/", origins=[origin]), "")
        self.assertEqual(safe_next_path("//evil.example", origins=[origin]), "")
        self.assertEqual(
            safe_next_path("https://mcp.metehanavci.com/app", origins=[origin]),
            "/app",
        )

    def test_upsert_ignores_client_org_kind(self):
        from supabase_auth import upsert_user

        guest = upsert_user({"id": "1", "email": "a@gmail.com", "name": "A"}, kind="org")
        self.assertEqual(guest["kind"], "individual")
        os.environ["LASERMCP_ORG_DOMAINS"] = "payas.edu.tr"
        org = upsert_user({"id": "2", "email": "b@payas.edu.tr", "name": "B"})
        self.assertEqual(org["kind"], "org")

    def test_signed_session_survives_without_store(self):
        from supabase_auth import new_session, session_user

        sid = new_session({"id": "u9", "email": "ada@b.com", "name": "Ada"})
        self.assertEqual(session_user(sid)["email"], "ada@b.com")
        self.assertEqual(session_user(sid)["name"], "Ada")
        self.assertIsNone(session_user(sid + "tamper"))
        self.assertIsNone(session_user("not-a-session"))

    def test_overview_keys_are_owner_scoped(self):
        from keys import create_key, current_auth
        from studio import overview

        create_key("mine", owner="u1", email="a@y.com")
        create_key("theirs", owner="u2", email="b@y.com")
        token = current_auth.set({"id": "u1", "email": "a@y.com"})
        try:
            names = {row.get("name") for row in overview()["keys"]}
        finally:
            current_auth.reset(token)
        self.assertEqual(names, {"mine"})
        self.assertEqual(overview()["keys"], [])


if __name__ == "__main__":
    unittest.main()
