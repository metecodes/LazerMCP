import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from svgpathtools import parse_path

from standard_models import get_standard_model, model_recipe, model_parameters, ROOT
from toolbox import render_toolbox
from review import review_built
from semantic_cad import inspect_design


class StandardModelTests(unittest.TestCase):
    def test_standard_house_has_real_closed_parts_and_verified_mates(self):
        built = render_toolbox(model_recipe(), model_parameters())
        report = review_built(built)
        self.assertEqual(report['final_status'],'PROTOTYPE READY',report['look_again'])
        self.assertEqual(built['assembly']['tab_slot_pairs'],11)
        self.assertEqual(len(inspect_design(built['svg_bytes'])['parts']),7)
        self.assertEqual(built['topology']['nicked_closed'],0)
        for el in ET.fromstring(built['svg_bytes']).iter():
            if el.tag.endswith('path') and el.get('data-operation')=='CUT':
                self.assertTrue(all(abs(p.start-p.end)<1e-7 for p in parse_path(el.get('d')).continuous_subpaths()))
        self.assertTrue(built['assembly']['assembled_preview_svg'])

    def test_permanent_assets_do_not_use_job_expiry_storage(self):
        model = get_standard_model(base_url='https://example.test')
        self.assertTrue(model['success'])
        self.assertIsNone(model['expires_at'])
        self.assertEqual(model['thickness_mm'],2.7)
        self.assertEqual(model['production_export'],'BLOCKED')
        for key in ('svg_url','dxf_url','assembled_preview_url','recipe_url'):
            self.assertTrue(model[key].startswith('https://example.test/demo/'))
            self.assertTrue((ROOT/'web'/'demo'/model[key].rsplit('/',1)[1]).is_file())
        self.assertFalse(get_standard_model('../secret')['success'])

    def test_thickness_derived_placements_remain_valid(self):
        from house_holder import recipe
        from assembly import check_assembly
        for thickness in (2.7,3):
            result = check_assembly(recipe(thickness=thickness),thickness=thickness)
            self.assertTrue(result['ok'],result['look_again'])
