import unittest
from unittest.mock import patch

from assembly import check_assembly
from assembly_result import build, render
from tests.test_explicit_mates import connectors


class AssemblyResultTests(unittest.TestCase):
    def test_result_keeps_automatic_transforms_and_renders_without_solver(self):
        parts = connectors()
        assembly = check_assembly(parts, thickness=3, parameters={"assembly_order": ["beta", "alpha"]})
        result = build(assembly, file_id="house.svg", project_id="house")
        self.assertTrue(result["validated"])
        self.assertEqual(result["debug"]["part_count"], len(parts))
        self.assertEqual(result["debug"]["transform_count"], len(parts))
        self.assertTrue(all(part["transform"]["matrix"] for part in result["parts"]))
        with patch("assembly.check_assembly", side_effect=AssertionError("render must not re-solve assembly")):
            preview = render(result, "assembled")
        self.assertTrue(preview["success"])
        self.assertIn("Automatic Assembly preview", preview["svg"])

    def test_missing_or_unvalidated_result_has_specific_code(self):
        self.assertEqual(render(None)["code"], "ASSEMBLY_RESULT_NOT_FOUND")
        result = build({}, file_id="none.svg")
        self.assertEqual(render(result)["code"], "ASSEMBLY_RESULT_NOT_VALIDATED")

    def test_server_uses_persisted_result_and_keeps_legacy_cut_alias(self):
        import server
        result = build(check_assembly(connectors(), parameters={"assembly_order": ["beta", "alpha"]}), file_id="house.svg")
        with patch("workshop.editor_context", return_value={"assembly_result": result}):
            assembled = server.render_preview("house.svg", "assembled")
        self.assertTrue(assembled["success"])
        with patch("payas_cad._mcp", return_value={"success": True, "preview_kind": "nested"}):
            nested = server.render_preview("house.svg", "cut")
        self.assertEqual(nested["preview_kind"], "nested")

    def test_editor_context_reuses_persisted_result(self):
        from projects import save_version
        from workshop import editor_context
        parts = connectors()
        result = build(check_assembly(parts, parameters={"assembly_order": ["beta", "alpha"]}), file_id="assembly-result.svg", project_id="assembly-result")
        save_version({"project": "assembly result", "project_id": "assembly-result"},
                     {"file_id": "assembly-result.svg", "primitives": parts, "assembly_result": result})
        with patch("assembly.check_assembly", side_effect=AssertionError("persisted result should be reused")):
            context = editor_context("assembly-result.svg")
        self.assertEqual(context["assembly_result"]["file_id"], "assembly-result.svg")


if __name__ == "__main__":
    unittest.main()
