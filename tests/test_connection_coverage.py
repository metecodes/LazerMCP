import unittest

from assembly import check_assembly
from connection_validation import validate
from pipeline import review_only
from toolbox import render_toolbox


def panel(label, role="structural", moving=False):
    return {"type":"panel","label":label,"role":role,"moving":moving,"w":40,"h":30,"edges":"eeee",
            "placement":{"origin":[0,0,0],"u":[1,0,0],"v":[0,1,0]}}


class ConnectionCoverageTests(unittest.TestCase):
    def test_placement_alone_is_not_connection_evidence(self):
        parts=[panel("a"),panel("b")];assembly=check_assembly(parts)
        report=validate(parts,{},assembly,{"slides":[]})
        self.assertEqual(report["coverage_percent"],0)
        self.assertTrue(all(c["status"]=="FAIL" for c in report["checks"]))
        self.assertIn("mates=[]",report["checks"][0]["note"])

    def test_compiled_box_has_full_structural_connection_coverage(self):
        parts=[{"type":"box","label":"body","x":100,"y":80,"h":120,"bottom":True}]
        assembly=check_assembly(parts);report=validate(parts,{},assembly,{"slides":[]})
        self.assertEqual(report["coverage_percent"],100)
        self.assertTrue(all(c["status"]=="PASS" for c in report["checks"]))

    def test_removable_part_requires_verified_removal_path(self):
        parts=[panel("frame","removable"),panel("rail")];assembly=check_assembly(parts)
        failed=validate(parts,{},assembly,{"slides":[]})
        self.assertTrue(any("remove/reinstall" in c["note"] for c in failed["checks"]))
        params={"connections":[{"id":"remove-frame","type":"removable_slide","moving_part":"frame","rails":["rail"]}]}
        passed=validate(parts,params,assembly,{"slides":[{"id":"remove-frame","status":"PASS","removal_verified":True,"reinstall_verified":True}]})
        self.assertEqual(passed["coverage_percent"],100)

    def test_claimed_metadata_pass_does_not_prove_tab_slot_geometry(self):
        parts=[panel("a"),panel("b")];assembly=check_assembly(parts)
        params={"connections":[{"id":"fake","type":"tab_slot","part_a":"a","part_b":"b","status":"PASS"}]}
        report=validate(parts,params,assembly,{"slides":[]})
        self.assertEqual(report["connection_graph"][0]["status"],"NOT_VERIFIED")
        self.assertEqual(report["mate_geometry_checks"][0]["status"],"NOT_VERIFIED")

    def test_physical_part_ids_are_unique(self):
        parts=[panel("same"),panel("same")];assembly=check_assembly(parts)
        report=validate(parts,{},assembly,{"slides":[]})
        self.assertTrue(any("unique" in c["note"] for c in report["checks"]))

    def test_removable_requires_both_remove_and_reinstall_evidence(self):
        parts=[panel("frame","removable"),panel("rail")];assembly=check_assembly(parts)
        params={"connections":[{"id":"remove-frame","type":"removable_slide","moving_part":"frame","rails":["rail"]}]}
        report=validate(parts,params,assembly,{"slides":[{"id":"remove-frame","status":"PASS","removal_verified":True}]})
        self.assertEqual(report["connection_graph"][0]["status"],"NOT_VERIFIED")

    def test_final_gate_blocks_isolated_structural_mdf(self):
        built=review_only(render_toolbox([panel("a"),panel("b")],{}))
        self.assertEqual(built["review"]["categories"]["CONNECTION_COVERAGE"]["status"],"FAIL")
        self.assertEqual(built["final_status"],"BLOCKED")

    def test_final_gate_reports_complete_compiled_box_graph(self):
        built=review_only(render_toolbox([{"type":"box","label":"body","x":100,"y":80,"h":120,"bottom":True}],{}))
        category=built["review"]["categories"]["CONNECTION_COVERAGE"]
        self.assertEqual(category["status"],"PASS",category)
        self.assertEqual(built["connection_validation"]["coverage_percent"],100)


if __name__=="__main__":unittest.main()
