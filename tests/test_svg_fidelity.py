import unittest
from xml.etree import ElementTree as ET

from design_engine import import_svg_document
from dxf_export import svg_bytes_to_dxf
from boxes_adapter import _write_svg


class SvgFidelityTests(unittest.TestCase):
    def build(self, d, group=""):
        return import_svg_document(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100"><g {group}><path d="{d}"/></g></svg>',
            {"svg_default_operation": "CUT", "thickness": 2.7},
        )

    def test_thin_slot_corners_survive_export(self):
        built = self.build("M0 0 L2.7 0 L2.7 90 L0 90 Z")
        dxf = svg_bytes_to_dxf(built["svg_bytes"]).decode()
        self.assertEqual(dxf.count("\nVERTEX\n"), 4)
        self.assertIn("2.7000", dxf)

    def test_disconnected_paths_are_not_joined(self):
        built = self.build("M0 0 L.1 0 M1.3 0 L10 0")
        dxf = svg_bytes_to_dxf(built["svg_bytes"]).decode()
        self.assertEqual(dxf.count("\nPOLYLINE\n"), 2)
        self.assertEqual(dxf.count("\nVERTEX\n"), 4)

    def test_parent_transform_survives_grouping(self):
        built = self.build("M0 0 L2.7 0", 'transform="translate(10 20)"')
        dxf = svg_bytes_to_dxf(built["svg_bytes"]).decode()
        self.assertIn("10.0000", dxf)
        self.assertIn("12.7000", dxf)
        self.assertIn("80.0000", dxf)

    def test_no_extra_holding_gaps_on_import(self):
        built = self.build("M0 0 L2.7 0 L2.7 90 L0 90 Z")
        _, saved, _ = _write_svg(built["svg_bytes"], "fidelity-test", preserve_source_geometry=True)
        path = next(el for el in ET.fromstring(saved).iter() if el.tag.endswith("}path"))
        self.assertEqual(path.get("d"), "M0 0 L2.7 0 L2.7 90 L0 90 Z")

    def test_operation_is_not_guessed(self):
        raw = '<svg width="10mm" height="10mm"><path stroke="red" d="M0 0 L1 0"/></svg>'
        built = import_svg_document(raw)
        self.assertNotIn("\nPOLYLINE\n", svg_bytes_to_dxf(built["svg_bytes"]).decode())

    def test_negative_viewbox_origin_is_preserved_in_mm(self):
        built = import_svg_document('<svg width="20mm" height="20mm" viewBox="-5 -5 20 20"><path d="M0 0 L2.7 0"/></svg>', {"svg_default_operation": "CUT"})
        dxf = svg_bytes_to_dxf(built["svg_bytes"]).decode()
        self.assertIn("5.0000", dxf)
        self.assertIn("7.7000", dxf)
        self.assertIn("15.0000", dxf)
