import unittest
from xml.etree import ElementTree as ET
from design_engine import compile_design
from dxf_export import svg_bytes_to_dxf
from manufacturing import finish_manufacturing_svg
from markings import marking_geom

class EngravingLayoutTests(unittest.TestCase):
    def test_text_logo_yellow_through_final_processing(self):
        built = compile_design(preset='engraving_layout',parameters={'width_mm':150,'height_mm':200,'items':[
            {'kind':'text','value':'PAYAS STEM · ÖNCE GÜVENLİK','x':75,'y':150,'width':100},
            {'kind':'path','d':'M0 0 L10 20 L20 0','x':75,'y':100,'width':30},
            {'kind':'line','points':[[10,10],[20,10]],'operation':'CUT'}]})
        final,_=finish_manufacturing_svg(built['svg_bytes'])
        paths=[el for el in ET.fromstring(final).iter() if el.tag.endswith('path')]
        self.assertTrue(paths)
        for path in paths:
            self.assertEqual(path.get('stroke'),'#FF0000' if path.get('data-operation')=='CUT' else '#FFFF00')
        dxf=svg_bytes_to_dxf(final).decode()
        self.assertIn('ENGRAVE\n70\n0\n62\n2',dxf)
        self.assertIn('CUT\n70\n0\n62\n1',dxf)
        self.assertNotIn('<text',final.decode())

    def test_missing_logo_never_silently_becomes_plus(self):
        with self.assertRaises(ValueError):marking_geom({'kind':'icon','name':'traffic-police'})
        with self.assertRaises(ValueError):compile_design(preset='engraving_layout',parameters={'items':[{'kind':'path'}]})

    def test_rejects_outside_layout(self):
        with self.assertRaises(ValueError):compile_design(preset='engraving_layout',parameters={'items':[{'kind':'text','value':'STEM','x':-30,'y':10}]})

    def test_open_logo_strokes_stay_open(self):
        geom=marking_geom({'kind':'path','d':'M0 0 L10 20 L20 0'})
        self.assertEqual(len(geom.coords),3)
