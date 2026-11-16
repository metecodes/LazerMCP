"""The door in front of the local model: what it lets through and what it refuses."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "local_model"))

import tunnel_proxy as tp

KEY = "lmk_test-key"
GOOD = json.dumps({"model": "lasermcp", "messages": [{"role": "user", "content": "kutu"}]}).encode()


def check(method="POST", path="/v1/chat/completions", auth=f"Bearer {KEY}", body=GOOD, key=KEY):
    return tp.check(method, path, auth, body, key)[0]


class CheckTests(unittest.TestCase):
    def test_a_design_request_with_the_key_passes(self):
        self.assertEqual(check(), 200)

    def test_no_key_or_a_wrong_key_is_refused(self):
        for auth in ("", "Bearer", "Bearer wrong", f"Basic {KEY}", KEY):
            with self.subTest(auth=auth):
                self.assertEqual(check(auth=auth), 401)

    def test_a_proxy_without_a_key_serves_nobody(self):
        self.assertEqual(check(key="", auth="Bearer "), 503)

    def test_the_rest_of_ollama_is_not_reachable(self):
        # Pulling, deleting and listing models, and every other path, stay closed.
        for method, path in (("POST", "/api/pull"), ("DELETE", "/api/delete"), ("GET", "/api/tags"), ("GET", "/v1/models"),
                             ("POST", "/v1/embeddings"), ("GET", "/v1/chat/completions"), ("POST", "/"), ("POST", "/v1/chat/completions/../../api/pull")):
            with self.subTest(method=method, path=path):
                self.assertEqual(check(method=method, path=path), 404)

    def test_only_our_model_and_sane_bodies(self):
        other = json.dumps({"model": "qwen3:8b", "messages": []}).encode()
        self.assertEqual(check(body=other), 403)
        self.assertEqual(check(body=b"not json"), 400)
        self.assertEqual(check(body=json.dumps({"model": "lasermcp", "stream": True}).encode()), 400)
        self.assertEqual(check(body=b"x" * (tp.MAX_BODY + 1)), 413)


class KeyFileTests(unittest.TestCase):
    def test_a_new_key_replaces_the_old_one_and_keeps_other_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("SUPABASE_URL=https://x\nLASERMCP_LOCAL_API_KEY=old\n", encoding="utf-8")
            key = tp.write_new_key(env)
            text = env.read_text(encoding="utf-8")
            self.assertTrue(key.startswith("lmk_") and len(key) > 30)
            self.assertIn("SUPABASE_URL=https://x", text)
            self.assertEqual(text.count("LASERMCP_LOCAL_API_KEY="), 1)
            self.assertNotIn("=old", text)
            import os
            from unittest import mock

            with mock.patch.dict(os.environ, {"LASERMCP_LOCAL_API_KEY": ""}):
                self.assertEqual(tp.read_key(env), key)


if __name__ == "__main__":
    unittest.main()
