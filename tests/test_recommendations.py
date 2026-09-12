import unittest

from assembly_sheet import assembly_sheet
from markings import attach_marking, marking_geom
from physical import read_physical, resolve_burn
from review import NOT_VERIFIED, PASS, PRODUCTION_READY, PROTOTYPE_READY, format_gate_card, build_scorecard
from seen import check_what_you_see


class PhysicalTests(unittest.TestCase):
    def test_no_measure_stays_unverified(self):
        report = read_physical({}, moving=True)
        self.assertEqual(report["kerf"], NOT_VERIFIED)
        self.assertFalse(report["production_ok"])

    def test_measured_bar_passes_kerf(self):
        report = read_physical({"measured_bar_mm": 99.7}, moving=False)
        self.assertEqual(report["kerf"], PASS)
        self.assertEqual(report["movement"], "N/A")
        self.assertGreater(report["suggested_burn"], 0.14)

    def test_out_of_range_fails(self):
        report = read_physical({"measured_bar_mm": 90}, moving=False)
        self.assertEqual(report["kerf"], "FAIL")

    def test_production_needs_human_assembly(self):
        report = read_physical(
            {"measured_bar_mm": 100.0, "physical_assembly": "verified", "movement_test": "verified"},
            moving=True,
        )
        self.assertEqual(report["use"], "N/A")
        self.assertTrue(report["production_ok"])

    def test_powered_needs_use_test(self):
        report = read_physical(
            {"measured_bar_mm": 100.0, "physical_assembly": "verified"},
            moving=False,
            powered=True,
        )
        self.assertEqual(report["use"], NOT_VERIFIED)
        self.assertFalse(report["production_ok"])

    def test_powered_use_verified(self):
        report = read_physical(
            {
                "measured_bar_mm": 100.0,
                "physical_assembly": "verified",
                "use_test": "verified",
            },
            moving=False,
            powered=True,
        )
        self.assertEqual(report["use"], PASS)
        self.assertTrue(report["production_ok"])

    def test_never_invent_assembly(self):
        report = read_physical({"measured_bar_mm": 100.0}, moving=False)
        self.assertEqual(report["assembly"], NOT_VERIFIED)
        self.assertFalse(report["production_ok"])

    def test_resolve_burn_uses_measurement(self):
        burn, report = resolve_burn({"measured_bar_mm": 99.7})
        self.assertEqual(burn, report["suggested_burn"])


class SeenTests(unittest.TestCase):
    def test_rotor_requires_propeller(self):
        notes = check_what_you_see([{"type": "disc", "d": 40}], "4 kanatlı pervane")
        self.assertTrue(any(n["status"] == "FAIL" for n in notes))

    def test_rotor_ok(self):
        notes = check_what_you_see([{"type": "propeller", "blades": 4, "d": 48}], "4 kanatlı pervane")
        self.assertTrue(any(n["status"] == "PASS" for n in notes))

    def test_door_requires_slot(self):
        notes = check_what_you_see([{"type": "box", "x": 70, "y": 50, "h": 80}], "ön yüzde kapı var")
        self.assertTrue(any("slots" in n["note"] for n in notes if n["status"] == "FAIL"))


class MarkingTests(unittest.TestCase):
    def test_text_geom(self):
        geom = marking_geom({"kind": "text", "value": "PAYAS", "x": 10, "y": 10, "height": 6})
        self.assertIsNotNone(geom)

    def test_attach_target(self):
        parts = [{"type": "panel", "w": 36, "h": 36, "label": "motor-mount"}]
        attach_marking(parts, {"type": "marking", "target_part": "motor-mount", "kind": "text", "value": "M"})
        self.assertTrue(parts[0].get("markings"))


class CardTests(unittest.TestCase):
    def test_prototype_card_format(self):
        score = build_scorecard([], {"kerf": NOT_VERIFIED, "assembly": NOT_VERIFIED, "movement": NOT_VERIFIED})
        card = format_gate_card(score, PROTOTYPE_READY, "Prototype SVG", "BLOCKED")
        self.assertIn("FINAL STATUS: PROTOTYPE READY", card)
        self.assertIn("Physical Kerf Test      NOT VERIFIED", card)
        self.assertIn("After Assembly Use      NOT VERIFIED", card)
        self.assertIn("PRODUCTION EXPORT:\nBLOCKED", card)

    def test_production_card(self):
        score = build_scorecard([], {"kerf": PASS, "assembly": PASS, "movement": PASS})
        card = format_gate_card(score, PRODUCTION_READY, "Production SVG", "AUTHORIZED")
        self.assertIn("FINAL STATUS: PRODUCTION READY", card)
        self.assertIn("AUTHORIZED OUTPUT:\nProduction SVG", card)

    def test_assembly_sheet_order(self):
        text = assembly_sheet(
            {
                "parts": [
                    {"name": "propeller", "kind": "propeller"},
                    {"name": "front", "kind": "wall"},
                    {"name": "bottom", "kind": "floor"},
                ]
            }
        )
        self.assertIn("1. bottom", text)
        self.assertIn("front", text)
        self.assertLess(text.index("bottom"), text.index("propeller"))
        self.assertNotIn("AFTER ASSEMBLY USE", text)

    def test_use_sheet_named_kits(self):
        from assembly_sheet import use_sheet

        traffic = use_sheet("traffic_light")
        self.assertIn("AFTER ASSEMBLY USE", traffic)
        self.assertIn("şalter", traffic.lower())
        robot = use_sheet("PayasRobot")
        self.assertIn("LED", robot)
        self.assertIn("vida", robot.lower())
        self.assertEqual(use_sheet("product_box"), "")


class StudioTests(unittest.TestCase):
    def test_bom_named_kit(self):
        from bom import build_bom

        bom = build_bom(
            product="robot_bank",
            material={"id": "poplar_3mm", "name": "3 mm kavak kontrplak", "thickness": 3.0},
        )
        self.assertIn("MATERIALS (MCP)", bom["speak"])
        self.assertTrue(any("M3" in row["item"] for row in bom["lines"]))
        self.assertTrue(any("LED" in row["item"] for row in bom["lines"]))
        self.assertTrue(any("şalter" in row["item"].lower() for row in bom["lines"]))

    def test_bom_traffic_has_three_switches(self):
        from bom import build_bom

        bom = build_bom(
            product="traffic_light",
            material={"id": "poplar_3mm", "name": "3 mm kavak kontrplak", "thickness": 3.0},
        )
        switch = next(row for row in bom["lines"] if "şalter" in row["item"].lower())
        self.assertEqual(switch["qty"], 3)

    def test_bom_composed_writes_hardware(self):
        from bom import build_bom

        bom = build_bom(
            primitives=[{"type": "box", "x": 70, "y": 50, "h": 80}, {"type": "propeller", "d": 40, "hole": 4}],
            material={"id": "poplar_3mm", "name": "3 mm kavak kontrplak", "thickness": 3.0, "sheet_w": 1500, "sheet_h": 3000},
        )
        self.assertIn("MATERIALS (MCP)", bom["speak"])
        self.assertTrue(any("mil" in row["item"].lower() for row in bom["lines"]))

    def test_profiles_resolve(self):
        from profiles import apply_profiles

        params = apply_profiles({"material": "mdf", "machine": "desktop_400"})
        self.assertEqual(params["thickness"], 3.0)
        self.assertEqual(params["material"], "mdf_3mm")
        self.assertEqual(params["_machine"]["bed_w"], 400)

    def test_calibration_persist(self):
        import os
        import tempfile

        from calibrate import apply_stored_burn, record_calibration
        from physical import read_physical

        tmp = tempfile.mkdtemp()
        old = os.environ.get("MCP_DATA_DIR")
        os.environ["MCP_DATA_DIR"] = tmp
        try:
            phys = read_physical({"measured_bar_mm": 99.7}, moving=False)
            row = record_calibration({"machine": "payas_workshop", "material": "poplar_3mm"}, phys)
            self.assertIsNotNone(row)
            applied = apply_stored_burn({"machine": "payas_workshop", "material": "poplar_3mm"})
            self.assertIn("burn", applied)
        finally:
            if old is None:
                os.environ.pop("MCP_DATA_DIR", None)
            else:
                os.environ["MCP_DATA_DIR"] = old

    def test_free_plan_hides_dxf(self):
        import os

        from plans import apply_plan_to_result, get_plan

        old = os.environ.get("LASERMCP_BETA")
        os.environ["LASERMCP_BETA"] = "0"
        try:
            self.assertFalse(get_plan("free")["dxf"])
            self.assertTrue(get_plan("maker")["dxf"])
            self.assertTrue(get_plan("pro")["bom"])
            out = apply_plan_to_result({"dxf_url": "/x.dxf", "speak": "CARD\n\nMATERIALS (MCP):\n- glue", "bom": {"speak": "x"}})
            self.assertNotIn("dxf_url", out)
        finally:
            if old is None:
                os.environ.pop("LASERMCP_BETA", None)
            else:
                os.environ["LASERMCP_BETA"] = old

    def test_maker_keeps_dxf_strips_bom(self):
        import os

        from keys import current_auth
        from plans import apply_plan_to_result

        old = os.environ.get("LASERMCP_BETA")
        os.environ["LASERMCP_BETA"] = "0"
        token = current_auth.set({"id": "k1", "plan": "maker", "role": "workshop"})
        try:
            out = apply_plan_to_result({
                "dxf_url": "/x.dxf",
                "speak": "CARD\n\nMATERIALS (MCP):\n- glue",
                "bom": {"speak": "x"},
                "project": {"id": "p"},
                "sheet_ids": ["a", "b"],
                "sheets": 2,
            })
            self.assertIn("dxf_url", out)
            self.assertNotIn("bom", out)
            self.assertNotIn("project", out)
            self.assertEqual(out.get("sheets"), 1)
        finally:
            current_auth.reset(token)
            if old is None:
                os.environ.pop("LASERMCP_BETA", None)
            else:
                os.environ["LASERMCP_BETA"] = old

    def test_generate_svg_uses_material_kerf(self):
        from boxes_adapter import _merge_parameters

        merged = _merge_parameters({"x": 80, "y": 60, "h": 40, "material": "mdf_3mm"})
        self.assertAlmostEqual(float(merged["burn"]), 0.2)
        self.assertEqual(merged["material"], "mdf_3mm")

    def test_plan_turkish_product_box(self):
        from job_planner import plan_laser_job

        plan = plan_laser_job("180 mm ürün kutusu yap")
        self.assertEqual(plan.get("next_tool"), "create_product_box")

    def test_plan_turkish_roof_is_assembly(self):
        from job_planner import plan_laser_job

        plan = plan_laser_job("ahşap ev, çatı ve dört duvar")
        self.assertEqual(plan.get("next_tool"), "create_design")

    def test_validate_missing_file_is_mcp_safe(self):
        from payas_cad import validate_assembly

        report = validate_assembly(file_id="no-such-file.svg")
        self.assertTrue(report.get("success"))
        self.assertTrue(report.get("look_again"))

    def test_assembly_graph_edges(self):
        from assembly import check_assembly

        report = check_assembly([{"type": "box", "x": 80, "y": 80, "h": 80, "bottom": True}])
        graph = report.get("graph") or {}
        self.assertTrue(graph.get("nodes"))
        self.assertGreaterEqual(graph.get("edge_count") or 0, 1)


if __name__ == "__main__":
    unittest.main()
