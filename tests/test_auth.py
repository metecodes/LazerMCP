import os
import tempfile
import unittest


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = self.tmp
        for key in (
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "LASERMCP_ORG_DOMAINS",
            "LASERMCP_OAUTH_REDIRECT_HOSTS",
            "MCP_AUTH_TOKEN",
            "VERCEL",
        ):
            os.environ.pop(key, None)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MCP_DATA_DIR", None)
        else:
            os.environ["MCP_DATA_DIR"] = self.old
        for key in (
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "LASERMCP_ORG_DOMAINS",
            "LASERMCP_OAUTH_REDIRECT_HOSTS",
            "MCP_AUTH_TOKEN",
            "VERCEL",
        ):
            os.environ.pop(key, None)

    def test_file_download_is_attachment(self):
        from server import _file_payload, _safe_download_name, _wants_inline_file
        from starlette.requests import Request

        self.assertEqual(_safe_download_name("../x.svg"), "x.svg")

        file_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        down = _file_payload(file_bytes, "box.svg", "image/svg+xml", inline=False)
        self.assertEqual(down.headers["content-disposition"], 'attachment; filename="box.svg"')
        self.assertEqual(down.media_type, "application/octet-stream")
        preview = _file_payload(file_bytes, "box.svg", "image/svg+xml", inline=True)
        self.assertIn("inline", preview.headers["content-disposition"])
        self.assertEqual(preview.media_type, "image/svg+xml")
        scope = {"type": "http", "method": "GET", "path": "/files/box.svg", "query_string": b"view=1", "headers": []}
        self.assertTrue(_wants_inline_file(Request(scope)))

    def test_missing_file_is_html_for_browsers(self):
        from server import _missing_output, _prefers_html
        from starlette.requests import Request

        html_scope = {
            "type": "http",
            "method": "GET",
            "path": "/files/gone.svg",
            "query_string": b"",
            "headers": [(b"accept", b"text/html,application/xhtml+xml")],
        }
        req = Request(html_scope)
        self.assertTrue(_prefers_html(req))
        page = _missing_output(req, signed_in=False)
        self.assertEqual(page.status_code, 404)
        self.assertIn("text/html", page.media_type)
        self.assertNotIn(b"Not found.", page.body)
        json_scope = dict(html_scope)
        json_scope["headers"] = [(b"accept", b"application/json")]
        api = _missing_output(Request(json_scope), signed_in=True)
        self.assertEqual(api.media_type, "application/json")
        self.assertNotIn("Not found.", api.body.decode())

    def test_redirect_helper_sets_location(self):
        from server import _redirect

        gone = _redirect("https://claude.ai/api/mcp/auth_callback")
        self.assertEqual(gone.status_code, 302)
        self.assertEqual(gone.headers["location"], "https://claude.ai/api/mcp/auth_callback")
        browser = _redirect("https://example.supabase.co/auth/v1/authorize", status=200)
        self.assertEqual(browser.status_code, 200)
        self.assertIn("example.supabase.co", browser.body.decode())

    def test_mcp_http_keeps_chatgpt_session(self):
        from server import mcp_http_kwargs

        kwargs = mcp_http_kwargs()
        self.assertIsNone(kwargs["session_idle_timeout"])
        self.assertEqual(kwargs["retry_interval"], 3000)
        self.assertFalse(kwargs["stateless_http"])
        self.assertFalse(kwargs["json_response"])
        os.environ["VERCEL"] = "1"
        hosted = mcp_http_kwargs()
        self.assertTrue(hosted["stateless_http"])
        self.assertTrue(hosted["json_response"])

    def test_oauth_metadata(self):
        from oauth_mcp import metadata, resource_metadata

        meta = metadata("https://mcp.metehanavci.com")
        self.assertEqual(meta["authorization_endpoint"], "https://mcp.metehanavci.com/oauth/authorize")
        self.assertIn("S256", meta["code_challenge_methods_supported"])
        self.assertEqual(meta["grant_types_supported"], ["authorization_code", "refresh_token"])
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
        self.assertTrue(tok["refresh_token"].startswith("mcpr_"))
        self.assertEqual(tok["expires_in"], 30 * 24 * 3600)
        prin = resolve_oauth_token(tok["access_token"])
        self.assertEqual(prin["email"], "a@b.com")
        self.assertEqual(prin["kind"], "individual")
        self.assertIsNone(resolve_oauth_token(tok["refresh_token"]))

    def test_oauth_refresh_rotates_tokens(self):
        import base64
        import hashlib

        from oauth_mcp import exchange_token, issue_code, resolve_oauth_token

        verifier = "b" * 43
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        code = issue_code(
            client_id="cli_refresh",
            redirect_uri="https://chatgpt.com/connector/oauth/callback",
            state="s",
            challenge=challenge,
            user={"id": "u2", "email": "b@c.com", "name": "B", "kind": "org"},
        )
        first = exchange_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "https://chatgpt.com/connector/oauth/callback",
            }
        )
        rotated = exchange_token(
            {"grant_type": "refresh_token", "refresh_token": first["refresh_token"]}
        )
        self.assertNotEqual(rotated["access_token"], first["access_token"])
        self.assertNotEqual(rotated["refresh_token"], first["refresh_token"])
        self.assertEqual(resolve_oauth_token(rotated["access_token"])["email"], "b@c.com")
        self.assertEqual(resolve_oauth_token(rotated["access_token"])["kind"], "org")
        self.assertEqual(resolve_oauth_token(first["access_token"])["email"], "b@c.com")
        again = exchange_token({"grant_type": "refresh_token", "refresh_token": first["refresh_token"]})
        self.assertEqual(resolve_oauth_token(again["access_token"])["email"], "b@c.com")

    def test_signed_oauth_survives_empty_store(self):
        import base64
        import hashlib
        from pathlib import Path

        from oauth_mcp import exchange_token, issue_code, resolve_oauth_token

        verifier = "c" * 43
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        code = issue_code(
            client_id="cli_stateless",
            redirect_uri="https://chatgpt.com/connector/oauth/callback",
            state="s",
            challenge=challenge,
            user={"id": "u3", "email": "d@e.com", "name": "D", "kind": "individual"},
        )
        for name in ("oauth_codes.json", "oauth_tokens.json", "oauth_clients.json"):
            path = Path(self.tmp) / name
            if path.is_file():
                path.unlink()
        tok = exchange_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "https://chatgpt.com/connector/oauth/callback",
            }
        )
        self.assertEqual(resolve_oauth_token(tok["access_token"])["email"], "d@e.com")
        self.assertTrue(tok["access_token"].startswith("mcp_"))
        self.assertIn(".", tok["access_token"])

    def test_oauth_refresh_rejects_access_token(self):
        from oauth_mcp import exchange_token

        with self.assertRaises(ValueError):
            exchange_token({"grant_type": "refresh_token", "refresh_token": "mcp_not_a_refresh"})
        with self.assertRaises(ValueError):
            exchange_token({"grant_type": "client_credentials"})

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

    def test_public_config_reports_session_ready(self):
        os.environ.pop("MCP_ENV", None)
        os.environ.pop("VERCEL", None)
        os.environ.pop("MCP_SESSION_SECRET", None)
        from supabase_auth import public_config

        cfg = public_config("https://mcp.metehanavci.com/mcp")
        self.assertTrue(cfg["session_ready"])
        self.assertEqual(cfg["look_again"], [])

    def test_session_user_ignores_bad_signature_length(self):
        from supabase_auth import session_user

        self.assertIsNone(session_user("aaa.bb"))

    def test_overview_keys_are_owner_scoped(self):
        from importlib import reload

        import keys
        import studio

        reload(keys)
        reload(studio)
        keys.create_key("mine", owner="u1", email="a@y.com")
        keys.create_key("theirs", owner="u2", email="b@y.com")
        token = keys.current_auth.set({"id": "u1", "email": "a@y.com"})
        try:
            names = {row.get("name") for row in studio.overview()["keys"]}
        finally:
            keys.current_auth.reset(token)
        self.assertEqual(names, {"mine"})
        self.assertEqual(studio.overview()["keys"], [])


if __name__ == "__main__":
    unittest.main()
