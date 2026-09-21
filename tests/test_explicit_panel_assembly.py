import unittest

from explicit_panel_assembly import compile_connections
from reference_fidelity import check_reference_fidelity
from toolbox import render_toolbox
from review import review_built


def fixture(migrate=False):
    ports_front = [
        {"id":"rj45","x":18,"y":20,"connector_width":16,"connector_height":14},
        {"id":"usb3","x":45,"y":20,"connector_width":14,"connector_height":7},
        {"id":"usb2","x":72,"y":20,"connector_width":14,"connector_height":7},
    ]
    ports_right = [
        {"id":"usb-c","x":22,"y":20,"connector_width":11,"connector_height":5},
        {"id":"hdmi-1","x":55,"y":20,"connector_width":12,"connector_height":6},
        {"id":"hdmi-2","x":88,"y":20,"connector_width":12,"connector_height":6},
    ]
    if migrate: ports_front, ports_right = [], ports_front + ports_right
    p = lambda origin,u,v:{"origin":origin,"u":u,"v":v}
    parts = [
        {"type":"panel","label":"bottom","w":96,"h":115,"edges":"eeee","placement":p([0,0,0],[1,0,0],[0,1,0])},
        {"type":"panel","label":"lid","w":96,"h":115,"edges":"eeee","placement":p([0,0,40],[1,0,0],[0,1,0])},
        {"type":"panel","label":"front-short-large-ports","w":96,"h":40,"edges":"eeee","ports":ports_front,"placement":p([0,0,0],[1,0,0],[0,0,1])},
        {"type":"panel","label":"back-short-blank","w":96,"h":40,"edges":"eeee","placement":p([0,115,0],[1,0,0],[0,0,1])},
        {"type":"panel","label":"right-long-small-ports","w":115,"h":40,"edges":"eeee","ports":ports_right,"placement":p([96,0,0],[0,1,0],[0,0,1])},
        {"type":"panel","label":"left-long-blank","w":115,"h":40,"edges":"eeee","placement":p([0,0,0],[0,1,0],[0,0,1])},
    ]
    pairs = [("bottom","front-short-large-ports"),("bottom","back-short-blank"),("bottom","left-long-blank"),("bottom","right-long-small-ports"),
             ("lid","front-short-large-ports"),("lid","back-short-blank"),("lid","left-long-blank"),("lid","right-long-small-ports"),
             ("front-short-large-ports","left-long-blank"),("front-short-large-ports","right-long-small-ports"),
             ("back-short-blank","left-long-blank"),("back-short-blank","right-long-small-ports")]
    params={"connections":[{"id":f"C{i:02d}","type":"finger_joint","part_a":a,"part_b":b} for i,(a,b) in enumerate(pairs,1)]}
    return parts,params


class ExplicitPanelAssemblyTests(unittest.TestCase):
    def test_compiles_world_contact_edges_and_keeps_ports(self):
        parts,params=fixture();compiled,report=compile_connections(parts,params,3,.15)
        self.assertEqual(report["status"],"PASS",report["errors"]);self.assertEqual(len(report["joints"]),12)
        self.assertEqual(report["port_inventory"]["front-short-large-ports"],["rj45","usb3","usb2"])
        self.assertEqual(report["port_inventory"]["right-long-small-ports"],["usb-c","hdmi-1","hdmi-2"])
        self.assertTrue(all(j["port_keepout_clear"] for j in report["joints"]))
        self.assertTrue(all(j["length_mm"] in {40,96,115} for j in report["joints"]))
        self.assertTrue(all("f" in next(p["edges"] for p in compiled if p["label"]==j["part_a"]) for j in report["joints"]))

    def test_rendered_fixture_has_real_mates_and_assembly(self):
        parts,params=fixture();built=render_toolbox(parts,params);review=review_built(built)
        self.assertTrue(built["assembly"]["ok"],built["assembly"]["look_again"])
        self.assertEqual(len(built["assembly"]["explicit_panel_assembly"]["joints"]),12)
        self.assertTrue(all(p["mates"] for p in review["design_map"]["parts"]))
        self.assertEqual(review["categories"]["CONNECTIONS"]["status"],"PASS")
        self.assertEqual(review["categories"]["ASSEMBLY"]["status"],"PASS")
        self.assertEqual(review["categories"]["3D_ASSEMBLY"]["status"],"PASS")

    def test_reference_port_migration_is_fail_closed(self):
        parts,params=fixture(migrate=True)
        refs=[]
        expected={"front-short-large-ports":["rj45","usb3","usb2"],"back-short-blank":[],"right-long-small-ports":["usb-c","hdmi-1","hdmi-2"],"left-long-blank":[]}
        for name,ports in expected.items():
            part=next(p for p in parts if p["label"]==name)
            refs.append({"reference_part":name,"generated_part":name,"width_mm":part["w"],"height_mm":part["h"],"ports":ports})
        result=check_reference_fidelity({"reference_job":True,"reference_parts":refs},parts)
        self.assertTrue(any(c["status"]=="FAIL" and "migration" in c["note"] for c in result["part_mapping"]))
        self.assertTrue(any(c["status"]=="FAIL" for c in result["fidelity"]))
        params.update({"reference_job":True,"reference_parts":refs})
        final=review_built(render_toolbox(parts,params))
        self.assertEqual(final["final_status"],"BLOCKED")
        self.assertEqual(final["categories"]["REFERENCE_FIDELITY"]["status"],"FAIL")
        self.assertEqual(final["categories"]["PART_MAPPING"]["status"],"FAIL")


if __name__=="__main__": unittest.main()
