"""Platform studio: 3D assembly JSON, quotas, thin MCP gates."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from assembly import check_assembly
from assembly_result import build, panels_for_viewer
from tests.test_explicit_mates import connectors


class PlatformStudioTests(unittest.TestCase):
    def test_panels_for_viewer_extrudes_outlines(self):
        assembly = check_assembly(connectors(), parameters={"assembly_order": ["beta", "alpha"]})
        result = build(assembly, file_id="studio.svg", project_id="studio")
        viewer = panels_for_viewer(result)
        self.assertTrue(viewer["success"])
        self.assertGreaterEqual(len(viewer["panels"]), 2)
        panel = viewer["panels"][0]
        self.assertGreaterEqual(len(panel["outline_local_mm"]), 3)
        self.assertIn("matrix", panel["transform"])
        self.assertIn("NOT_VERIFIED", viewer["note"])

    def test_hard_quota_blocks_free_platform_ai(self):
        from plans import gate_job

        with patch.dict(os.environ, {"LASERMCP_BETA": "0", "LASERMCP_HARD_QUOTA": "1"}, clear=False):
            from importlib import reload
            import plans

            reload(plans)
            blocked = plans.gate_job("platform_ai")
            self.assertFalse(blocked.get("ok"))
            self.assertTrue(any("Maker/Pro" in x for x in blocked.get("look_again") or []))

    def test_mcp_create_from_reference_gated_when_enforced(self):
        from importlib import reload
        import plans

        with patch.dict(os.environ, {"LASERMCP_BETA": "0", "LASERMCP_HARD_QUOTA": "1"}, clear=False):
            reload(plans)
            gate = plans.gate_mcp_tool("create_from_reference")
            self.assertFalse(gate.get("ok"))

    def tearDown(self):
        from importlib import reload
        import plans

        # restore default beta-open behavior for other tests
        os.environ.pop("LASERMCP_HARD_QUOTA", None)
        if "LASERMCP_BETA" not in os.environ:
            os.environ["LASERMCP_BETA"] = "1"
        reload(plans)


if __name__ == "__main__":
    unittest.main()
