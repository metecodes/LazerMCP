"""Rate limits on guest-facing routes and the shared (cross-instance) counter."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient

_ENV = ("MCP_DATA_DIR", "MCP_ENV", "VERCEL", "SUPABASE_URL", "SUPABASE_ANON_KEY",
        "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "MCP_AUTH_TOKEN")


class _Iso(unittest.TestCase):
    def setUp(self):
        from persist.rate_limit import reset

        self.old = {key: os.environ.get(key) for key in _ENV}
        for key in _ENV:
            os.environ.pop(key, None)
        os.environ["MCP_DATA_DIR"] = tempfile.mkdtemp()
        reset()

    def tearDown(self):
        from persist.rate_limit import reset

        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset()


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SharedCounterTests(_Iso):
    def _supabase(self):
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "service-role-for-tests"

    def test_local_only_never_calls_out(self):
        from persist.rate_limit import check

        self._supabase()
        with patch("persist.rate_limit.urllib.request.urlopen") as net:
            self.assertTrue(check("k", "a", limit=1, window_sec=60))
            self.assertFalse(check("k", "a", limit=1, window_sec=60))
        net.assert_not_called()

    def test_shared_verdict_wins_and_identity_is_hashed(self):
        from persist.rate_limit import check

        self._supabase()
        seen = []

        def reply(request, timeout=None):
            seen.append(json.loads(request.data))
            return _Reply(b"false")

        with patch("persist.rate_limit.urllib.request.urlopen", side_effect=reply):
            # In-memory would allow the first hit; the shared counter says another instance used it up.
            self.assertFalse(check("password-account", "person@example.com", limit=5, window_sec=60, shared=True))
        self.assertEqual(seen[0]["p_limit"], 5)
        self.assertNotIn("person@example.com", seen[0]["p_bucket"])

    def test_missing_function_falls_back_to_memory_and_backs_off(self):
        from persist.rate_limit import check

        self._supabase()
        missing = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))
        with patch("persist.rate_limit.urllib.request.urlopen", side_effect=missing) as net:
            self.assertTrue(check("k", "a", limit=2, window_sec=60, shared=True))
            self.assertTrue(check("k", "a", limit=2, window_sec=60, shared=True))
            self.assertFalse(check("k", "a", limit=2, window_sec=60, shared=True))
        self.assertEqual(net.call_count, 1)

    def test_without_supabase_shared_is_memory(self):
        from persist.rate_limit import check

        with patch("persist.rate_limit.urllib.request.urlopen") as net:
            self.assertTrue(check("k", "a", limit=1, window_sec=60, shared=True))
            self.assertFalse(check("k", "a", limit=1, window_sec=60, shared=True))
        net.assert_not_called()


class RouteLimitTests(_Iso):
    def _client(self):
        import server

        app = server.mcp.streamable_http_app(
            streamable_http_path="/mcp", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        return TestClient(app)

    def test_guest_account_probe_is_not_an_error(self):
        with self._client() as client:
            quiet = client.get("/api/account?optional=1")
            self.assertEqual(quiet.status_code, 200)
            self.assertIs(quiet.json()["signed_in"], False)
            self.assertIsNone(quiet.json()["user"])
            self.assertEqual(client.get("/api/account").status_code, 401)

    def test_studio_writes_are_capped_but_previews_keep_working(self):
        made = {"success": True, "file_id": "x.svg"}
        with patch("server.STUDIO_WRITE_LIMIT", (2, 3600)), \
                patch("workshop.create_studio_box", return_value=made) as box, self._client() as client:
            self.assertEqual(client.post("/api/studio/box", json={"x": 100}).status_code, 200)
            self.assertEqual(client.post("/api/studio/box", json={"x": 100}).status_code, 200)
            blocked = client.post("/api/studio/box", json={"x": 100})
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers.get("retry-after"), "60")
            self.assertEqual(box.call_count, 2)
            # Scrubbing a slider is counted separately from saving.
            self.assertEqual(client.post("/api/studio/box", json={"x": 100, "preview": True}).status_code, 200)
            self.assertEqual(client.get("/api/studio/profiles").status_code, 200)

    def test_password_attempts_are_capped_per_account(self):
        with patch("server.PASSWORD_ACCOUNT_LIMIT", (2, 900)), \
                patch("supabase_auth.configured", return_value=True), \
                patch("supabase_auth.password_grant", return_value=(None, "Invalid email or password.")) as grant, \
                self._client() as client:
            body = {"email": "Person@Example.com", "password": "wrong"}
            self.assertEqual(client.post("/api/auth/password", json=body).status_code, 401)
            self.assertEqual(client.post("/api/auth/password", json=body).status_code, 401)
            self.assertEqual(client.post("/api/auth/password", json={**body, "email": "person@example.com"}).status_code, 429)
            self.assertEqual(grant.call_count, 2)
            # Another account from the same address is still within the address limit.
            other = client.post("/api/auth/password", json={"email": "other@example.com", "password": "wrong"})
            self.assertEqual(other.status_code, 401)

    def test_forwarded_address_is_only_trusted_on_the_platform(self):
        import server
        from starlette.requests import Request

        def request(headers):
            raw = [(k.encode(), v.encode()) for k, v in headers.items()]
            return Request({"type": "http", "headers": raw, "client": ("10.0.0.9", 1234)})

        with patch("server.IS_VERCEL", False):
            self.assertEqual(server._client_ip(request({"x-forwarded-for": "1.2.3.4"})), "10.0.0.9")
        with patch("server.IS_VERCEL", True):
            self.assertEqual(server._client_ip(request({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})), "1.2.3.4")
            self.assertEqual(server._client_ip(request({"x-real-ip": "5.6.7.8", "x-forwarded-for": "1.2.3.4"})), "5.6.7.8")


if __name__ == "__main__":
    unittest.main()
