"""Ressam Robot prototype: Boxes.py geometry, checked four-bar and bridge export."""
from pathlib import Path as FilePath
import sys
import json
import math
import copy
from xml.etree import ElementTree as ET

ROOT = FilePath(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from boxes import Boxes, edges, Color
from boxes.stem_layout import pack_sheet
from svgpathtools import parse_path, Path, Line
from shapely.geometry import Polygon, Point, LineString, box
from shapely.affinity import affine_transform

NS = "{http://www.w3.org/2000/svg}"
INK = "http://www.inkscape.org/namespaces/inkscape"


def require(condition, message):
    if not condition:
        raise ValueError(message)


class MountEdge(edges.BaseEdge):
    char = "T"

    def margin(self):
        return self.thickness

    def __call__(self, length, **kw):
        specifications = [(length/2, 10)] if self.current_name.startswith("Head") else [(5, 6), (35, 6)]
        position = 0
        for centre, width in specifications:
            self.edge(centre-width/2-position)
            self.polyline(0, -90, self.thickness, 90, width, 90, self.thickness, -90)
            position = centre+width/2
            self.mount_records.append(dict(part=self.current_name, centre=centre, width=width,
                                           depth=self.thickness))
        self.edge(length-position)


class PenNotchEdge(edges.BaseEdge):
    char = "N"

    def __call__(self, length, **kw):
        self.polyline((length-20)/2, 90, 8, -90, 20, -90, 8, 90, (length-20)/2)


class RessamRobot(Boxes):
    """Single-pen four-bar drawing robot; no three-pen vibration drive."""

    def __init__(self, kerf=.15):
        require(math.isfinite(kerf) and 0<=kerf<.5,"Invalid kerf")
        super().__init__()
        self.addSettingsArgs(edges.FingerJointSettings, finger=2., space=2.)
        self.buildArgParser()
        self.parseArgs(["--thickness=3", f"--burn={kerf/2}", "--reference=0", "--labels=false",
                        "--inner_corners=corner", "--tabs=0"])
        self.catalog = json.loads((FilePath(__file__).parent/"components.json").read_text())
        self.specs, self.features, self.mount_records = [], [], []
        self.metadata["reproducible"] = True
        self.metadata["description"] = "Payas STEM Ressam Robot: checked prototype, physical test required."
        self.define()

    def panel(self, name, w, h, edge="eeee", disc=False):
        self.specs.append(dict(name=name, w=w, h=h, edges=edge, disc=disc))

    def hole_spec(self, part, kind, x, y, w, h=None, engrave=False):
        self.features.append(dict(part=part, kind=kind, x=x, y=y, w=w, h=h,
                                  layer="ENGRAVE" if engrave else "CUT"))

    def define(self):
        t = self.thickness
        # Two closed feet: 36 x 95 x 40 external, standard ClosedBox pairs.
        for side in ("Left", "Right"):
            prefix = side+" Foot "
            for suffix, w, h, es in [("Front", 30, 34, "FFFF"), ("Back", 30, 34, "FFFF"),
                ("Outer", 89, 34, "FfFf"), ("Inner", 89, 34, "FfFf"),
                ("Top", 30, 89, "ffff"), ("Bottom", 30, 89, "ffff")]:
                self.panel(prefix+suffix, w, h, es)
            sx = 8.5 if side == "Left" else 21.5
            self.hole_spec(prefix+"Top", "head-slot", sx, 74.5, t, 10)
        motor = self.catalog["components"]["motor"]
        self.hole_spec("Left Foot Top", "motor-boss", 15, 12, motor["front_boss_diameter_mm"]+.2)
        for dx, dy in motor["mounting_holes"]["centres_mm"]:
            self.hole_spec("Left Foot Top", "motor-M1.6", 15+dx, 12+dy, 1.8)
        self.hole_spec("Right Foot Top", "rocker-pivot", 15, 12, 3.2)
        # Wire access in the service rear of the motor foot.
        self.hole_spec("Left Foot Back", "wire", 15, 22, 5)
        # Open-bottom head stands on the feet. 110 x 35 x 120 external.
        for name, w, h, es in [("Head Front", 104, 117, "eFFF"), ("Head Back", 104, 117, "eFFF"),
                               ("Head Left", 29, 117, "TfFf"), ("Head Right", 29, 117, "TfFf"),
                               ("Head Top", 104, 29, "ffff")]:
            self.panel(name, w, h, es)
        for x in (28, 76):
            self.hole_spec("Head Front", "eye-bolt", x, 88, 3.2)
        self.hole_spec("Head Front", "smile", 52, 61, 24, 12, True)
        # Two bands retain the enclosed battery holder against the removable back.
        for x in (13, 91):
            for y in (51, 91):
                self.hole_spec("Head Back", "battery-strap", x, y, 3.2, 6)
        battery = self.catalog["components"]["battery_holder"]["envelope_mm"]
        self.hole_spec("Head Back", "battery-service-window", 52, 71, battery[0]+1.5, battery[1]+1.5)
        for y in (20, 105):
            for x in (5, 99):
                self.hole_spec("Head Back", "service-tie", x, y, 3.2, 5)
            for name in ("Head Left", "Head Right"):
                self.hole_spec(name, "service-tie", 23, y, 3.2, 5)
        self.panel("Crank", 36, 36, disc=True)
        self.hole_spec("Crank", "shaft-clearance", 0, 0, 3.4)
        hub = self.catalog["components"]["shaft_hub"]
        for x, y in hub["mounting_pattern_mm"]:
            self.hole_spec("Crank", "hub-M3", x, y, 3.2)
        self.hole_spec("Crank", "crank-pin", 12, 0, 3.2)
        self.panel("Rocker", 42, 12)
        for x in (6, 36):
            self.hole_spec("Rocker", "pivot", x, 6, 3.2)
        self.panel("Pen Beam", 96, 24, "Neee")
        for x in (6, 90):
            self.hole_spec("Pen Beam", "pivot", x, 18, 3.2)
        for x in (33, 63):
            self.hole_spec("Pen Beam", "carrier-slot", x, 5, 6, t)
        self.panel("Pen Saddle", 40, 40, "Teee")
        for x in (5, 35):
            for y in (12, 30):
                self.hole_spec("Pen Saddle", "pen-strap", x, y, 3.2, 5)
        # Mechanical retention of saddle: tie around beam through saddle lower slots.
        for x in (12, 28):
            self.hole_spec("Pen Saddle", "saddle-retainer", x, 5, 3.2, 3)
        for name in ("Eye Left", "Eye Right"):
            self.panel(name, 28, 28, disc=True)
            self.hole_spec(name, "eye-bolt", 0, 0, 3.2)
            self.hole_spec(name, "pupil", 0, 0, 12, engrave=True)
            self.hole_spec(name, "highlight", -3, 3, 2, engrave=True)

    def draw_features(self):
        for f in self.features:
            if f["part"] != self.current_name:
                continue
            kwargs = {"color": Color.ETCHING} if f["layer"] == "ENGRAVE" else {}
            if f["kind"] == "smile":
                self.ctx.stroke()
                with self.saved_context():
                    self.set_source_color(Color.ETCHING)
                    self.moveTo(f["x"]-12,f["y"],-90)
                    burn=self.burn
                    self.burn=0
                    try:
                        self.corner(180,12);self.corner(90);self.edge(2);self.corner(90)
                        self.corner(-180,10);self.corner(90);self.edge(2);self.corner(90)
                        self.ctx.stroke()
                    finally:
                        self.burn=burn
                continue
            if f["h"] is None:
                self.hole(f["x"], f["y"], d=f["w"], **kwargs)
            else:
                self.rectangularHole(f["x"], f["y"], f["w"], f["h"], **kwargs)

    def render(self):
        self.addPart(MountEdge(self, None))
        self.addPart(PenNotchEdge(self, None))
        for p in self.specs:
            self.current_name = p["name"]
            if p["disc"]:
                self.parts.disc(p["w"], callback=self.draw_features, move="up")
            else:
                self.rectangularWall(p["w"], p["h"], p["edges"], callback=[self.draw_features], move="up")


def polygon(path):
    require(path.iscontinuous() and abs(path.start-path.end) < .002, "Unexpected open design contour")
    points = [path.start]
    for segment in path:
        n = 1 if isinstance(segment, Line) else 48
        points.extend(segment.point(i/n) for i in range(1, n+1))
    points[-1] = points[0]
    result = Polygon([(p.real, p.imag) for p in points])
    require(result.is_valid and result.area > .001, "Invalid contour topology")
    return result


def paths_in(group, layer="CUT"):
    return [parse_path(p.get("d")) for p in group.findall(NS+"path")
            if (p.get("stroke") == "rgb(0,255,0)") == (layer == "ENGRAVE")]


def validate_closed(data, robot, packed=False):
    root = ET.fromstring(data)
    groups = [g for g in root.findall(NS+"g") if g.findall(NS+"path")]
    require(len(groups) == len(robot.specs) == getattr(robot, "expected_parts", 23), "Wrong wooden part count")
    outer_shapes, all_shapes, cut_count = [], [], 0
    seen = set()
    for group, spec in zip(groups, robot.specs):
        require(not packed or group.get("data-panel") == spec["name"], "Wrong panel identity")
        paths = paths_in(group)
        shapes = [polygon(p) for p in paths]
        expected = [f for f in robot.features if f["part"] == spec["name"] and f["layer"] == "CUT"]
        require(len(paths) == len(expected)+1, "Opening count mismatch: "+spec["name"])
        outer_index = max(range(len(shapes)), key=lambda i: shapes[i].area)
        outer = shapes[outer_index]
        holes = [s for i, s in enumerate(shapes) if i != outer_index]
        require(all(outer.contains(h) for h in holes), "Opening outside panel")
        for i, shape in enumerate(shapes):
            require(all(not shape.boundary.intersects(other.boundary) for other in shapes[:i]), "Intersecting cuts")
            require(all(shape.boundary.distance(other.boundary)>=1. for other in shapes[:i]),
                    "Less than 1 mm material between cut paths")
        xmin, ymin, xmax, ymax = outer.bounds
        if spec["disc"]:
            ox, oy = (xmin+xmax)/2, (ymin+ymax)/2
            ew = eh = spec["w"]+2*robot.burn
        else:
            left = robot.thickness if spec["edges"][3] in "fF" else 0
            bottom = robot.thickness if spec["edges"][0] in "fFT" else 0
            top = robot.thickness if spec["edges"][2] in "fF" else 0
            right = robot.thickness if spec["edges"][1] in "fF" else 0
            ox, oy = xmin+left+robot.burn, ymax-bottom-robot.burn
            ew, eh = spec["w"]+left+right+2*robot.burn, spec["h"]+top+bottom+2*robot.burn
        require(abs(xmax-xmin-ew)<.005 and abs(ymax-ymin-eh)<.005, "Panel dimension mismatch "+spec["name"])
        if spec["edges"][0]=="T":
            cross=outer.intersection(LineString([(xmin-1,ymax-1.5),(xmax+1,ymax-1.5)]))
            intervals=list(cross.geoms) if cross.geom_type=="MultiLineString" else [cross]
            declared=[r for r in robot.mount_records if r["part"]==spec["name"]]
            # Also support standalone validation from a fresh, not-yet-rendered instance.
            if not declared:
                declared=[dict(centre=spec['w']/2,width=10)] if spec['name'].startswith('Head') else [dict(centre=5,width=6),dict(centre=35,width=6)]
            require(len(intervals)==len(declared),"Actual tab count mismatch")
            for tab in declared:
                require(sum(abs(s.length-tab['width']-2*robot.burn)<.005 and
                            abs(s.centroid.x-ox-tab['centre'])<.005 for s in intervals)==1,
                        "Actual tab profile mismatch")
        for f in expected:
            w, h = f["w"]-2*robot.burn, (f["h"] or f["w"])-2*robot.burn
            matches = [s for s in holes if abs(s.centroid.x-ox-f["x"])<.005 and abs(s.centroid.y-oy+f["y"])<.005
                       and abs(s.bounds[2]-s.bounds[0]-w)<.005 and abs(s.bounds[3]-s.bounds[1]-h)<.005]
            require(len(matches)==1, "Opening size/position mismatch "+spec["name"]+" "+f["kind"])
            holes.remove(matches[0])
        for path in paths:
            for seg in path:
                if seg.length() < 1e-8:
                    continue
                points = tuple((round(p.real, 5), round(p.imag, 5)) for p in seg.bpoints())
                key = min(points, tuple(reversed(points)))
                require(key not in seen, "Duplicate cutting segment")
                seen.add(key)
        for engraving in paths_in(group, "ENGRAVE"):
            require(outer.covers(polygon(engraving)), "Engraving outside panel")
        if packed:
            require(xmin>=9.999 and ymin>=9.999 and xmax<=1490.001 and ymax<=2990.001, "Outside sheet")
        outer_shapes.append(outer)
        all_shapes.extend(shapes)
        cut_count += len(paths)
    for i, outer in enumerate(outer_shapes):
        require(all(outer.distance(other)>=2.99 if packed else outer.disjoint(other)
                    for other in outer_shapes[:i]), "Panel overlap or insufficient spacing")
    return dict(parts=len(groups), closed_design_contours=cut_count, duplicate_lines=0,
                overlapping_cuts=0, unexpected_open_paths=0, sheet_mm=[1500,3000] if packed else None)


def validate_joints(robot):
    catalog = robot.catalog["components"]
    require([catalog[k]["quantity"] for k in ("motor","battery_holder","shaft_hub","switch","marker")]==[1]*5,
            "Wrong component counts")
    require(catalog["motor"]["shaft_diameter_mm"]==catalog["shaft_hub"]["shaft_diameter_mm"], "Shaft hub mismatch")
    require(catalog["motor"]["full_envelope_mm"][2] < 34 and catalog["battery_holder"]["envelope_mm"][2] < 29,
            "Component does not fit enclosure")
    specs = {p["name"]: p for p in robot.specs}
    matches, used = [], set()
    for prefix, faces, lids in [("Left Foot ", ("Front","Back","Outer","Inner"), [("Top",2),("Bottom",0)]),
                                ("Right Foot ", ("Front","Back","Outer","Inner"), [("Top",2),("Bottom",0)]),
                                ("Head ", ("Front","Back","Left","Right"), [("Top",2)])]:
        a,b,c,d=faces
        for face in (a,b):
            for other, ei in ((c,1),(d,3)):
                matches.append((prefix+face,ei,prefix+other,1 if face==b else 3))
        for lid, ei in lids:
            for face, li in zip(faces,(0,2,1,3)):
                matches.append((prefix+face,ei,prefix+lid,li))
    for a, ai, b, bi in matches:
        sa,sb=specs[a],specs[b]
        la=sa["w"] if ai%2==0 else sa["h"]
        lb=sb["w"] if bi%2==0 else sb["h"]
        require({sa["edges"][ai],sb["edges"][bi]}=={"f","F"} and la==lb, "Unmatched finger joint")
        require(robot.edges["f"].calcFingers(la,None)==robot.edges["F"].calcFingers(lb,None), "Finger spacing mismatch")
        for item in ((a,ai),(b,bi)):
            require(item not in used,"Multiply used joint")
            used.add(item)
    expected={(p["name"],i) for p in robot.specs for i,e in enumerate(p["edges"]) if e in "fF"}
    require(used==expected,"Missing finger pair")
    tab_matches=[]
    for tab in robot.mount_records:
        if tab["part"].startswith("Head"):
            left=tab["part"]=="Head Left"
            target="Left Foot Top" if left else "Right Foot Top"
            world_tab=(11.5 if left else 118.5,63+tab["centre"])
            slots=[f for f in robot.features if f["part"]==target and f["kind"]=="head-slot"]
            slot=slots[0]
            world_slot=((0 if left else 94)+3+slot["x"],3+slot["y"])
            require(world_tab==world_slot and slot["w"]==3 and slot["h"]==tab["width"],"Head tab mismatch")
        else:
            target="Pen Beam"
            slots=[f for f in robot.features if f["kind"]=="carrier-slot" and f["x"]==28+tab["centre"]]
            require(len(slots)==1 and slots[0]["w"]==tab["width"] and slots[0]["h"]==3,"Carrier tab mismatch")
            slot=slots[0]
            world_tab=world_slot=(slot["x"],slot["y"])
        require(tab["depth"]==3,"Incorrect tab depth")
        tab_matches.append(dict(male=tab["part"],female=target,width=tab["width"],thickness=3,
                                centre=world_tab))
    require(len(tab_matches)==4,"Expected four mounting tabs")
    return dict(finger_pairs=len(matches), tab_slot_pairs=tab_matches,
                motor_floor_clearance_mm=37-catalog["motor"]["full_envelope_mm"][2]-3,
                battery_cavity_clearance_mm=29-catalog["battery_holder"]["envelope_mm"][2],
                link_vertical_clearance_mm=5, screw_head_design_envelope_mm=3)


def motion_check():
    """Full-cycle four-bar closure and horizontal pen/obstacle envelopes."""
    ground, crank, coupler, rocker = 94.,12.,84.,30.
    require(crank+ground < coupler+rocker, "Four-bar is not Grashof")
    track=[]
    worst=999.
    moving_clearance=999.
    feet=[box(0,0,36,95),box(94,0,130,95)]
    for i in range(1441):
        a=2*math.pi*i/1440
        A=complex(18+crank*math.cos(a),15+crank*math.sin(a))
        O=complex(112,15)
        delta=O-A; d=abs(delta)
        require(abs(coupler-rocker)<d<coupler+rocker,"Four-bar toggle")
        along=(coupler**2-rocker**2+d*d)/(2*d)
        transverse=math.sqrt(coupler**2-along**2)
        B=A+delta/d*complex(along,-transverse)
        require(abs(abs(B-O)-rocker)<1e-7,"Rocker closure")
        u=(B-A)/coupler
        # Beam pivots at local y=18, saddle at local y=5. Front is negative y.
        middle=(A+B)/2
        beam_local=Polygon([(0,0),(38,0),(38,8),(58,8),(58,0),(96,0),(96,24),(0,24)])
        origin=A-u*complex(6,18)
        beam=affine_transform(beam_local,[u.real,-u.imag,u.imag,u.real,origin.real,origin.imag])
        crank_shape=Point(18,15).buffer(18)
        rocker_shape=LineString([(O.real,O.imag),(B.real,B.imag)]).buffer(6)
        require(crank_shape.distance(rocker_shape)>2,"Coplanar links collide")
        require(beam.bounds[3]<58 and rocker_shape.bounds[3]<58 and crank_shape.bounds[3]<58,
                "Moving link hits upright head")
        # Pen centre varies with radius as it is strapped to saddle front face.
        for radius in (4.,7.):
            pen=middle+u*complex(0,-14.5-radius)
            shape=Point(pen.real,pen.imag).buffer(radius)
            clearance=min(shape.distance(f) for f in feet)
            require(clearance>2,"Pen intersects a foot")
            require(shape.bounds[3]<60-2,"Pen intersects upright body")
            gap=min(shape.distance(beam),shape.distance(crank_shape),shape.distance(rocker_shape))
            require(gap>2,"Pen intersects moving mechanism")
            moving_clearance=min(moving_clearance,gap)
            worst=min(worst,clearance)
        track.append([pen.real,pen.imag])
    return dict(samples=1441, ground_mm=ground, crank_radius_mm=crank,coupler_centres_mm=coupler,
        rocker_centres_mm=rocker, minimum_pen_foot_clearance_mm=round(worst,3),
        minimum_pen_link_clearance_mm=round(moving_clearance,3),
        pen_path_bbox_mm=[min(p[0] for p in track), min(p[1] for p in track),
                          max(p[0] for p in track), max(p[1] for p in track)],
        crank_z_mm=[46,49], beam_z_mm=[54,57], track=track,
        limitation="Geometric sweep, not motor load/friction or physical prototype certification")


def bridge_outer(path, gap=1.):
    """Two exact arclength gaps; preserve curves, never close across a bridge."""
    candidates=sorted(range(len(path)),key=lambda i:path[i].length(),reverse=True)
    chosen=[]
    for i in candidates:
        if path[i].length()>=5 and (not chosen or abs(path[i].point(.5)-path[chosen[0]].point(.5))>6):
            chosen.append(i)
        if len(chosen)==2:
            break
    require(len(chosen)==2,"No suitable holding bridge locations")
    kept=[]; removed=[]
    for i,segment in enumerate(path):
        if i not in chosen:
            kept.append(segment)
            continue
        length=segment.length()
        a=segment.ilength((length-gap)/2)
        b=segment.ilength((length+gap)/2)
        first, last = segment.cropped(0,a), segment.cropped(b,1)
        first.start, last.end = segment.start, segment.end
        kept.extend([first,last])
        removed.append(segment.cropped(a,b))
    cut=Path(*kept)
    require(abs(sum(s.length() for s in kept+removed)-path.length())<1e-6,"Bridge length conservation failed")
    require(all(abs(s.length()-gap)<1e-6 for s in removed),"Wrong bridge gap")
    require(len(cut.continuous_subpaths()) in (2,3),"Unexpected bridge fragmentation")
    return cut, [Path(s).d() for s in removed]


def add_bridges(data, expected_parts=23):
    root=ET.fromstring(data)
    records=[]
    for group in root.findall(NS+"g"):
        elements=[e for e in group.findall(NS+"path") if e.get("stroke")!="rgb(0,255,0)"]
        if not elements:
            continue
        element=max(elements,key=lambda e:polygon(parse_path(e.get("d"))).area)
        closed=element.get("d")
        cut,gaps=bridge_outer(parse_path(closed))
        element.set("d",cut.d())
        element.set("data-holding-bridges","2")
        records.append(dict(part=group.get("data-panel"),closed_design=closed,cut=cut.d(),gaps=gaps))
    require(len(records)==expected_parts,"Missing bridges")
    # Real layers; no visible bridge marks or stock outline that might be cut.
    ET.register_namespace("inkscape",INK)
    cut_layer=ET.SubElement(root,NS+"g",{"id":"CUT",f"{{{INK}}}groupmode":"layer",f"{{{INK}}}label":"CUT"})
    engrave_layer=ET.SubElement(root,NS+"g",{"id":"ENGRAVE","fill":"none",f"{{{INK}}}groupmode":"layer",f"{{{INK}}}label":"ENGRAVE"})
    for group in list(root.findall(NS+"g")):
        if group in (cut_layer,engrave_layer):
            continue
        root.remove(group)
        for element in list(group.findall(NS+"path")):
            if element.get("stroke")=="rgb(0,255,0)":
                group.remove(element); engrave_layer.append(element)
        cut_layer.append(group)
    return ET.tostring(root,encoding="utf-8",xml_declaration=True),records


def validate_final(data, records, robot):
    root=ET.fromstring(data)
    require(root.get("width")=="1500mm" and root.get("height")=="3000mm", "Wrong stock units")
    cut_layer=root.find(NS+"g[@id='CUT']")
    require(cut_layer is not None,"CUT layer missing")
    require(len(cut_layer.findall(NS+"g"))==len(records)==getattr(robot,"expected_parts",23),"Missing or extra cut panel")
    rebuilt=ET.Element(NS+"svg",root.attrib)
    for group,record in zip(cut_layer.findall(NS+"g"),records):
        require(group.get("data-panel")==record["part"],"Bridge part identity mismatch")
        clone=copy.deepcopy(group)
        bridged=clone.findall(NS+"path[@data-holding-bridges='2']")
        require(len(bridged)==1 and bridged[0].get("d")==record["cut"],"Unregistered cut gap or modified path")
        expected,gaps=bridge_outer(parse_path(record["closed_design"]))
        require(expected.d()==record["cut"] and gaps==record["gaps"],"Bridge manifest mismatch")
        bridged[0].set("d",record["closed_design"])
        rebuilt.append(clone)
    report=validate_closed(ET.tostring(rebuilt),robot,True)
    report.update(holding_bridges=2*len(records),bridge_toolpath_gap_mm=1.,
                  estimated_retained_bridge_mm=.85,closed_design_restored=True,
                  cut_paths_open_only_at_registered_bridges=True)
    return report


def main():
    robot=RessamRobot()
    motion=motion_check()
    robot.open(); robot.render()
    joints=validate_joints(robot)
    raw=robot.close().getvalue()  # In memory, not exported.
    validate_closed(raw,robot)
    packed,layout=pack_sheet(raw,[(p["name"],) for p in robot.specs],1500,3000,cluster_width=360)
    validate_closed(packed,robot,True)
    final,bridges=add_bridges(packed)
    validation=validate_final(final,bridges,robot)
    output=ROOT/"output/Payas_STEM_Ressam_Robot_PROTOTYPE.svg"
    report=dict(status="GEOMETRY_VALIDATED_PHYSICAL_PROTOTYPE_REQUIRED",geometry=validation,
        joints=joints,layout=layout,motion=motion,parts=robot.specs,features=robot.features,
        bridges=bridges,components=robot.catalog)
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(final)
    output.with_suffix(".validation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(output)
    print(json.dumps(validation))
    print(json.dumps(layout))


if __name__=="__main__":
    main()
