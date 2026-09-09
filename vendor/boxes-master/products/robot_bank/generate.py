"""Read-only-in-memory validation gates precede Robot Bank SVG export."""
from pathlib import Path
import sys,json,math,copy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from boxes import edges
from products.ressam_robot.generate import RessamRobot,validate_closed,validate_final,add_bridges,polygon,parse_path,NS,require
from boxes.stem_layout import pack_sheet
from svgpathtools import Line
from xml.etree import ElementTree as ET
from shapely.geometry import Polygon,LineString,box
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from products.robot_bank.orientation import plane,OUTSIDE_NORMALS,validate_outside_faces

class RailTabs(edges.BaseEdge):
    char='T'
    def margin(self):return self.thickness
    def __call__(self,length,**kw):
        last=0
        for center in (34,82):
            self.edge(center-3-last)
            self.polyline(0,-90,3,90,6,90,3,-90)
            last=center+3
            self.mount_records.append(dict(part=self.current_name,centre=center,width=6,depth=3))
        self.edge(length-last)

class RobotBank(RessamRobot):
    expected_parts=15
    def define(self):
        self.catalog=json.loads((Path(__file__).parent/'components.json').read_text())
        # ClosedBox f/F convention: nominal external box120x85x148, at Z12.
        for name,w,h,es in [('Front',114,142,'FFFF'),('Back',114,142,'FFFF'),
                            ('Left',79,142,'FfFf'),('Right',79,142,'FfFf'),
                            ('Top',114,79,'ffff'),('Bottom',114,79,'ffff')]:
            self.panel('Bank '+name,w,h,es)
        self.hole_spec('Bank Top','coin-slot',57,39.5,34,4)
        self.hole_spec('Bank Back','service-opening',57,37,64,50)
        for x in (21,93):self.hole_spec('Bank Back','cover-M3',x,37,3.2)
        for name in ('Bank Left','Bank Right'):
            for z in (80,112):self.hole_spec(name,'arm-M3',66 if name=='Bank Left' else 13,z-15,3.2)
        for x in (12,36,84,108):
            for y in (18,66):self.hole_spec('Bank Bottom','rail-slot',x-3,y-3,3,6)
        self.panel('Rear Cover',80,66)
        for x in (4,76):self.hole_spec('Rear Cover','cover-M3',x,33,3.2)
        for name in ('Arm Left','Arm Right'):
            self.panel(name,44,70)
            for z in (18,50):self.hole_spec(name,'arm-M3',12 if name=='Arm Left' else 32,z,3.2)
        for name in ('Rail L1','Rail L2','Rail R1','Rail R2'):
            self.panel(name,101,12,'Teee')
            self.hole_spec(name,'toe-slot',9,7.5,12,3)
        for name in ('Toe Left','Toe Right'):self.panel(name,27,12)
    def render(self):
        self.addPart(RailTabs(self,None))
        for p in self.specs:
            self.current_name=p['name']
            if p['name'].startswith('Arm') or p['name']=='Rear Cover':
                radius=6 if p['name'].startswith('Arm') else 3
                def callback(r=radius):
                    with self.saved_context():
                        self.moveTo(-r,0);self.draw_features()
                self.roundedPlate(p['w'],p['h'],radius,edge='e',extend_corners=False,callback=[callback],move='up')
            else:self.rectangularWall(p['w'],p['h'],p['edges'],callback=[self.draw_features],move='up')

def local_shapes(data,robot):
    result={}
    for group,spec in zip(ET.fromstring(data).findall(NS+'g'),robot.specs):
        paths=[parse_path(p.get('d')) for p in group.findall(NS+'path')]
        outer=max(paths,key=lambda p:polygon(p).area);bounds=outer.bbox();es=spec['edges']
        ox=bounds[0]+robot.burn+(3 if es[3] in 'fF' else 0)
        oy=bounds[3]-robot.burn-(3 if es[0] in 'fFT' else 0)
        result[spec['name']]=dict(outer=polygon(outer),holes=[polygon(p) for p in paths if p is not outer],ox=ox,oy=oy,
            local=Polygon([(x-ox,oy-y) for x,y in polygon(outer).exterior.coords]))
    return result

def validate_assembly(robot,packed):
    specs={p['name']:p for p in robot.specs};actual=local_shapes(packed,robot)
    pairs=[('Bank Left',1,'Bank Front',3),('Bank Left',3,'Bank Back',1),
           ('Bank Right',3,'Bank Front',1),('Bank Right',1,'Bank Back',3)]
    for lid,edge in [('Bank Top',2),('Bank Bottom',0)]:
        pairs +=[(lid,0,'Bank Front',edge),(lid,2,'Bank Back',edge),(lid,3,'Bank Left',edge),(lid,1,'Bank Right',edge)]
    def intervals(name,e):
        s=specs[name];w,h=s['w'],s['h'];p=actual[name]['local']
        line=LineString([[(0,-1.5),(w,-1.5)],[(w+1.5,0),(w+1.5,h)],[(0,h+1.5),(w,h+1.5)],[(-1.5,0),(-1.5,h)]][e])
        cut=line.intersection(p) if s['edges'][e]=='f' else line.difference(p)
        geoms=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
        return sorted((min(q.coords[0][e%2],q.coords[-1][e%2]),max(q.coords[0][e%2],q.coords[-1][e%2])) for q in geoms if q.length>1e-5)
    checked=[];used=set()
    for a,ae,b,be in pairs:
        require(specs[a]['edges'][ae]=='f' and specs[b]['edges'][be]=='F','Finger type mismatch')
        aa,bb=intervals(a,ae),intervals(b,be)
        require(len(aa)==len(bb),'Finger count mismatch')
        for (l,r),(ll,rr) in zip(aa,bb):
            require(abs((l+r)-(ll+rr))<.005 and abs((r-l)-6.15)<.005 and abs((rr-ll)-5.85)<.005,'Actual finger profile mismatch')
        used.update([(a,ae),(b,be)])
        checked.append(dict(male=a,male_edge=ae,female=b,female_edge=be,count=len(aa),tab_mm=[6,3],slot_mm=[6,3],nominal_clearance_mm=0))
    require(used=={(p['name'],e) for p in robot.specs for e,c in enumerate(p['edges']) if c in 'fF'},'Unpaired finger edge')
    tabs=[]
    for name,x in [('Rail L1',12),('Rail L2',36),('Rail R1',84),('Rail R2',108)]:
        for c in (34,82):
            rec=[r for r in robot.mount_records if r['part']==name and r['centre']==c]
            require(len(rec)==1 and rec[0]['width']==6 and rec[0]['depth']==3,'Rail tab mismatch')
            matches=[f for f in robot.features if f['part']=='Bank Bottom' and f['kind']=='rail-slot' and (f['x']+3,f['y']+3,f['w'],f['h'])==(x,c-16,3,6)]
            require(len(matches)==1,'Rail slot mismatch')
            tabs.append(dict(male=name,female='Bank Bottom',center_world_xy=[x,c-16],tab_mm=[6,3],slot_mm=[6,3],nominal_clearance_mm=0))
        foot='Toe Left' if x<60 else 'Toe Right'
        slot=next(f for f in robot.features if f['part']==name and f['kind']=='toe-slot')
        require((slot['x'],slot['y'],slot['w'],slot['h'])==(9,7.5,12,3),'Toe slot moved')
        require(specs[foot]['w']==27 and specs[foot]['h']==12,'Toe end no longer fits rails')
        tabs.append(dict(male=foot+' rectangular end',female=name,tab_mm=[12,3],slot_mm=[12,3],insertion_mm=3,nominal_clearance_mm=0))
    bolts=[]
    for a,b in [('Arm Left','Bank Left'),('Arm Right','Bank Right')]:
        arm=sorted((*plane(a,f['x'],f['y'])[1:],f['w']) for f in robot.features if f['part']==a)
        wall=sorted((*plane(b,f['x'],f['y'])[1:],f['w']) for f in robot.features if f['part']==b and f['kind']=='arm-M3')
        require(arm==wall==[(16,80,3.2),(16,112,3.2)],'Arm fastening mismatch')
        bolts.append(dict(parts=[a,b],centers_yz=arm,quantity=2))
    cover=sorted((plane('Rear Cover',f['x'],f['y'])[0],plane('Rear Cover',f['x'],f['y'])[2],f['w']) for f in robot.features if f['part']=='Rear Cover')
    back=sorted((plane('Bank Back',f['x'],f['y'])[0],plane('Bank Back',f['x'],f['y'])[2],f['w']) for f in robot.features if f['part']=='Bank Back' and f['kind']=='cover-M3')
    require(cover==back==[(24,52,3.2),(96,52,3.2)],'Cover fastening mismatch')
    opening=next(f for f in robot.features if f['kind']=='service-opening')
    require((opening['x'],opening['y'],opening['w'],opening['h'])==(57,37,64,50),'Service aperture registration')
    require(box(20,19,100,85).contains(box(28,27,92,77)),'Cover fails to cover aperture')
    bolts.append(dict(parts=['Rear Cover','Bank Back'],centers_xz=cover,quantity=2))
    # Non-joint solids use conservative assembled bounding boxes. Finger, rail-tab and
    # toe/rail intersections are intentional and checked against their actual mating profiles above.
    bounds={'body':(0,0,12,120,85,160),
            'Arm Left':(-3,-16,62,0,-16+specs['Arm Left']['w'],62+specs['Arm Left']['h']),
            'Arm Right':(120,-16,62,123,-16+specs['Arm Right']['w'],62+specs['Arm Right']['h']),
            'Rear Cover':(20,85,19,20+specs['Rear Cover']['w'],88,19+specs['Rear Cover']['h'])}
    for n,x in [('Rail L1',12),('Rail L2',36),('Rail R1',84),('Rail R2',108)]:
        bounds[n]=(x-1.5,-16,12-specs[n]['h'],x+1.5,-16+specs[n]['w'],12)
    collision_pairs=0
    for i,(a,aa) in enumerate(bounds.items()):
        for name,bb in list(bounds.items())[:i]:
            overlap=[min(aa[k+3],bb[k+3])-max(aa[k],bb[k]) for k in range(3)]
            require(not all(o>1e-7 for o in overlap),'Non-joint collision: '+a+' / '+name)
            collision_pairs+=1
    return dict(finger_pairs=checked,tab_slot_pairs=tabs,bolt_pairs=bolts,wooden_parts=len(robot.specs),
        material_mm=3,kerf_mm=.15,outer_body_mm=[120,85,148],overall_mm=[126,104,160],
        cavity_mm=[114,79,142],service_aperture_mm=[64,50],coin_slot_mm=[34,4],
        support_polygon_xy_mm=[[10.5,-16],[109.5,-16],[109.5,85],[10.5,85]],
        nominal_body_center_xy_mm=[60,42.5],arm_foot_vertical_clearance_mm=47,
        non_joint_collision_pairs_checked=collision_pairs,
        foot_insertion_sequence='Fit each toe between its two rails first, then insert all rail tabs into bottom before closing the body.',
        status='NOMINAL_GEOMETRY_PASS_PHYSICAL_FIT_REQUIRED',
        limits=['Actual kerf and plywood thickness not measured','Press-fit retention needs test; light adhesive may be needed for permanent structural joints',
                'No physical drop, strength or full-coin-load test','Hardware length and washer/nut stack unresolved',
                'Passive coin bank only; LEDs/sensor not implemented'])

def engravings(robot,packed):
    font=TTFont('C:/Windows/Fonts/arialbd.ttf');gs=font.getGlyphSet();cm=font.getBestCmap()
    def text(s,cx,y,w,h):
        units=sum(gs[cm[ord(c)]].width for c in s);sc=min(w/units,h/1490);x=cx-units*sc/2;out=[]
        for c in s:
            pen=SVGPathPen(gs);gs[cm[ord(c)]].draw(TransformPen(pen,(sc,0,0,sc,x,y)))
            if pen.getCommands():out.extend(parse_path(pen.getCommands()).continuous_subpaths())
            x+=gs[cm[ord(c)]].width*sc
        return out
    def poly(pts):return parse_path('M '+' L '.join(f'{x},{y}' for x,y in pts)+' Z')
    def circle(x,y,r):
        return poly([(x+r*math.cos(i*math.tau/96),y+r*math.sin(i*math.tau/96)) for i in range(96)])
    def stroke(pts,width=.65):
        p=LineString(pts).buffer(width/2,cap_style=1,join_style=1)
        return poly(list(p.exterior.coords))
    art={p['name']:[] for p in robot.specs}
    f=art['Bank Front']
    for x in (33,81):
        f.extend([circle(x,101,14),circle(x,101,10)])
        if not getattr(robot,'electronic_revision',False):f.append(circle(x-3,104,2))
    f.append(parse_path('M 39,78 Q 57,60 75,78 Q 74,61 57,62 Q 40,61 39,78 Z'))
    f.append(parse_path('M 57,34 C 35,47 45,61 57,51 C 69,61 79,47 57,34 Z'))
    f+=text('DENE YAP',57,20,60,6)
    for x,sgn in [(17,1),(97,-1)]:
        f.append(circle(x,128,3));f.append(stroke([(x,124),(x,118),(x-10*sgn,112),(4 if sgn==1 else 110,112)]))
        f.append(circle(x,58,2.5));f.append(stroke([(x,54),(x+8*sgn,50),(x+8*sgn,43)]))
        for y in (33,38,43):f.append(stroke([(x-3,y),(x+4,y)]))
    right=art['Bank Right'];right+=text('HAYALİM',49,79,42,6)+text('BİSİKLET',49,69,42,5)
    right +=[circle(24,29,12),circle(59,29,12),stroke([(24,29),(36,48),(47,29),(24,29)]),stroke([(36,48),(56,48),(59,29),(47,29),(56,48),(53,55),(48,55)]),stroke([(32,49),(40,49)])]
    right.append(poly([(40,114),(44,132),(53,138),(59,130),(57,113),(50,116),(44,111)]));right.append(circle(51,127,3))
    left=art['Bank Left'];left+=text('BU KUMBARA',28,100,48,5)+text('BENİM HAYALİM',28,88,48,4)
    left.append(stroke([(10,77),(45,77)]));left+=text('BİRİKTİR',39.5,40,50,5)
    logo=json.loads((ROOT/'assets/payas/logo-school.contours.json').read_text());sc=72/logo['width']
    art['Bank Back'] += [poly([(21+x*sc,84+y*sc) for x,y in ring]) for ring in logo['rings']]
    art['Rear Cover']+=text('PARA KAPAĞI',40,49,56,5)+text('DENE YAP',40,15,48,5)
    art['Bank Top']+=text('HAYALİNE YAKLAŞ',57,57,90,5)
    for i in range(9):art['Bank Top'].append(circle(25+8*i,20,2))
    for name in ('Arm Left','Arm Right'):
        cx=30 if name=='Arm Left' else 14
        art[name].append(circle(cx,34,8))
        for x in (cx-5,cx,cx+5):art[name].append(stroke([(x,45),(x,53)]))
    shapes=local_shapes(packed,robot);records=[];seen=set()
    for name,paths in art.items():
        s=shapes[name]
        for p in paths:
            q=p.scaled(1,-1).translated(complex(s['ox'],s['oy']));shape=polygon(q)
            require(s['outer'].contains(shape),'Engraving outside '+name)
            require(all(shape.boundary.distance(h.boundary)>.25 for h in s['holes']),'Engraving touches opening '+name)
            require(q.d() not in seen,'Duplicate engraving contour');seen.add(q.d())
            records.append(dict(part=name,d=q.d()))
    return records

def build():
    b=RobotBank();b.open();b.render();raw=b.close().getvalue()
    validate_closed(raw,b)
    packed,layout=pack_sheet(raw,[(p['name'],) for p in b.specs],1500,3000,cluster_width=390)
    validate_closed(packed,b,True);assembly=validate_assembly(b,packed);art=engravings(b,packed)
    final,bridges=add_bridges(packed,b.expected_parts);tree=ET.fromstring(final)
    for rec in art:ET.SubElement(tree.find(NS+"g[@id='ENGRAVE']"),NS+'path',{'d':rec['d'],'data-panel':rec['part'],'fill':'none','stroke':'#000000','stroke-width':'0.15'})
    for p in tree.iter(NS+'path'):p.set('stroke','#000000')
    final=ET.tostring(tree,encoding='utf-8',xml_declaration=True);geometry=validate_final(final,bridges,b)
    orientation_checks=validate_outside_faces()
    report=dict(status='PASSIVE_MECHANICAL_PROTOTYPE',orientation_checks=orientation_checks,orientation_revision='OUTSIDE_FACES_REV1',geometry=geometry,assembly=assembly,layout=layout,parts=b.specs,
                features=b.features,mount_records=b.mount_records,bridges=bridges,engravings=art,components=b.catalog)
    return final,report,b

if __name__=='__main__':
    final,report,b=build();out=ROOT/'output/Payas_STEM_Robot_Kumbara_YON_REV1.svg'
    out.write_bytes(final);out.with_suffix('.validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(file=str(out),geometry=report['geometry'],layout=report['layout']),indent=2))
