"""AI prompt cost estimate + studio upload routing."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class AiCostAndUploadTests(unittest.TestCase):
    def test_prompt_cost_studio_zero_mcp_positive(self):
        from workshop import estimate_ai_prompt_cost

        quote = estimate_ai_prompt_cost(
            {"prompt": "180x120x70 acik finger joint kutu 3 mm kavak", "model": "gpt-4o-mini"}
        )
        self.assertTrue(quote["success"])
        self.assertEqual(quote["studio_ai"]["usd"]["total"], 0.0)
        self.assertFalse(quote["studio_ai"]["billable_llm"])
        self.assertTrue(quote["mcp_host_ai"]["billable_llm"])
        self.assertGreater(quote["mcp_host_ai"]["usd"]["total"], 0.0)

    def test_studio_ai_requires_prompt_or_file(self):
        from workshop import create_studio_ai

        with patch("plans.entitled", return_value=True), patch(
            "plans.gate_job",
            return_value={"ok": True, "plan": "pro", "plan_name": "Pro", "used": 0, "quota": 400},
        ):
            out = create_studio_ai({})
        self.assertTrue(out.get("ok") is False or out.get("success") is True)
        self.assertTrue(any("prompt" in x.lower() or "upload" in x.lower() for x in (out.get("look_again") or [])))

    def test_studio_ai_svg_route(self):
        from workshop import create_studio_ai

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30">'
            '<path d="M0 0 H40 V30 H0 Z" stroke="#ff0000" fill="none" data-operation="CUT"/>'
            "</svg>"
        )
        fake = {
            "success": True,
            "file_id": "t.svg",
            "assembly_result": {"success": True, "panels": [], "thickness_mm": 3},
            "look_again": [],
        }
        with patch("plans.entitled", return_value=True), patch(
            "plans.gate_job",
            return_value={"ok": True, "plan": "pro", "plan_name": "Pro", "used": 0, "quota": 400},
        ), patch("payas_cad.create_design", return_value=fake), patch(
            "assembly_result.panels_for_viewer",
            return_value={"success": True, "panels": [{"part_id": "a", "outline_local_mm": [[0, 0], [1, 0], [1, 1]], "transform": {"matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}}], "thickness_mm": 3},
        ):
            out = create_studio_ai({"svg": svg, "thickness": 3})
        self.assertTrue(out["success"])
        self.assertEqual(out["source"], "svg")

    def test_studio_stl_uses_passed_bytes_and_returns_inline_stl(self):
        # Serverless: the route reads the SVG from durable storage; the local output dir may not have it.
        import base64
        import os
        import tempfile

        from workshop import create_studio_stl

        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="30mm" viewBox="0 0 40 30">'
            b'<path d="M0 0 H40 V30 H0 Z" stroke="#ff0000" fill="none" class="cut" data-operation="CUT"/></svg>'
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}
        ), patch("boxes_adapter.OUTPUT_DIR", __import__("pathlib").Path(tmp)), patch(
            "plans.gate_job", return_value={"ok": True, "plan": "free"}
        ):
            out = create_studio_stl({"file_id": "not-on-this-instance.svg", "height_mm": 3}, svg_bytes=svg)
        self.assertTrue(out["success"], out.get("look_again"))
        self.assertEqual(out["stl_id"], "not-on-this-instance.stl")
        self.assertTrue(base64.b64decode(out["stl_base64"]))

    def test_password_sign_in_route_is_public(self):
        import server

        self.assertIn("/api/auth/password", server.PUBLIC_PATHS)


if __name__ == "__main__":
    unittest.main()
