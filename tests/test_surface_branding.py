import unittest

from surface_branding import apply_surface_content
from toolbox import render_toolbox


class SurfaceBrandingTests(unittest.TestCase):
    def panels(self):
        return [
            {'type':'panel','label':'front','w':100,'h':70,'edges':'eeee'},
            {'type':'panel','label':'back','w':90,'h':60,'edges':'eeee'},
        ]

    def test_no_content_is_added_without_user_request(self):
        parts,report=apply_surface_content(self.panels(),{})
        self.assertFalse(report['placements'])
        self.assertTrue(all(not p.get('markings') for p in parts))

    def test_user_text_is_added_once_and_remains_engrave(self):
        parts,report=apply_surface_content(self.panels(),{'surface_texts':['MİNİK MUCİTLER']})
        marks=[m for p in parts for m in p.get('markings') or []]
        self.assertEqual(len(marks),1);self.assertEqual(marks[0]['value'],'MİNİK MUCİTLER')
        self.assertEqual(marks[0]['operation'],'ENGRAVE');self.assertEqual(report['placements'][0]['color'],'#000000')

    def test_opt_in_brand_name_and_logo_reach_each_suitable_panel(self):
        params={'apply_branding':True,'branding':{'name':'PAYAS STEM','logo_path':'M0 0 L10 0 L5 8 Z'}}
        parts,report=apply_surface_content(self.panels(),params)
        self.assertEqual(len(report['placements']),4)
        for part in parts:
            marks=part.get('markings') or []
            self.assertEqual({m['semantic_role'] for m in marks},{'text','logo'})
            self.assertTrue(all(m['operation']=='ENGRAVE' for m in marks))
            self.assertNotEqual(marks[0]['_branding_box'],marks[1]['_branding_box'])

    def test_compiled_svg_keeps_branding_yellow_and_reports_dimensions(self):
        built=render_toolbox([{'type':'panel','label':'face','w':100,'h':70,'edges':'eeee'}],{'surface_texts':['MİNİK MUCİTLER'],'apply_branding':True,'brand_name':'PAYAS STEM'})
        svg=built['svg_bytes'].decode('utf-8')
        self.assertIn('#000000',svg);self.assertIn('data-operation="ENGRAVE"',svg)
        self.assertNotIn('data-semantic-role="text" data-operation="CUT"',svg)
        self.assertEqual(len(built['surface_content']['placements']),2)
        self.assertTrue(all(p['width_mm']>0 and p['height_mm']>0 for p in built['surface_content']['placements']))

    def test_box_faces_are_supported(self):
        box={'type':'box','label':'kutu','x':80,'y':50,'h':90,'lid':True}
        parts,report=apply_surface_content([box],{'apply_branding':True,'brand_name':'PAYAS STEM'})
        self.assertEqual(len(report['placements']),5)
        self.assertTrue(all((parts[0]['walls'][f].get('markings')) for f in ('front','back','left','right','top')))


if __name__ == '__main__': unittest.main()
