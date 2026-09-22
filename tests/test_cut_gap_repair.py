import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from cut_gap_repair import repair_cut_gaps
from project_options import apply_holding_nicks, resolve_choices
from topology import inspect_topology


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'+body+'</svg>').encode()


CUT='<path data-operation="CUT" stroke="#FF0000" d="M1 0H10V10H0V0.65H0.4"/>'


class CutGapRepairTests(unittest.TestCase):
    def test_untagged_gaps_need_explicit_request(self):
        source=svg(CUT)
        self.assertEqual(apply_holding_nicks(source,{'holding_nicks':False}),source)
        fixed=apply_holding_nicks(source,{'holding_nicks':False,'repair_cut_gaps':True})
        self.assertTrue(inspect_topology(fixed)['ok'])
        self.assertIn(b'"square_joins": 1',fixed.replace(b'&quot;',b'"'))

    def test_engraving_is_unchanged(self):
        mark='<path id="text" data-operation="ENGRAVE" stroke="#000000" d="M1 1L1.4 1.1"/>'
        result=ET.fromstring(repair_cut_gaps(svg(CUT+mark),explicit=True))
        el=next(e for e in result.iter() if e.get('id')=='text')
        self.assertEqual(el.get('d'),'M1 1L1.4 1.1')

    def test_ambiguous_pairing_is_blocked(self):
        with self.assertRaisesRegex(ValueError,'CUT_REPAIR_AMBIGUOUS'):
            repair_cut_gaps(svg(CUT+CUT.replace('M1 0','M1.1 0')),explicit=True)

    def test_different_part_groups_are_never_joined(self):
        raw=svg('<g id="a"><path data-operation="CUT" stroke="#FF0000" d="M0 0H10"/></g><g id="b"><path data-operation="CUT" stroke="#FF0000" d="M10 0H0"/></g>')
        with self.assertRaisesRegex(ValueError,'UNMATCHED'):
            repair_cut_gaps(raw,explicit=True)

    def test_scaled_or_transformed_geometry_fails_closed(self):
        for raw in (svg(CUT).replace(b'100mm',b'200mm'),svg(CUT.replace('<path','<path transform="scale(2)"'))):
            with self.assertRaisesRegex(ValueError,'CUT_REPAIR_UNITS|CUT_REPAIR_TRANSFORM'):
                repair_cut_gaps(raw,explicit=True)

    def test_saved_svg_and_dxf_use_fixed_geometry(self):
        import boxes_adapter
        from dxf_export import svg_bytes_to_dxf
        with tempfile.TemporaryDirectory() as tmp,patch.object(boxes_adapter,'OUTPUT_DIR',Path(tmp)):
            _,saved,_=boxes_adapter._write_svg(svg(CUT),'repair-test',preserve_source_geometry=True,
                                              project_parameters={'holding_nicks':False,'repair_cut_gaps':True})
        self.assertTrue(inspect_topology(saved)['ok'])
        self.assertIn(b'POLYLINE',svg_bytes_to_dxf(saved))
        self.assertEqual(apply_holding_nicks(saved,{'holding_nicks':False,'repair_cut_gaps':True}),saved)

    def test_invalid_option_combinations(self):
        for params in ({'holding_nicks':True,'repair_cut_gaps':True},{'holding_nicks':False,'repair_cut_gaps':'true'}):
            with self.assertRaises(ValueError):resolve_choices(params)



    def test_import_compiler_repairs_before_review(self):
        from design_engine import import_svg_document
        built=import_svg_document(svg(CUT).decode(),{'holding_nicks':False,'repair_cut_gaps':True})
        self.assertTrue(inspect_topology(built['svg_bytes'])['ok'])
        self.assertIn(b'data-cut-gap-repair',built['svg_bytes'])
        self.assertEqual(built['cut_gap_repair']['square_joins'],1)
