import unittest
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import tempfile
import json

from dxf_export import svg_bytes_to_dxf
from engraving_validation import validate as engraving
from linear_motion import validate as motion
from standalone_validation import classify_assembly_mode
from topology import inspect_topology
from toolbox import render_toolbox
from review import review_built


def svg(content):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
            'viewBox="0 0 100 100">' + content + '</svg>').encode()


OUTER = '<path d="M0 0H100V100H0Z" stroke="#FF0000" fill="none" data-operation="CUT"/>'
MARK = '<path d="M45 50L55 50" stroke="#FFFF00" fill="none" data-operation="ENGRAVE"/>'


class ValidationGapRegressions(unittest.TestCase):
    def test_raw_text_export_fails_instead_of_silently_dropping_letters(self):
        with self.assertRaisesRegex(ValueError, "DXF_UNRESOLVED_GEOMETRY"):
            svg_bytes_to_dxf(svg(OUTER + '<text x="10" y="20">PAYAS STEM</text>'))

    def test_engraving_inside_removed_material_fails_but_surface_passes(self):
        hole = '<path d="M40 40H60V60H40Z" stroke="#FF0000" data-operation="CUT"/>'
        self.assertTrue(any(r['status'] == 'FAIL' for r in engraving(svg(OUTER+hole+MARK))['geometry']))
        self.assertTrue(all(r['status'] == 'PASS' for r in engraving(svg(OUTER+MARK))['geometry']))

    def test_duplicate_unnamed_engraving_fails(self):
        rows = engraving(svg(OUTER+MARK+MARK))['geometry']
        self.assertTrue(any(r['status'] == 'FAIL' and 'overlaps' in r['note'] for r in rows))

    def test_malformed_path_is_not_accepted_even_with_nick_metadata(self):
        for attr in ('', 'data-holding-nicks="2"'):
            result = inspect_topology(svg(f'<path d="M broken" stroke="#FF0000" data-operation="CUT" {attr}/>'))
            self.assertFalse(result['ok'])
            self.assertEqual(result['open_cuts'][0]['code'], 'INVALID_CUT_PATH')

    def test_engraving_preset_cannot_override_two_physical_parts(self):
        report = classify_assembly_mode({'preset':'engraving_layout', 'parameters':{'assembly_mode':'standalone'}},
                                       [{'kind':'panel'}, {'kind':'panel'}], [], False)
        self.assertFalse(report['valid'])
        self.assertEqual(report['physical_part_count'], 2)

    def panels(self):
        a = dict(type='panel', label='a', w=100, h=100, edges='eeee',
                 placement=dict(origin=[0,0,0], u=[1,0,0], v=[0,1,0]))
        b = deepcopy(a); b['label'] = 'b'
        return a, b

    def test_coplanar_overlapping_panels_cannot_be_prototype_ready(self):
        params = {'connections':[dict(id='C1', type='finger_joint', part_a='a', part_b='b')]}
        report = review_built(render_toolbox(list(self.panels()), params))
        self.assertEqual(report['final_status'], 'BLOCKED')

    def test_ray_and_allowed_contact_names_do_not_hide_penetration(self):
        for clearance in (0, 50):
            params = {'connections':[dict(id='S1', type='linear_slide', moving_part='a', rails=['b'],
                      axis=[1,0,0], travel_mm=10, clearance_mm=clearance, allowed_contact_parts=['b'])]}
            self.assertEqual(motion(list(self.panels()), params)['status'], 'FAIL')

    def test_touching_support_surface_does_not_block_slide(self):
        a,b = self.panels(); b['placement']['origin'][2] = -3
        params = {'connections':[dict(id='S1', type='linear_slide', moving_part='a', rails=['b'],
                  axis=[1,0,0], travel_mm=10)]}
        self.assertEqual(motion([a,b],params)['status'], 'PASS')

    def test_post_save_review_exception_revokes_old_authorization(self):
        import boxes_adapter
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(boxes_adapter, 'OUTPUT_DIR', Path(tmp)), \
             patch('plans.entitled', return_value=True), \
             patch('pipeline.review_only', side_effect=RuntimeError('injected review failure')), \
             patch('studio.attach', side_effect=lambda extra,*a: extra), \
             patch('studio.finish_result', side_effect=lambda result,*a: result), \
             patch('persist.job.attach_durable_artifacts', side_effect=lambda result,*a: result):
            result = boxes_adapter.save_generated_svg(svg(OUTER+MARK), extra={
                'final_status':'PROTOTYPE READY', 'authorized_output':'Prototype SVG'})
            report = json.loads((Path(tmp)/result['report_id']).read_text(encoding='utf-8'))
            self.assertEqual(report['final_status'], 'BLOCKED')
            self.assertEqual(report['authorized_output'], 'None')
            self.assertEqual(report['production_export'], 'BLOCKED')
            self.assertFalse(report['ready_to_cut'])

    def test_nonfinite_laser_settings_rejected(self):
        from laser_settings import resolve_operation_settings
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                resolve_operation_settings({'operation_settings':{'ENGRAVE':{'speed_scale':value}}})
