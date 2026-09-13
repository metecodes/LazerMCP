import asyncio
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlparse, parse_qs
from starlette.requests import Request


class SigninUXTests(unittest.TestCase):
    def request(self, nxt=""):
        return Request({"type": "http", "method": "GET", "path": "/api/auth/start",
                        "scheme": "https", "server": ("app.example", 443),
                        "headers": [(b"host", b"app.example")],
                        "query_string": urlencode({"next": nxt}).encode()})

    def start(self, nxt="", user=None, ready=True):
        import server
        with patch("supabase_auth.configured", return_value=True), \
             patch("supabase_auth.session_ready", return_value=ready), \
             patch("supabase_auth.session_user", return_value=user), \
             patch("supabase_auth.supabase_url", return_value="https://auth.example"), \
             patch("supabase_auth.supabase_anon_key", return_value="public-test-key"), \
             patch.object(server, "PUBLIC_BASE_URL", ""):
            return asyncio.run(server.api_auth_start(self.request(nxt)))

    def test_direct_provider_url_preserves_oauth_destination(self):
        nxt = "/oauth/authorize?client_id=client&state=original"
        response = self.start(nxt)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        url = urlparse(json.loads(response.body)["url"])
        self.assertEqual(url.netloc, "auth.example")
        callback = parse_qs(url.query)["redirect_to"][0]
        self.assertEqual(parse_qs(urlparse(callback).query)["next"], [nxt])

    def test_existing_session_skips_google(self):
        response = self.start("/connect", user={"id": "test"}, ready=False)
        self.assertEqual(json.loads(response.body), {"url": "/connect", "signed_in": True})

    def test_external_redirect_and_callback_loops_fall_back(self):
        for nxt in ("https://evil.example", "//evil.example", "https://app.example//evil.example", "/auth/callback", "/auth/google?next=/account"):
            with self.subTest(nxt=nxt):
                self.assertEqual(json.loads(self.start(nxt, user={"id": "test"}).body)["url"], "/dashboard")

    def test_unavailable_session_returns_actionable_failure_not_redirect_loop(self):
        response = self.start(ready=False)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("url", json.loads(response.body))

    def test_callback_is_separate_from_account_and_not_cached(self):
        from server import auth_callback_page
        response = asyncio.run(auth_callback_page(self.request()))
        self.assertEqual(response.path.name, "auth-callback.html")
        self.assertEqual(response.headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
