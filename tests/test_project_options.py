import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from project_options import resolve_choices, apply_holding_nicks
from toolbox import render_toolbox
from dxf_export import svg_bytes_to_dxf


class ProjectOptionsTests(unittest.TestCase):
    def test_missing_choices_ask_before_generation(self):
        _, result = resolve_choices()
        self.assertEqual(result['status'], 'NEEDS_INPUT')
        self.assertEqual({q['field'] for q in result['questions']}, {'holding_nicks','surface_texts'})

    def test_false_and_empty_are_explicit_answers_and_project_local(self):
        original = {'holding_nicks':False, 'surface_texts':[]}
        params, pending = resolve_choices(original)
        self.assertIsNone(pending)
        self.assertFalse(params['holding_nicks'])
        params['holding_nicks'] = True
        self.assertFalse(original['holding_nicks'])
        self.assertIsNotNone(resolve_choices()[1])

    def test_invalid_choices_not_coerced(self):
        with self.assertRaises(ValueError):
            resolve_choices({'holding_nicks':'false','surface_texts':[]})

    def test_nicks_text_palette_and_final_save(self):
        import boxes_adapter
        part = {'type':'panel','label':'board','w':120,'h':80,'edges':'eeee'}
        for enabled in (False,True):
            params = {'holding_nicks':enabled,'surface_texts':[{'text':'PAYAS STEM','target_part':'board'}]}
            built = render_toolbox([part], params)
            root = ET.fromstring(built['svg_bytes'])
            self.assertEqual(any(p.get('data-holding-nicks') for p in root.iter()),enabled)
            paths = [p for p in root.iter() if p.tag.endswith('path')]
            marks = [p for p in paths if p.get('data-operation')=='ENGRAVE']
            self.assertTrue(marks)
            self.assertTrue(all(p.get('stroke')=='#000000' for p in marks))
            cuts = [p for p in paths if p.get('data-operation')=='CUT']
            self.assertTrue(cuts)
            self.assertTrue(all(p.get('stroke')=='#FF0000' for p in cuts))
            with tempfile.TemporaryDirectory() as tmp, patch.object(boxes_adapter,'OUTPUT_DIR',Path(tmp)):
                _, saved, _ = boxes_adapter._write_svg(built['svg_bytes'],'test',project_parameters=params)
            self.assertEqual(any(p.get('data-holding-nicks') for p in ET.fromstring(saved).iter()),enabled)
            dxf = svg_bytes_to_dxf(saved).decode()
            self.assertIn('ENGRAVE\n70\n0\n62\n7',dxf)
            self.assertIn('CUT\n70\n0\n62\n1',dxf)
            self.assertIn('POLYLINE\n8\nENGRAVE',dxf)
            self.assertIn('POLYLINE\n8\nCUT',dxf)

    def test_no_extra_text_and_no_nicks(self):
        built = render_toolbox([{'type':'panel','label':'p','w':100,'h':80,'edges':'eeee'}],
                               {'holding_nicks':False,'surface_texts':[]})
        self.assertEqual(built['surface_content']['placements'],[])
        self.assertNotIn(b'data-holding-nicks',built['svg_bytes'])

    def test_source_nicks_cannot_be_silently_closed(self):
        raw = b'<svg xmlns="http://www.w3.org/2000/svg"><path data-operation="CUT" stroke="#FF0000" d="M0 0H100V100H0Z"/></svg>'
        nicked = apply_holding_nicks(raw,{'holding_nicks':True})
        with self.assertRaisesRegex(ValueError,'SOURCE_HAS_HOLDING_NICKS'):
            apply_holding_nicks(nicked,{'holding_nicks':False})
