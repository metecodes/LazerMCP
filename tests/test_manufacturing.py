"""Manufacturing operations are explicit. Color is presentation only."""

from __future__ import annotations

import os
import tempfile
import unittest
from xml.etree import ElementTree as ET

from manufacturing import (
    OPERATIONS,
    annotate_primitive,
    annotate_primitives,
    apply_manufacturing_svg,
    finish_manufacturing_svg,
    validate_primitives,
    validate_svg_operations,
)


def _ops(svg: bytes) -> dict[str, list[str]]:
    root = ET.fromstring(svg)
    found: dict[str, list[str]] = {op: [] for op in OPERATIONS}
    for el in root.iter():
        tag = el.tag.split("}")[-1].lower()
        if tag not in {"path", "line", "polyline", "polygon", "circle", "rect", "ellipse"}:
            continue
        op = (el.get("data-operation") or "").upper()
        if op in found:
            found[op].append(el.get("data-semantic-role") or "")
    return found


def _group_ids(svg: bytes) -> list[str]:
    root = ET.fromstring(svg)
    ids = []
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "g":
            continue
        ident = (el.get("id") or "").upper()
        if ident in OPERATIONS and ident not in ids:
            ids.append(ident)
    return ids


class PrimitiveIntentTests(unittest.TestCase):
    def test_semantic_defaults(self):
        cases = [
            ({"type": "box", "x": 40, "y": 30, "h": 20}, "outer_contour", "CUT"),
            ({"type": "panel", "w": 20, "h": 20, "holes": [{"x": 10, "y": 10, "d": 4}]}, "outer_contour", "CUT"),
            ({"type": "text", "value": "PAYAS"}, "text", "ENGRAVE"),
            ({"type": "panel", "w": 20, "h": 20, "label": "logo-plate", "semantic_role": "logo"}, "logo", "ENGRAVE"),
            ({"semantic_role": "texture", "type": "marking", "kind": "line"}, "texture", "ENGRAVE"),
            ({"semantic_role": "decorative_detail", "type": "panel", "w": 10, "h": 10}, "decorative_detail", "ENGRAVE"),
            ({"semantic_role": "construction_guide", "type": "panel", "w": 10, "h": 10}, "construction_guide", "GUIDE"),
        ]
        for part, role, op in cases:
            annotated = annotate_primitive(dict(part))
            self.assertEqual(annotated["semantic_role"], role, part)
            self.assertEqual(annotated["operation"], op, part)
            self.assertTrue(annotated["operation_source"])

    def test_holes_slots_and_markings_are_annotated(self):
        part = annotate_primitive(
            {
                "type": "box",
                "x": 70,
                "y": 50,
                "h": 80,
                "walls": {
                    "front": {
                        "holes": [{"x": 20, "y": 20, "d": 4}],
                        "slots": [{"x": 35, "y": 30, "w": 12, "h": 20}],
                        "markings": [{"kind": "text", "value": "PAYAS", "x": 35, "y": 10, "height": 4}],
                    }
                },
            }
        )
        hole = part["walls"]["front"]["holes"][0]
        slot = part["walls"]["front"]["slots"][0]
        mark = part["walls"]["front"]["markings"][0]
        self.assertEqual(hole["semantic_role"], "hole")
        self.assertEqual(hole["operation"], "CUT")
        self.assertEqual(slot["semantic_role"], "slot")
        self.assertEqual(slot["operation"], "CUT")
        self.assertEqual(mark["semantic_role"], "text")
        self.assertEqual(mark["operation"], "ENGRAVE")
        self.assertEqual(mark["operation_source"], "default")

    def test_explicit_text_cut_is_auditable_warning(self):
        part = annotate_primitive(
            {"type": "text", "value": "CUTOUT", "operation": "CUT", "semantic_role": "text"}
        )
        self.assertEqual(part["operation"], "CUT")
        self.assertEqual(part["operation_source"], "explicit")
        report = validate_primitives([part])
        self.assertTrue(report["ok"])
        self.assertTrue(any("explicit and auditable" in w for w in report["warnings"]))

    def test_implicit_text_cut_fails(self):
        report = validate_primitives(
            [{"type": "text", "value": "X", "semantic_role": "text", "operation": "CUT", "operation_source": "default"}]
        )
        self.assertTrue(report["critical_fail"])
        self.assertTrue(any("text marked CUT" in n for n in report["fail"]))

    def test_missing_and_unknown_operation_fail(self):
        missing = validate_primitives([{"type": "panel", "semantic_role": "outer_contour"}])
        unknown = validate_primitives(
            [{"type": "panel", "semantic_role": "outer_contour", "operation": "BURN"}]
        )
        self.assertTrue(missing["critical_fail"])
        self.assertTrue(unknown["critical_fail"])

    def test_guide_cut_and_outer_not_cut_fail(self):
        guide = validate_primitives(
            [{"semantic_role": "construction_guide", "operation": "CUT", "operation_source": "explicit"}]
        )
        outer = validate_primitives(
            [{"semantic_role": "outer_contour", "operation": "ENGRAVE", "operation_source": "explicit"}]
        )
        hole = validate_primitives([{"semantic_role": "hole", "operation": "ENGRAVE", "operation_source": "explicit"}])
        self.assertTrue(guide["critical_fail"])
        self.assertTrue(outer["critical_fail"])
        self.assertTrue(hole["critical_fail"])

    def test_decorative_cut_is_warning(self):
        report = validate_primitives(
            [{"semantic_role": "texture", "operation": "CUT", "operation_source": "explicit"}]
        )
        self.assertTrue(report["ok"])
        self.assertTrue(report["warnings"])


class SvgExporterTests(unittest.TestCase):
    def test_groups_and_keywords_not_color_alone(self):
        raw = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="40mm">'
            '<path d="M 0 0 L 40 0 L 40 40 L 0 40 Z" stroke="#FF0000" id="outer"/>'
            '<path d="M 4 4 L 12 4 L 12 8 L 4 8 Z" stroke="#FF0000" id="roof-tile-texture"/>'
            '<path d="M 6 20 L 18 20" stroke="#FF0000" class="facade-decor"/>'
            '<path d="M 8 24 L 16 24" stroke="#FF0000" class="letter-text"/>'
            '<path d="M 2 30 L 10 30" stroke="#FF0000" data-role="construction_guide"/>'
            "</svg>"
        ).encode("utf-8")
        stamped, report = finish_manufacturing_svg(raw)
        self.assertEqual(set(_group_ids(stamped)), set(OPERATIONS))
        ops = _ops(stamped)
        self.assertTrue(ops["CUT"])
        self.assertTrue(any(r == "texture" for r in ops["ENGRAVE"]))
        self.assertTrue(any(r == "decorative_detail" for r in ops["ENGRAVE"]))
        self.assertTrue(any(r == "text" for r in ops["ENGRAVE"]))
        self.assertTrue(ops["GUIDE"])
        self.assertTrue(report["ok"])
        self.assertFalse(report["critical_fail"])

    def test_missing_operation_on_export_fails(self):
        raw = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path d="M 0 0 L 10 0 L 10 10 Z" stroke="#FF0000"/>'
            "</svg>"
        ).encode("utf-8")
        stamped = apply_manufacturing_svg(raw)
        root = ET.fromstring(stamped)
        for el in root.iter():
            if el.tag.split("}")[-1].lower() == "path":
                el.attrib.pop("data-operation", None)
        broken = ET.tostring(root, encoding="utf-8")
        report = validate_svg_operations(broken)
        self.assertTrue(report["critical_fail"])
        self.assertTrue(any("missing operation" in n for n in report["fail"]))

    def test_holding_nicks_stay_cut_and_closed(self):
        from holding_nicks import nick_cut_svg
        from topology import inspect_topology

        raw = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path d="M 0 0 L 80 0 L 80 40 L 0 40 Z" stroke="#FF0000"/>'
            "</svg>"
        ).encode("utf-8")
        stamped, _report = finish_manufacturing_svg(raw)
        nicked = nick_cut_svg(stamped)
        topo = inspect_topology(nicked)
        self.assertTrue(topo.get("ok"))
        self.assertFalse(topo.get("open_cuts"))
        root = ET.fromstring(nicked)
        nicked_paths = [el for el in root.iter() if el.get("data-holding-nicks")]
        self.assertTrue(nicked_paths)
        for el in nicked_paths:
            self.assertEqual(el.get("data-operation"), "CUT")
        report = validate_svg_operations(nicked)
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(int(report.get("nicked") or 0), 1)

    def test_gate_blocks_critical_manufacturing_fail(self):
        from review import review_built

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<g id="CUT" data-operation="CUT"/>'
            '<g id="ENGRAVE" data-operation="ENGRAVE"/>'
            '<g id="SCORE" data-operation="SCORE"/>'
            '<g id="GUIDE" data-operation="GUIDE"/>'
            '<g id="LABEL" data-operation="LABEL"/>'
            '<path d="M 0 0 L 10 0" data-operation="CUT" data-semantic-role="construction_guide"'
            ' data-operation-source="default" stroke="#FF0000"/>'
            "</svg>"
        ).encode("utf-8")
        report = review_built(
            {
                "svg_bytes": svg,
                "product": "jigsaw_puzzle",
                "topology": {"ok": True, "cut_paths": 1, "open_cuts": [], "duplicates": [], "self_intersections": []},
                "nesting": {"ok": True, "errors": [], "part_count": 1},
                "manufacturing": validate_svg_operations(svg),
            }
        )
        self.assertEqual(report["final_status"], "BLOCKED")
        self.assertEqual(report["categories"]["MANUFACTURING"]["status"], "FAIL")


class ProductRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = self.tmp

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MCP_DATA_DIR", None)
        else:
            os.environ["MCP_DATA_DIR"] = self.old

    def _assert_sheet(self, svg: bytes, primitives=None, *, expect_engrave: bool = False):
        report = validate_svg_operations(svg, primitives)
        self.assertTrue(report["ok"], report.get("fail"))
        self.assertGreaterEqual(int(report.get("cut_paths") or 0), 1)
        self.assertEqual(set(report.get("groups") or []), set(OPERATIONS))
        ops = _ops(svg)
        self.assertTrue(ops["CUT"])
        if expect_engrave:
            self.assertTrue(ops["ENGRAVE"])
            self.assertFalse(any(r == "text" for r in ops["CUT"]))
        if primitives:
            for part in annotate_primitives(list(primitives)):
                self.assertIn(part.get("operation"), OPERATIONS)
                self.assertTrue(part.get("semantic_role"))

    def test_windmill(self):
        from toolbox import GRAMMAR, render_toolbox

        parts = GRAMMAR["mill"]["primitives"]
        built = render_toolbox(parts, {"thickness": 3.0, "burn": 0.15})
        self._assert_sheet(built["svg_bytes"], built.get("primitives"), expect_engrave=True)
        self.assertTrue((built.get("manufacturing") or {}).get("ok"))
        topo = built.get("topology") or {}
        self.assertFalse(topo.get("open_cuts"))

    def test_safranbolu_style_house(self):
        from toolbox import render_toolbox

        parts = [
            {
                "type": "box",
                "x": 90,
                "y": 70,
                "h": 110,
                "bottom": True,
                "walls": {
                    "front": {
                        "slots": [
                            {"x": 28, "y": 32, "w": 18, "h": 28},
                            {"x": 62, "y": 40, "w": 16, "h": 22},
                        ],
                        "markings": [
                            {
                                "kind": "line",
                                "points": [[10, 78], [80, 78], [80, 98], [10, 98], [10, 78]],
                                "semantic_role": "decorative_detail",
                            },
                            {
                                "kind": "text",
                                "value": "SAFRANBOLU",
                                "x": 45,
                                "y": 12,
                                "height": 4,
                                "align": "center",
                            },
                        ],
                    }
                },
            },
            {"type": "triangle", "w": 90, "h": 32, "count": 2, "label": "roof-support"},
            {
                "type": "panel",
                "w": 100,
                "h": 70,
                "edges": "eeee",
                "count": 2,
                "label": "roof",
                "markings": [
                    {
                        "kind": "line",
                        "points": [[8, 12], [92, 12], [92, 20], [8, 20], [8, 12]],
                        "semantic_role": "texture",
                    }
                ],
            },
        ]
        built = render_toolbox(parts, {"thickness": 3.0, "burn": 0.15})
        self._assert_sheet(built["svg_bytes"], built.get("primitives"), expect_engrave=True)
        report = built.get("manufacturing") or validate_svg_operations(built["svg_bytes"], built.get("primitives"))
        self.assertFalse(any("text marked CUT" in n for n in report.get("fail") or []))

    def test_traffic_light(self):
        from payas_cad import create_traffic_light

        result = create_traffic_light(public_base_url="http://127.0.0.1:8000")
        self.assertTrue(result.get("success"))
        from boxes_adapter import OUTPUT_DIR

        svg = (OUTPUT_DIR / result["file_id"]).read_bytes()
        self._assert_sheet(svg)
        mfg = result.get("manufacturing") or validate_svg_operations(svg)
        self.assertTrue(mfg.get("ok"), mfg.get("fail"))

    def test_ferris_wheel(self):
        from toolbox import render_toolbox

        parts = [
            {"type": "disc", "d": 90, "hole": 4, "label": "wheel-rim"},
            {"type": "disc", "d": 22, "hole": 4, "label": "hub"},
            {"type": "panel", "w": 8, "h": 38, "edges": "eeee", "count": 8, "label": "spoke"},
            {
                "type": "disc",
                "d": 16,
                "count": 6,
                "label": "gondola",
                "markings": [
                    {"kind": "icon", "icon": "heart", "x": 8, "y": 8, "width": 6, "semantic_role": "decorative_detail"}
                ],
            },
            {"type": "box", "x": 50, "y": 36, "h": 24, "bottom": True, "label": "base"},
        ]
        built = render_toolbox(parts, {"thickness": 3.0, "burn": 0.15})
        self._assert_sheet(built["svg_bytes"], built.get("primitives"), expect_engrave=True)

    def test_robot_kit(self):
        from payas_cad import create_robot_bank

        result = create_robot_bank()
        self.assertTrue(result.get("success"))
        from boxes_adapter import OUTPUT_DIR

        svg = (OUTPUT_DIR / result["file_id"]).read_bytes()
        self._assert_sheet(svg, expect_engrave=True)
        mfg = result.get("manufacturing") or validate_svg_operations(svg)
        self.assertTrue(mfg.get("ok"), mfg.get("fail"))
        from topology import inspect_topology

        topo = inspect_topology(svg)
        self.assertFalse(topo.get("open_cuts"))
        root = ET.fromstring(svg)
        held = [
            el
            for el in root.iter()
            if el.get("data-holding-nicks") or el.get("data-holding-bridges")
        ]
        for el in held:
            self.assertEqual((el.get("data-operation") or "").upper(), "CUT")


if __name__ == "__main__":
    unittest.main()
