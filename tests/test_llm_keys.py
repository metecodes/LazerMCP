"""Workshop LLM keys — separate from LaserMCP lzr_ platform keys."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class LlmKeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(
            os.environ,
            {
                "MCP_DATA_DIR": self.tmp,
                "MCP_SESSION_SECRET": "test-session-secret-for-llm-keys",
                "OPENAI_API_KEY": "",
                "ANTHROPIC_API_KEY": "",
                "LASERMCP_OPENAI_API_KEY": "",
                "LASERMCP_ANTHROPIC_API_KEY": "",
            },
            clear=False,
        )
        self.env.start()
        # Clear empty env keys so _env_key ignores them
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LASERMCP_OPENAI_API_KEY", "LASERMCP_ANTHROPIC_API_KEY"):
            os.environ.pop(name, None)

    def tearDown(self):
        self.env.stop()

    def test_save_get_delete_roundtrip(self):
        from llm_keys import delete_key, get_raw_key, list_status, save_key

        out = save_key("openai", "sk-test-openai-key-123456", by="ops@example.com")
        self.assertTrue(out["success"])
        self.assertTrue(out["prefix"].startswith("sk-test"))
        self.assertEqual(get_raw_key("openai"), "sk-test-openai-key-123456")
        status = {r["provider"]: r for r in list_status()}
        self.assertTrue(status["openai"]["configured"])
        self.assertFalse(status["anthropic"]["configured"])
        # ciphertext on disk, never raw
        blob = Path(self.tmp, "llm_keys.json").read_text(encoding="utf-8")
        self.assertNotIn("sk-test-openai-key-123456", blob)
        self.assertIn("ciphertext", blob)
        delete_key("openai")
        self.assertIsNone(get_raw_key("openai"))

    def test_env_fallback(self):
        from llm_keys import get_raw_key, list_status

        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-env-fallback-9999"
        self.assertEqual(get_raw_key("anthropic"), "sk-ant-env-fallback-9999")
        row = next(r for r in list_status() if r["provider"] == "anthropic")
        self.assertEqual(row["source"], "env")
        self.assertTrue(row["configured"])

    def test_extract_json_from_llm_client(self):
        from llm_client import _extract_json

        data = _extract_json('{"primitives":[{"type":"box","x":10,"y":10,"h":10}],"parameters":{}}')
        self.assertEqual(data["primitives"][0]["type"], "box")
        wrapped = _extract_json('```json\n{"primitives":[{"type":"panel","w":1,"h":1}],"parameters":{}}\n```')
        self.assertEqual(wrapped["primitives"][0]["type"], "panel")

    def test_cost_quote_mentions_workshop_keys(self):
        from llm_keys import save_key
        from workshop import estimate_ai_prompt_cost

        save_key("openai", "sk-test-openai-key-abcdef")
        quote = estimate_ai_prompt_cost({"prompt": "180x120x70 kutu", "model": "gpt-4o-mini"})
        self.assertTrue(quote["studio_ai"]["uses_workshop_key"])
        self.assertTrue(any(r["configured"] for r in quote["workshop_llm_keys"]))


if __name__ == "__main__":
    unittest.main()
