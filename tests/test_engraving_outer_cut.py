import unittest

from design_engine import compile_design, import_svg_document
from review import review_built
from topology import inspect_topology


class EngravingOuterCutTests(unittest.TestCase):
    def test_alphabet_layout_emits_one_physical_closed_cut_path(self):
        words = ["APPLE","BALL","CAT","DOG","ELEPHANT","FISH","GRAPES","HOUSE","ICE CREAM","JUICE","KITE","LION","MOON","NEST","ORANGE","PENCIL","QUEEN","RABBIT","SUN","TREE","UMBRELLA","VAN","WHALE","XYLOPHONE","YO-YO","ZEBRA"]
        items=[{"kind":"text","value":"ENGLISH ALPHABET","x":100,"y":225,"height":8}]
        for i,(letter,word) in enumerate(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",words)):
            col,row=i%2,i//2
            items.append({"kind":"text","value":f"{letter}  {word}","x":50+col*100,"y":208-row*15,"height":4})
        built=compile_design(preset="engraving_layout",parameters={"width_mm":200,"height_mm":240,"assembly_mode":"standalone","items":items})
        topology=inspect_topology(built["svg_bytes"])
        self.assertEqual(topology["cut_paths"],1);self.assertEqual(topology["closed"],1)
        self.assertEqual(topology["open_cuts"],[]);self.assertEqual(topology["duplicates"],[]);self.assertEqual(topology["self_intersections"],[])
        report=review_built({**built,"topology":topology,"nesting":{"ok":True,"part_count":1,"placements":[{}]}})
        self.assertEqual(report["final_status"],"PROTOTYPE READY",report["look_again"])
        for category in ("SVG_GEOMETRY","MANUFACTURING","ENGRAVE_GEOMETRY","OPERATION_SEPARATION"):
            self.assertEqual(report["categories"][category]["status"],"PASS")
        self.assertEqual(report["production_export"],"BLOCKED")

    def test_semantic_cut_without_path_returns_specific_mismatch(self):
        built=import_svg_document('<svg width="20mm" height="20mm" viewBox="0 0 20 20"><rect x="0" y="0" width="20" height="20" fill="none" stroke="#FF0000" data-operation="CUT" data-operation-origin="EXPLICIT" data-semantic-role="outer_contour"/></svg>',{"assembly_mode":"standalone"})
        built.update({"preset":"engraving_layout","physical_part_count":1,"topology":inspect_topology(built["svg_bytes"]),"nesting":{"ok":True,"part_count":1,"placements":[{}]}})
        report=review_built(built)
        self.assertEqual(report["final_status"],"BLOCKED")
        self.assertEqual(report["compiler_error"]["error_code"],"CUT_GEOMETRY_COMPILER_MISMATCH")
        self.assertEqual(report["compiler_error"]["semantic_cut_count"],1)
        self.assertEqual(report["compiler_error"]["physical_cut_path_count"],0)
        self.assertEqual(report["compiler_error"]["compiler_stage"],"svg_writer")


if __name__=="__main__": unittest.main()
