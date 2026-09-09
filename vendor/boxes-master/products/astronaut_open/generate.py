"""Open-frame astronaut demonstration kit, replacing the retired wide-box design."""
from pathlib import Path
import sys,json,math,copy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from products.ressam_robot.generate import RessamRobot,validate_closed,validate_final,add_bridges,polygon,parse_path,NS,require
from products.robot_bank.generate import local_shapes
from products.yacht.generate import Yacht,replace_profiles as replace_polygons,validate_assembly as static_slices
from products.astronaut_open.geometry import figure_shape,artwork,motion_check
from boxes.stem_layout import pack_sheet
from shapely.geometry import Polygon,Point,LineString,box
from xml.etree import ElementTree as ET
OUT=ROOT/'output/Payas_STEM_Astronot_AcikSase_V1'

class OpenAstronaut(RessamRobot):
 expected_parts=15
 world=Yacht.world
 def render(self):
  for p in self.specs:
   self.current_name=p['name']
   if p['name']=='Crank' or p['name'].startswith('Spacer'):
    def cb(p=p):
     with self.saved_context():self.moveTo(-p['w']/2,-p['h']/2);self.draw_features()
    self.parts.disc(p['w'],callback=cb,move='up')
   else:self.rectangularWall(p['w'],p['h'],callback=[self.draw_features],move='up')
 def define(self):
  self.catalog=json.loads(Path(__file__).with_name('components.json').read_text());self.profiles={};self.planes={};self.joints=[]
  self.metadata['description']='Payas STEM open-frame stationary astronaut; reference inspired, selected-hardware prototype'
  def panel(n,w,h,q,o,axes):
   self.panel(n,w,h);self.profiles[n]=q;self.planes[n]={'origin':o,'axes':axes}
  frame=box(0,3,124,18).union(box(13,3,111,164.5))
  for x in (25.5,98.5):frame=frame.union(Point(x,164.5).buffer(12.5,quad_segs=32))
  frame=frame.difference(box(38,110,86,180))
  panel('Open Frame',124,177,frame,[-62,0,3],[0,2,1])
  for n,x in [('Box Left',-30),('Box Right',27)]:panel(n,36,150,box(3,3,33,147),[x,0,6],[1,2,0])
  panel('Box Rear',68,150,box(0,3,68,147),[-34,33,6],[0,2,1])
  for n,z in [('Box Top',153),('Box Bottom',6)]:panel(n,68,36,box(0,0,68,36),[-34,3,z],[0,1,2])
  # H-shaped laminated base: forward/rear centre notches and two long side feet.
  base=Polygon([(0,0),(30,0),(30,38),(110,38),(110,0),(140,0),(140,100),(110,100),(110,78),(30,78),(30,100),(0,100)])
  panel('Base Upper',140,100,base,[-70,-40,3],[0,1,2]);panel('Base Lower',140,100,base,[-70,-40,0],[0,1,2])
  panel('Crank',44,44,Point(22,22).buffer(22,quad_segs=32),[-22,-8.5,77],[0,2,1])
  panel('Yoke',94,24,box(0,0,94,24),[-47,-20.7,87],[0,2,1])
  panel('Astronaut',112,160,figure_shape(),[-56,-29.7,57],[0,2,1])
  for n,x,y in [('Spacer Left',-29,-26.7),('Spacer Right',29,-26.7),('Spacer Left Extra',-29,-23.7),('Spacer Right Extra',29,-23.7)]:
   panel(n,18,18,Point(9,9).buffer(9,quad_segs=16),[x-9,y,90],[0,2,1]);self.hole_spec(n,'spacer-bolt',9,9,3.2)
  def join(male,edge,c,female):
   p=next(p for p in self.specs if p['name']==male);w,h=p['w'],p['h']
   if edge=='bottom':q=box(c-5,0,c+5,3);uv=[c,1.5];length_axis=0
   elif edge=='top':q=box(c-5,h-3,c+5,h);uv=[c,h-1.5];length_axis=0
   elif edge=='left':q=box(0,c-5,3,c+5);uv=[1.5,c];length_axis=1
   else:q=box(w-3,c-5,w,c+5);uv=[w-1.5,c];length_axis=1
   self.profiles[male]=self.profiles[male].union(q)
   xyz=self.world(male,*uv,1.5);fp=self.planes[female];xy=[xyz[a]-fp['origin'][a] for a in fp['axes'][:2]]
   dim=[10 if a==self.planes[male]['axes'][length_axis] else 3 for a in fp['axes'][:2]]
   jid=f'J{len(self.joints)+1:02}';self.hole_spec(female,jid,*xy,*dim)
   self.joints.append(dict(id=jid,male=male,edge=edge,uv=uv,length_axis=length_axis,female=female,slot_center=xy,slot_size=dim,xyz=xyz,tab_mm=[10,3],nominal_clearance_mm=0))
  for c in (22,102):join('Open Frame','bottom',c,'Base Upper')
  for n in ('Box Left','Box Right'):
   for c in (29,84,139):join(n,'left',c,'Open Frame');join(n,'right',c,'Box Rear')
   for c in (12,24):join(n,'bottom',c,'Box Bottom');join(n,'top',c,'Box Top')
  for c in (19,49):join('Box Rear','bottom',c,'Box Bottom');join('Box Rear','top',c,'Box Top')
  self.hole_spec('Open Frame','frame-opening',62,49,48,62)
  m=self.catalog['motor'];self.hole_spec('Open Frame','motor-boss',62,96,m['front_boss_diameter_mm']+.2)
  for x,y in m['mounting_holes']['centres_mm']:self.hole_spec('Open Frame','motor-mount',62+x,96+y,1.8)
  for x in (22,102):self.hole_spec('Open Frame','vertical-guide',x,146,4.4,44)
  self.hole_spec('Box Top','switch',34,15,*self.catalog['switch']['cutout_mm'])
  for n in ('Base Upper','Base Lower','Box Bottom'):
   for x in (-20,20):
    for y in (12,28):
     pl=self.planes[n];self.hole_spec(n,'base-bolt',x-pl['origin'][0],y-pl['origin'][1],8 if n=='Base Lower' else 3.2)
  # Straps moved to fit the narrower rear panel; battery dimensions remain sourced.
  for x in (11,57):
   for z in (22,54):self.hole_spec('Box Rear','battery-strap',x,z,3.2,6)
  self.hole_spec('Crank','shaft-clearance',22,22,3.4)
  for x,y in self.catalog['hub']['mounting_pattern_mm']:self.hole_spec('Crank','hub-mount',22+x,22+y,3.2)
  self.hole_spec('Crank','crank-pin',38,22,3.2)
  self.hole_spec('Yoke','horizontal-slot',47,12,40,4.4)
  for x in (18,76):self.hole_spec('Yoke','figure-mount',x,12,3.2)
  for x in (27,85):self.hole_spec('Astronaut','yoke-mount',x,42,3.2)
  for x in (16,96):self.hole_spec('Astronaut','guide-pin',x,92,3.2)
  # Window and circular holes are drawn by the shared Boxes helpers, not this outline map.
  for p in self.specs:
   q=self.profiles[p['name']];require(q.geom_type=='Polygon' and q.is_valid,'Disconnected profile '+p['name'])
   require(all(abs(a-b)<1e-6 for a,b in zip(q.bounds,(0,0,p['w'],p['h']))),'Profile bounds '+p['name'])

def replace_profiles(data,b):
 original=ET.fromstring(data);new=ET.fromstring(replace_polygons(data,b))
 for p,a,c in zip(b.specs,original.findall(NS+'g'),new.findall(NS+'g')):
  if p['name']=='Crank' or p['name'].startswith('Spacer'):
   outer=lambda g:max(g.findall(NS+'path'),key=lambda e:polygon(parse_path(e.get('d'))).area)
   outer(c).set('d',outer(a).get('d'))
 return ET.tostring(new)

def check(b,data):
 shapes=local_shapes(data,b)
 for j in b.joints:
  u,v=j['uv'];axis=j['length_axis'];line=LineString([(u-6,v),(u+6,v)]) if axis==0 else LineString([(u,v-6),(u,v+6)])
  q=shapes[j['male']]['local'].intersection(line);require(abs(q.length-10.15)<.005,'Wrong tab profile '+j['id'])
  f=next(f for f in b.features if f['kind']==j['id']);require([f['w'],f['h']]==j['slot_size'],'Wrong slot size')
  require(max(abs(x-y) for x,y in zip(b.world(f['part'],f['x'],f['y'],1.5),b.world(j['male'],u,v,1.5)))<1e-8,'Misaligned assembly joint')
 # Reuse the yacht's perpendicular-solid checker on stationary structure only.
 static=copy.copy(b);static.specs=b.specs[:8];static.joints=[]
 static.features=[f for f in b.features if f['part'] in {p['name'] for p in static.specs}]
 rt=ET.fromstring(data)
 for g in list(rt.findall(NS+'g'))[8:]:rt.remove(g)
 solid=static_slices(static,ET.tostring(rt))
 # Narrow cavity is 54mm between side walls: orient the 58mm battery dimension vertically.
 require(b.catalog['battery']['envelope_mm']==[58,48,15],'Revalidate changed battery')
 battery=[-24,18,20,24,33,78];require(battery[0]>-27 and battery[3]<27,'Battery side clearance')
 require(battery[5]<94,'Battery hits motor')
 require(3+b.catalog['motor']['full_envelope_mm'][2]<33,'Motor back clearance')
 sw=b.catalog['switch'];require(all(lo<=v<=hi for v,(lo,hi) in zip(sw['cutout_mm'],sw['cutout_allowed_mm'])),'Switch cutout')
 h=b.catalog['hardware'];play=h['shoulder']['shoulder_length_mm']-3-2*h['slide_washer']['thickness_mm']
 require(.25<=play<=.55 and h['shoulder']['shoulder_diameter_mm']==4,'Invalid slider stack')
 require(h['guide_standoff']['length_mm']==25 and h['crank_standoff']['length_mm']==7,'Wrong standoff')
 for n,k,ox,oz in [('Yoke','figure-mount',-47,87),('Astronaut','yoke-mount',-56,57)]:
  require(sorted((f['x']+ox,f['y']+oz) for f in b.features if f['part']==n and f['kind']==k)==[(-29,99),(29,99)],'Figure/yoke mount mismatch')
 for n,k,ox,oz in [('Open Frame','vertical-guide',-62,3),('Astronaut','guide-pin',-56,57)]:
  require(sorted((f['x']+ox,f['y']+oz) for f in b.features if f['part']==n and f['kind']==k)==[(-40,149),(40,149)],'Guide pin/slot centers mismatch')
 for n in ('Box Bottom','Base Upper','Base Lower'):
  require(sorted(tuple(b.world(n,f['x'],f['y'])[:2]) for f in b.features if f['part']==n and f['kind']=='base-bolt')==[(-20,12),(-20,28),(20,12),(20,28)],'Base screw axes mismatch')
 # Account for the selected shoulder head radius and 0.4mm axial float over a full revolution.
 require(h['shoulder']['head_height_mm']<=3,'Head collides with astronaut')
 for i in range(1441):
  x=16*math.cos(i*math.tau/1440)
  require(min(abs(x-a)-9-h['shoulder']['head_diameter_mm']/2 for a in (-29,29))>.5,'Head hits spacer')
 return dict(joints=b.joints,joint_count=len(b.joints),stationary_collision_slice_samples=solid['collision_slice_samples'],stationary_collisions=solid['nominal_solid_collisions'],
  battery_envelope_xyz_mm=battery,assembled_envelope_mm=[140,100,233],axial_play_mm=play,
  mandatory_postprocess='Countersink the two M1.6 motor holes to 90 degrees, heads exactly flush. Glue two base layers.',
  pending=['Actual plywood/kerf and joint retention','Motor seating and smooth manual rotation','3AA motor load/current, wire routing and stability test'],
  status='REFERENCE_OPEN_FRAME_PROTOTYPE; not a walking model or physical certification')

def build():
 b=OpenAstronaut();b.open();b.render();raw=replace_profiles(b.close().getvalue(),b);validate_closed(raw,b)
 packed,layout=pack_sheet(raw,[(p['name'],) for p in b.specs],1500,3000,cluster_width=420);validate_closed(packed,b,True)
 assembly=check(b,packed);motion=motion_check(b);art=artwork(b,packed)
 final,bridges=add_bridges(packed,b.expected_parts);root=ET.fromstring(final)
 for a in art:ET.SubElement(root.find(NS+"g[@id='ENGRAVE']"),NS+'path',{'d':a['d'],'data-panel':a['part'],'stroke':'#000000','stroke-width':'.15','fill':'none'})
 for e in root.iter(NS+'path'):e.set('stroke','#000000')
 final=ET.tostring(root,encoding='utf-8',xml_declaration=True);geometry=validate_final(final,bridges,b)
 return final,dict(status='OPEN_FRAME_V1_PROTOTYPE',parts=b.specs,features=b.features,planes=b.planes,assembly=assembly,motion=motion,engravings=art,bridges=bridges,geometry=geometry,layout=layout,components=b.catalog),b
if __name__=='__main__':
 data,r,b=build();OUT.with_suffix('.svg').write_bytes(data);OUT.with_suffix('.validation.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps({'geometry':r['geometry'],'layout':r['layout'],'joints':r['assembly']['joint_count']},indent=2))
