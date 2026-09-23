import unittest
from xml.etree import ElementTree as ET

from contour_precision import cleanup_cut_contours
from dxf_export import svg_bytes_to_dxf


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'
            + body + '</svg>').encode()


class ContourPrecisionTests(unittest.TestCase):
    def test_removes_sub_tolerance_cut_wobble_and_dxf_uses_same_path(self):
        raw = svg('<path data-operation="CUT" d="M0 0 L40 .025 L80 0 L80 30 L0 30 Z"/>'
                  '<path data-operation="ENGRAVE" d="M0 40 L40 40.025"/>')
        cleaned = cleanup_cut_contours(raw)
        root = ET.fromstring(cleaned)
        cuts = [e for e in root.iter() if e.get('data-operation') == 'CUT']
        engraving = next(e for e in root.iter() if e.get('data-operation') == 'ENGRAVE')
        self.assertNotIn('40.000000 0.025000', cuts[0].get('d'))
        self.assertEqual(engraving.get('d'), 'M0 40 L40 40.025')
        self.assertIn('data-contour-precision', root.attrib)
        dxf = svg_bytes_to_dxf(cleaned).decode()
        self.assertEqual(dxf.count('\nVERTEX\n'), 6)

    def test_preserves_real_slope_and_is_idempotent(self):
        raw = svg('<path data-operation="CUT" d="M0 0 L20 2 L20 30 L0 30 Z"/>')
        first = cleanup_cut_contours(raw)
        self.assertIn('L20 2', first.decode())
        self.assertEqual(first, cleanup_cut_contours(first))

    def test_non_mm_source_is_unchanged(self):
        raw = b'<svg xmlns="http://www.w3.org/2000/svg" width="100px" height="100px" viewBox="0 0 100 100"><path data-operation="CUT" d="M0 0L1 0"/></svg>'
        self.assertEqual(raw, cleanup_cut_contours(raw))
