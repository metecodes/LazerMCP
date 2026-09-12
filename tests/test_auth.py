import os
import tempfile
import unittest


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = self.tmp
        for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
            os.environ.pop(key, None)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MCP_DATA_DIR", None)
        else:
            os.environ["MCP_DATA_DIR"] = self.old
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_ANON_KEY", None)

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
        self.assertTrue(can_mint_keys({"kind": "org", "email": "x@y.com"}))
        self.assertFalse(can_mint_keys({"kind": "individual", "email": "x@y.com"}))
        created = create_key("atolye", owner="u1", email="x@y.com", kind="org")
        self.assertTrue(created["token"].startswith("lzr_"))
        self.assertEqual(resolve_key(created["token"])["kind"], "org")


if __name__ == "__main__":
    unittest.main()
