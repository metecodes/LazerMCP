import unittest
from dxf_import import dxf_to_svg
from semantic_cad import inspect_design,compose_design,create_text

DXF='''0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n8\nCUT\n70\n1\n10\n0\n20\n0\n10\n100\n20\n0\n10\n100\n20\n80\n10\n0\n20\n80\n0\nCIRCLE\n8\nCUT\n10\n50\n20\n40\n40\n5\n0\nENDSEC\n0\nEOF\n'''
class DxfCompositionTests(unittest.TestCase):
 def test_import_and_add_real_text(self):
  svg=dxf_to_svg(DXF);doc=inspect_design(svg);self.assertEqual(len(doc['parts']),1)
  out=compose_design(svg,[create_text('İŞ GÜVENLİĞİ',parent_part_id=doc['parts'][0]['id'],placement='top_center')]);self.assertTrue(out['success'],out['issues']);self.assertNotIn('<text',out['svg'])
 def test_unknown_layer_blocks(self):
  svg=dxf_to_svg(DXF.replace('8\nCUT','8\nMYSTERY',1));self.assertGreater(inspect_design(svg)['unknown_count'],0)
