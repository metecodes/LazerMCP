"""Regression tests for the 2026-11 security audit fixes."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class SecurityFixTests(unittest.TestCase):
    def test_svg_fetch_rejects_local_and_private_urls(self):
        from reference_upload import fetch_public_svg

        for url in (
            "file:///etc/passwd",
            "http://example.com/a.svg",
            "https://127.0.0.1/a.svg",
            "https://169.254.169.254/latest/meta-data/",
            "https://user:pw@example.com/a.svg",
        ):
            with self.assertRaises(ValueError, msg=url):
                fetch_public_svg(url)

    def test_validate_svg_tool_does_not_read_local_files(self):
        from server import validate_svg

        result = validate_svg(url="file:///etc/passwd")
        text = str(result)
        self.assertNotIn("root:", text)
        self.assertIn("public HTTPS", text)

    def test_inline_files_are_sandboxed(self):
        from server import _file_payload

        preview = _file_payload(b"<svg/>", "x.svg", "image/svg+xml", inline=True)
        self.assertIn("sandbox", preview.headers["content-security-policy"])
        self.assertIn("default-src 'none'", preview.headers["content-security-policy"])

    def test_dev_session_secret_is_not_the_public_constant(self):
        import hashlib

        os.environ.pop("MCP_SESSION_SECRET", None)
        os.environ.pop("VERCEL", None)
        os.environ.pop("MCP_ENV", None)
        from supabase_auth import _session_secret

        self.assertNotEqual(_session_secret(), hashlib.sha256(b"lasermcp-dev-session").digest())

    def test_unconfirmed_email_cannot_sign_in(self):
        from supabase_auth import _identity_from_user_payload

        self.assertIsNone(_identity_from_user_payload({"id": "u1", "email": "metehan1387@gmail.com"}))
        ok = _identity_from_user_payload(
            {"id": "u1", "email": "a@example.com", "email_confirmed_at": "2026-01-01T00:00:00Z"}
        )
        self.assertEqual(ok["email"], "a@example.com")


if __name__ == "__main__":
    unittest.main()
