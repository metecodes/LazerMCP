"""Payas STEM Dene Yap traffic light. Dimensions in mm, external envelopes."""
import math
import json
import io
from pathlib import Path

from boxes import Boxes, edges
from boxes.stem_validation import validate_surface, validate_svg
from boxes.stem_layout import pack_sheet


class TowerMountEdge(edges.BaseEdge):
    """One centred, one-thickness-deep tab; no fingers on this edge."""
    char = "T"

    def margin(self):
        return self.thickness

    def __call__(self, length, **kw):
        w, t = self.tower_tab_width, self.thickness
        if length < w + 2*t:
            raise ValueError("Insufficient tab shoulders")
        self.boxes.mount_tabs.append(dict(part=self.boxes.current_panel,
                                         centre=length/2, width=w, depth=t))
        self.polyline((length-w)/2, -90, t, 90, w, 90, t, -90, (length-w)/2)


class STEMTrafficLight(Boxes):
    """Payas STEM Dene Yap: hollow tower, exactly two mounting tabs."""
    ui_group = "Misc"
    description = """External dimensions. Leave bottom unglued for maintenance.
Mechanically checked prototype only: battery/switch envelopes are unresolved
in components.json. Burn is a per-side offset; calibrate on actual plywood."""

    def __init__(self):
        super().__init__()
        self.addSettingsArgs(edges.FingerJointSettings, finger=2., space=2.)
        self.buildArgParser()
        self.component_catalog = json.loads((Path(__file__).resolve().parents[2]/"components.json").read_text())
        components = self.component_catalog["components"]
        defaults = dict(base_width=120., base_depth=80., base_height=45.,
                        tower_width=36., tower_depth=30., tower_height=110.,
                        switch_w=components["switch"]["cutout"][0],
                        switch_h=components["switch"]["cutout"][1],
                        led_dia=components["led"]["hole_diameter"],
                        cable_dia=components["wires"]["routing_hole_diameter"],
                        tower_tab_width=10., slot_clearance=0.,
                        sheet_width=1500., sheet_height=3000., layout_width=300.)
        self.dimension_names = tuple(defaults)
        for name, value in defaults.items():
            self.argparser.add_argument("--"+name, type=float, default=value,
                                        help=name.replace("_", " ")+" (mm)")
        self.argparser.set_defaults(labels=False, reference=0, inner_corners="corner")

    def validate_parameters(self):
        c = self.component_catalog["components"]
        if (self.component_catalog["units"] != "mm" or set(c) != {"led", "switch", "resistor", "battery_holder", "wires"}
                or [c[k]["quantity"] for k in ("led", "switch", "resistor", "battery_holder")] != [3, 3, 3, 1]
                or c["resistor"]["resistance_ohms"] != 220 or c["battery_holder"]["cells"] != "3xAA"):
            raise ValueError("Component catalog does not match specified circuit")
        for name in self.dimension_names + ("thickness", "burn"):
            v = getattr(self, name)
            if not math.isfinite(v) or (v < 0 if name in ("burn", "slot_clearance") else v <= 0):
                raise ValueError("Invalid dimension: " + name)
        t = self.thickness
        if self.burn >= min(t, self.led_dia, self.cable_dia)/4:
            raise ValueError("Burn too large for smallest feature")
        if self.slot_clearance > t/4:
            raise ValueError("Excessive mounting clearance")
        if min(self.base_width, self.base_depth, self.base_height,
               self.tower_width, self.tower_depth, self.tower_height) <= 4*t:
            raise ValueError("Enclosure too small for material")
        if self.tower_depth-2*t < self.tower_tab_width+2*t:
            raise ValueError("Tower tab too wide")
        if self.format != "svg" or self.inner_corners != "corner":
            raise ValueError("Validated export requires SVG and inner_corners=corner")
        if self.tabs or self.reference or self.qr_code or self.debug:
            raise ValueError("Disable holding tabs, reference, QR and debug geometry")

    def open(self):
        self.validate_parameters()
        super().open()

    def panel_holes(self, name):
        for f in self.features:
            if f["part"] != name:
                continue
            if f["kind"] in ("led", "cable"):
                self.hole(f["x"], f["y"], d=f["w"])
            else:
                self.rectangularHole(f["x"], f["y"], f["w"], f["h"])

    def render(self):
        self.validate_parameters()
        t = self.thickness
        # ClosedBox uses these internal dimensions with paired f/F edges.
        x, y, h = self.base_width-2*t, self.base_depth-2*t, self.base_height-2*t
        tx, ty, th = self.tower_width-2*t, self.tower_depth-2*t, self.tower_height-t
        self.tower_centre = (x/2, y-self.tower_depth/2-t)
        cx, cy = self.tower_centre
        self.features = []
        def feature(part, kind, px, py, w, height=None):
            self.features.append(dict(part=part, kind=kind, x=px, y=py,
                                      w=w, h=w if height is None else height))
        for i in range(3):
            feature("Base Top", "switch", x*(i+1)/4, self.switch_h/2+2*t,
                    self.switch_w, self.switch_h)
            feature("Base Top", "cable", cx+(i-1)*(self.cable_dia+t), cy, self.cable_dia)
            feature("Tower Front", "led", tx/2, th*(i+1)/4, self.led_dia)
        for sign in (-1, 1):
            feature("Base Top", "slot", cx+sign*(self.tower_width-t)/2, cy,
                    t+self.slot_clearance, self.tower_tab_width+self.slot_clearance)
        self.panels = [
            ("Base Front", x, h, "FFFF"), ("Base Back", x, h, "FFFF"),
            ("Base Left", y, h, "FfFf"), ("Base Right", y, h, "FfFf"),
            ("Base Top", x, y, "ffff"), ("Base Bottom", x, y, "ffff"),
            ("Tower Front", tx, th, "eFFF"), ("Tower Back", tx, th, "eFFF"),
            ("Tower Left", ty, th, "TfFf"), ("Tower Right", ty, th, "TfFf"),
            ("Tower Cap", tx, ty, "ffff")]
        self.mount_tabs = []
        self.addPart(TowerMountEdge(self, None))
        self.validate_assembly(before_render=True)
        for name, width, height, edge_types in self.panels:
            self.current_panel = name
            self.rectangularWall(width, height, edge_types,
                                 callback=[lambda n=name: self.panel_holes(n)],
                                 move="up", label=name)
        self.validate_assembly()

    def validate_assembly(self, before_render=False):
        from shapely.geometry import box
        t = self.thickness
        counts = {k: sum(f["kind"] == k for f in self.features) for k in ("led", "switch", "cable", "slot")}
        if counts != dict(led=3, switch=3, cable=3, slot=2):
            raise ValueError("Wrong component opening counts")
        by_name = {p[0]: p for p in self.panels}
        if len(by_name) != 11:
            raise ValueError("Expected eleven wooden panels")
        def rectangle(f):
            return box(f["x"]-f["w"]/2, f["y"]-f["h"]/2,
                       f["x"]+f["w"]/2, f["y"]+f["h"]/2)
        for name, width, height, _ in self.panels:
            holes = [rectangle(f) for f in self.features if f["part"] == name]
            for i, hole in enumerate(holes):
                if not box(t, t, width-t, height-t).covers(hole):
                    raise ValueError("Opening too close to edge: " + name)
                if any(hole.distance(other) < t-1e-7 for other in holes[:i]):
                    raise ValueError("Insufficient web between openings: " + name)
        cx, cy = self.tower_centre
        cavity = box(cx-self.tower_width/2+t, cy-self.tower_depth/2+t,
                     cx+self.tower_width/2-t, cy+self.tower_depth/2-t)
        footprint = box(cx-self.tower_width/2, cy-self.tower_depth/2,
                        cx+self.tower_width/2, cy+self.tower_depth/2)
        for f in self.features:
            if f["kind"] == "cable" and not cavity.covers(rectangle(f)):
                raise ValueError("Cable hole outside hollow tower")
            if f["kind"] == "switch" and footprint.distance(rectangle(f)) < t:
                raise ValueError("Switch obstructed by tower")
        joins = []
        for prefix in ("Base", "Tower"):
            for front in ("Front", "Back"):
                for side, ei in (("Right", 1), ("Left", 3)):
                    joins.append((prefix+" "+front, ei, prefix+" "+side, 3 if front == "Front" else 1))
            lids = [("Top" if prefix == "Base" else "Cap", 2)]
            if prefix == "Base":
                lids.append(("Bottom", 0))
            for lid, wall_edge in lids:
                for wall, lid_edge in (("Front", 0), ("Right", 1), ("Back", 2), ("Left", 3)):
                    joins.append((prefix+" "+wall, wall_edge, prefix+" "+lid, lid_edge))
        used = set()
        for a, ai, b, bi in joins:
            pa, pb = by_name[a], by_name[b]
            la, lb = pa[1+ai%2], pb[1+bi%2]
            if set((pa[3][ai], pb[3][bi])) != {"f", "F"} or abs(la-lb) > 1e-7:
                raise ValueError("Incompatible finger joint: " + a + "/" + b)
            for panel, index in ((a, ai), (b, bi)):
                if (panel, index) in used:
                    raise ValueError("Edge used twice")
                used.add((panel, index))
            if self.edges["f"].calcFingers(la, None) != self.edges["F"].calcFingers(lb, None):
                raise ValueError("Unequal finger distribution")
        if used != {(p[0], i) for p in self.panels for i, e in enumerate(p[3]) if e in "fF"}:
            raise ValueError("Unpaired finger edge")
        settings = self.edges["f"].settings
        if settings.finger < t or settings.space < t or settings.surroundingspaces < 1:
            raise ValueError("Finger joints require material-width fingers and spaces")
        if settings.style != "rectangular" or settings.extra_length or settings.play:
            raise ValueError("Validated joints require rectangular style and zero extra_length/play")
        if not before_render:
            if sorted(tab["part"] for tab in self.mount_tabs) != ["Tower Left", "Tower Right"]:
                raise ValueError("Exactly one tab on each tower side required")
            for tab in self.mount_tabs:
                sign = -1 if tab["part"] == "Tower Left" else 1
                wx = cx+sign*(self.tower_width-t)/2
                wy = cy-self.tower_depth/2+t+tab["centre"]
                matches = [s for s in self.features if s["kind"] == "slot"
                           and abs(s["x"]-wx) < 1e-7 and abs(s["y"]-wy) < 1e-7
                           and abs(s["w"]-t-self.slot_clearance) < 1e-7
                           and abs(s["h"]-tab["width"]-self.slot_clearance) < 1e-7]
                if len(matches) != 1 or tab["depth"] != t:
                    raise ValueError("Tab has no unique physical matching slot")
        self.assembly_report = dict(openings=counts, wooden_panels=11, finger_joint_pairs=len(joins),
            tower_tabs=2, base_internal_mm=[self.base_width-2*t, self.base_depth-2*t, self.base_height-2*t],
            mounting_slot_nominal_mm=[t+self.slot_clearance, self.tower_tab_width+self.slot_clearance],
            burn_per_side_mm=self.burn, assumed_kerf_mm=2*self.burn, release_status="PROTOTYPE_ONLY",
            unresolved=["battery holder envelope", "switch body and clips", "LED flange and retention",
                        "wire bundle diameter", "measured material and kerf", "bottom retention force"])

    def close(self):
        if self.ctx is None:
            return
        self.validate_assembly()
        self.ctx.stroke()
        self.geometry_report = validate_surface(self.surface, self.panels, self.features,
                                               self.thickness, self.burn, self.tower_tab_width)
        data = super().close()
        self.svg_report = validate_svg(data.getvalue(), self.panels, self.features,
                                       self.thickness, self.burn, self.tower_tab_width)
        packed, self.layout_report = pack_sheet(data.getvalue(), self.panels,
            self.sheet_width, self.sheet_height, gap=max(3., 2*self.burn+self.thickness/2),
            cluster_width=self.layout_width)
        self.svg_report = validate_svg(packed, self.panels, self.features,
                                       self.thickness, self.burn, self.tower_tab_width)
        return io.BytesIO(packed)
