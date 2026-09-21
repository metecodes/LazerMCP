import unittest
from pipeline import review_only
from toolbox import render_toolbox

def base(**extra):
    row={"type":"box","label":"case","x":94,"y":69,"h":29,"bottom":True}
    row.update(extra);return row

class ElectronicsBoxTests(unittest.TestCase):
    def compile(self,row):return review_only(render_toolbox([row],{"thickness":3,"burn":.15}))

    def assert_parts_preserved(self,built,expected=5):
        parts=built["assembly"]["physical_parts"]
        self.assertEqual(len(parts),expected)
        self.assertEqual(len({p["id"] for p in parts}),expected)
        self.assertTrue(all(p["outer_cut"]["points"] for p in parts))

    def test_box_feature_combinations_preserve_parent_faces(self):
        cases=[
            base(),
            base(walls={"front":{"slots":[{"x":20,"y":15,"w":14,"h":10}]}}),
            base(walls={n:{"ports":[{"id":n,"x":20,"y":15,"w":14,"h":8}]} for n in ("front","back","left","right")}),
            base(bottom={"holes":[{"x":20,"y":20,"d":2.7}]}),
            base(lid={"type":"removable"}),
            base(lid={"type":"finger_joint"}),
            base(bottom={"holes":[{"x":20,"y":20,"d":2.7}]},lid=True,walls={"front":{"ports":[{"id":"p","x":20,"y":15,"w":14,"h":8}]}}),
            base(walls={"front":{"ports":[{"id":"p1","x":20,"y":15,"w":14,"h":8},{"id":"p2","x":55,"y":15,"w":18,"h":12}]}}),
        ]
        for row in cases:
            with self.subTest(row=row):
                built=self.compile(row);self.assert_parts_preserved(built,6 if row.get("lid") else 5)
                notes=" ".join(n for c in built["review"]["categories"].values() for n in c.get("notes") or [])
                self.assertNotIn("box is missing",notes)

    def test_raspberry_pi_5_generic_enclosure_reaches_prototype_ready(self):
        holes=[{"x":20,"y":20,"d":2.7},{"x":74,"y":20,"d":2.7},{"x":20,"y":49,"d":2.7},{"x":74,"y":49,"d":2.7}]
        row=base(bottom={"holes":holes},lid=True,walls={
            "front":{"ports":[{"id":"usb","x":25,"y":15,"connector_width":14,"connector_height":10,"plug_width":16,"plug_height":12,"clearance":1},{"id":"rj45","x":60,"y":15,"w":18,"h":14}]},
            "back":{"ports":[{"id":"usb-c","x":20,"y":12,"w":10,"h":5},{"id":"hdmi-1","x":40,"y":12,"w":12,"h":5},{"id":"hdmi-2","x":58,"y":12,"w":12,"h":5}]},
            "left":{"ports":[{"id":"microsd","x":30,"y":8,"w":18,"h":4}]},
            "right":{"ports":[{"id":"aux","x":30,"y":12,"w":12,"h":8}]},
            "lid":{"ports":[{"id":"gpio-ffc","x":47,"y":34.5,"w":55,"h":8}]},
        })
        from payas_cad import create_design
        built=create_design(primitives=[row],parameters={"thickness":3,"burn":.15,"material":"poplar_3mm","machine":"payas_workshop"},public_base_url="http://127.0.0.1:8000")
        self.assertTrue(built["success"]);self.assertEqual(built["final_status"],"PROTOTYPE READY",built.get("blocking_reasons"))
        self.assert_parts_preserved(built,6)
        counts={p["id"].split("/")[-1]:len(p["inner_cuts"]) for p in built["assembly"]["physical_parts"]}
        self.assertEqual(counts,{"bottom":4,"front":2,"back":3,"left":1,"right":1,"lid":1})
        for category in ("PART_COMPLETENESS","CONNECTIONS","ASSEMBLY","SVG_GEOMETRY","MANUFACTURING","CONNECTION_COVERAGE","MATE_GEOMETRY","TAB_SLOT_GEOMETRY","3D_ASSEMBLY"):
            self.assertEqual(built["review"]["categories"][category]["status"],"PASS",category)
        self.assertEqual(built["physical"]["kerf"],"NOT_VERIFIED")
        self.assertEqual(built["physical"]["assembly"],"NOT_VERIFIED")
        self.assertEqual(built["production_export"],"BLOCKED")
        self.assertEqual(built["assembly"]["transform_validation"]["status"],"PASS")
        self.assertIsNotNone(built["assembly"]["assembled_preview_svg"])

    def test_port_uses_larger_plug_envelope_plus_clearance(self):
        row=base(walls={"front":{"ports":[{"id":"usb-c","x":30,"y":15,"connector_width":10,"connector_height":5,"plug_width":14,"plug_height":9,"clearance":1}]}})
        built=self.compile(row);front=next(p for p in built["assembly"]["physical_parts"] if p["id"].endswith("/front"))
        pts=front["inner_cuts"][0]["points"]
        self.assertEqual(max(p[0] for p in pts)-min(p[0] for p in pts),16)
        self.assertEqual(max(p[1] for p in pts)-min(p[1] for p in pts),11)
        self.assertEqual(front["inner_cuts"][0]["semantic_role"],"port_cutout")

if __name__=="__main__":unittest.main()
