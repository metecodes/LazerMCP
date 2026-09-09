"""Static yacht kit: source-referenced appearance, independently dimensioned joints."""
from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from products.ressam_robot.generate import RessamRobot,validate_closed,validate_final,add_bridges,polygon,parse_path,NS,require
from products.robot_bank.generate import local_shapes
from boxes.stem_layout import pack_sheet
from shapely.geometry import Polygon,Point,box,LineString
from shapely.ops import unary_union
from xml.etree import ElementTree as ET
OUT=ROOT/'output/Payas_STEM_Yat_PROTOTYPE'

def path_poly(p):return parse_path('M '+' L '.join(f'{x},{y}' for x,y in p.exterior.coords)+' Z')

class Yacht(RessamRobot):
 expected_parts=17
 def define(self):
  self.catalog={'electronic_components':[],'material_mm':3,'kerf_mm':.15,'dimension_basis':'Designed 300 x 110 x 151 mm; not measured from photograph','product':'Static display yacht, not a waterproof or floating hull'}
  self.metadata['description']='Payas STEM Yacht: static 3mm plywood assembly prototype'
  self.profiles={};self.planes={};self.joints=[];self.art=[]
  def panel(n,w,h,shape,origin,axes):
   self.panel(n,w,h);self.profiles[n]=shape;self.planes[n]={'origin':origin,'axes':axes}
  # axes: local u, local v and positive material thickness, expressed as global coordinate indices.
  deck=Polygon([(0,15),(10,0),(235,0),(280,20),(300,45),(300,65),(280,90),(235,110),(10,110),(0,95)])
  panel('Main Deck',300,110,deck,[0,-55,43],[0,1,2])
  hull=Polygon([(0,43),(240,43),(240,35),(185,0),(20,0),(0,15)])
  for n,y in [('Hull Left',-40),('Hull Right',37)]:panel(n,240,46,hull,[25,y,0],[0,2,1])
  for n,x in [('Hull Bulkhead Rear',65),('Hull Bulkhead Front',190)]:panel(n,74,46,box(0,0,74,43),[x,-37,0],[1,2,0])
  cabin=Polygon([(0,3),(190,3),(160,63),(15,63)])
  for n,y in [('Cabin Left',-33),('Cabin Right',30)]:panel(n,190,66,cabin,[55,y,43],[0,2,1])
  for n,x in [('Cabin Front',205),('Cabin Rear',78)]:panel(n,60,66,box(0,3,60,63),[x,-30,43],[1,2,0])
  panel('Cabin Roof',160,76,Polygon([(0,5),(5,0),(150,0),(160,8),(160,68),(150,76),(5,76),(0,71)]),[65,-38,106],[0,1,2])
  fly=Polygon([(0,3),(50,3),(40,42),(10,42)])
  for n,y in [('Fly Support Left',-26.5),('Fly Support Right',23.5)]:panel(n,50,45,fly,[95,y,106],[0,2,1])
  panel('Fly Roof',90,68,box(0,0,90,68),[85,-34,148],[0,1,2])
  panel('Stern Bench',40,66,box(0,0,40,66),[8,-33,61],[0,1,2])
  for n,y in [('Bench Support Left',-26.5),('Bench Support Right',23.5)]:panel(n,30,21,Polygon([(0,3),(30,3),(26,18),(4,18)]),[10,y,43],[0,2,1])
  anchor=Polygon([(0,12),(6,12),(6,8),(12,4),(12,22),(18,22),(18,4),(24,8),(24,12),(30,12),(25,3),(15,0),(5,3)]).union(Point(15,25).buffer(7,quad_segs=32))
  panel('Anchor',30,35,anchor.union(box(10,29,20,32)),[265,0,11],[0,2,1])
  # Each tab's mating slot is derived in assembled coordinates, then checked against exported geometry.
  def join(male,edge,c,female):
   spec=next(p for p in self.specs if p['name']==male);h=spec['h'];v=1.5 if edge=='bottom' else h-1.5
   tab=box(c-5,0 if edge=='bottom' else h-3,c+5,3 if edge=='bottom' else h)
   self.profiles[male]=self.profiles[male].union(tab)
   xyz=self.world(male,c,v,1.5);fp=self.planes[female];uv=[xyz[a]-fp['origin'][a] for a in fp['axes'][:2]]
   ma=self.planes[male]['axes'];dim=[10 if a==ma[0] else 3 for a in fp['axes'][:2]]
   jid=f'J{len(self.joints)+1:02}';self.hole_spec(female,jid,*uv,*dim)
   self.joints.append(dict(id=jid,male=male,edge=edge,center=c,width=10,depth=3,female=female,slot_center=uv,slot_size=dim,xyz=xyz))
  for n in ('Hull Left','Hull Right'):
   for c in (35,110,195):join(n,'top',c,'Main Deck')
  for n in ('Hull Bulkhead Rear','Hull Bulkhead Front'):
   for c in (20,54):join(n,'top',c,'Main Deck')
  for n in ('Cabin Left','Cabin Right'):
   for c in (35,100,160):join(n,'bottom',c,'Main Deck')
   for c in (45,125):join(n,'top',c,'Cabin Roof')
  for n in ('Cabin Front','Cabin Rear'):
   for c in (15,45):join(n,'bottom',c,'Main Deck');join(n,'top',c,'Cabin Roof')
  for n in ('Fly Support Left','Fly Support Right'):
   for c in (12,38):join(n,'bottom',c,'Cabin Roof')
   for c in (15,35):join(n,'top',c,'Fly Roof')
  for n in ('Bench Support Left','Bench Support Right'):
   for c in (8,22):join(n,'bottom',c,'Main Deck')
   join(n,'top',15,'Stern Bench')
  join('Anchor','top',15,'Main Deck')
  for n in ('Cabin Left','Cabin Right'):
   for x in (62,120):self.hole_spec(n,'cabin-window',x,29,38,17)
   for x in (34,57):self.hole_spec(n,'upper-porthole',x,51,10)
  for x in (16,44):self.hole_spec('Cabin Front','windscreen',x,36,18,28)
  self.hole_spec('Cabin Rear','door',30,26,20,30)
  self.hole_spec('Anchor','ring',15,25,6)
  for n in ('Fly Support Left','Fly Support Right'):self.hole_spec(n,'bridge-window',25,24,18,12)
  # All decorative contours are closed and belong only to ENGRAVE.
  for n in ('Hull Left','Hull Right'):
   for x in (62,154):
    for radius in (12,9):self.art.append((n,Point(x,23).buffer(radius,quad_segs=48)))
    for angle in (0,math.pi/2,math.pi,3*math.pi/2):
     self.art.append((n,LineString([(x+9*math.cos(angle),23+9*math.sin(angle)),(x+12*math.cos(angle),23+12*math.sin(angle))]).buffer(.2)))
  for y in (12,22,44,54):self.art.append(('Stern Bench',box(5,y,35,y+.35)))
  for n in ('Cabin Left','Cabin Right'):
   for z in (12,17,22,27):self.art.append((n,box(12,z,26,z+.4)))
  for p in self.specs:
   q=self.profiles[p['name']];require(q.geom_type=='Polygon' and q.is_valid,'Disconnected part '+p['name'])
   require(all(abs(a-b)<1e-6 for a,b in zip(q.bounds,(0,0,p['w'],p['h']))),'Nominal bounds '+p['name'])
 def world(self,n,u,v,w=0):
  p=self.planes[n];out=p['origin'].copy()
  for a,d in zip(p['axes'],(u,v,w)):out[a]+=d
  return out
 def render(self):
  for p in self.specs:
   self.current_name=p['name'];self.rectangularWall(p['w'],p['h'],callback=[self.draw_features],move='up')

def replace_profiles(data,b):
 root=ET.fromstring(data)
 for p,g in zip(b.specs,root.findall(NS+'g')):
  e=max(g.findall(NS+'path'),key=lambda e:polygon(parse_path(e.get('d'))).area)
  x0,x1,y0,y1=parse_path(e.get('d')).bbox();ox=x0+b.burn;oy=y1-b.burn
  e.set('d',path_poly(b.profiles[p['name']].buffer(b.burn,join_style='round',quad_segs=16)).scaled(1,-1).translated(complex(ox,oy)).d())
 return ET.tostring(root)

def validate_assembly(b,data):
 shapes=local_shapes(data,b);checked=[]
 for j in b.joints:
  p=next(p for p in b.specs if p['name']==j['male']);v=1.5 if j['edge']=='bottom' else p['h']-1.5;c=j['center']
  tab=shapes[j['male']]['local'].intersection(LineString([(c-6,v),(c+6,v)]))
  require(abs(tab.length-10.15)<.005 and abs(tab.centroid.x-c)<.005,'Actual male tab mismatch '+j['id'])
  f=next(f for f in b.features if f['kind']==j['id'])
  require(f['part']==j['female'] and [f['x'],f['y']]==j['slot_center'] and [f['w'],f['h']]==j['slot_size'],'Slot declaration mismatch')
  xyz=b.world(f['part'],f['x'],f['y'],1.5)
  require(max(abs(x-y) for x,y in zip(xyz,b.world(j['male'],c,v,1.5)))<1e-8,'Assembly coordinate mismatch')
  checked.append(dict(**j,nominal_clearance_mm=0,result='MATCH'))
 # No spare male protrusions: independently extract every top/bottom thin-section interval.
 for p in b.specs:
  n=p['name']
  for edge,v in [('bottom',1.5),('top',p['h']-1.5)]:
   js=[j for j in b.joints if j['male']==n and j['edge']==edge]
   if not js:continue
   section=shapes[n]['local'].intersection(LineString([(-1,v),(p['w']+1,v)]))
   segs=list(section.geoms) if hasattr(section,'geoms') else [section]
   require(len(segs)==len(js),'Unregistered male tab '+n)
 # Assembly bounding boxes and exact nominal polygon cross-sections for perpendicular panels.
 solids={}
 for p in b.specs:
  n=p['name'];q=b.profiles[n]
  for f in b.features:
   if f['part']==n:q=q.difference(Point(f['x'],f['y']).buffer(f['w']/2,quad_segs=48) if f['h'] is None else box(f['x']-f['w']/2,f['y']-f['h']/2,f['x']+f['w']/2,f['y']+f['h']/2))
  solids[n]=q
 collisions=[];samples=0
 for i,a in enumerate(b.specs):
  for bb in b.specs[:i]:
   an,bn=a['name'],bb['name'];pa,pb=b.planes[an],b.planes[bn]
   aa=[b.world(an,0,0),b.world(an,a['w'],a['h'],3)];ab=[b.world(bn,0,0),b.world(bn,bb['w'],bb['h'],3)]
   low=[max(aa[0][k],ab[0][k]) for k in range(3)];hi=[min(aa[1][k],ab[1][k]) for k in range(3)]
   if any(hi[k]-low[k]<1e-7 for k in range(3)):continue
   # Test interior slices; tab-slot contacts on boundary are permitted.
   na,nb=pa['axes'][2],pb['axes'][2]
   if na==nb:raise ValueError('Unexpected coplanar slab overlap '+an+' / '+bn)
   common=next(k for k in range(3) if k not in (na,nb))
   def sec(name,fixed_axis,value):
    pl=b.planes[name];uv=pl['axes'][:2];q=solids[name]
    coord=value-pl['origin'][fixed_axis];line=LineString([(coord,-1000),(coord,1000)]) if uv[0]==fixed_axis else LineString([(-1000,coord),(1000,coord)])
    cut=q.intersection(line);gs=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
    return [(min(z[uv.index(common)] for z in g.coords)+pl['origin'][common],max(z[uv.index(common)] for z in g.coords)+pl['origin'][common]) for g in gs if g.geom_type=='LineString' and g.length>1e-8]
   for fa in (.001,.25,.5,.75,.999):
    for fb in (.001,.25,.5,.75,.999):
     sa=sec(an,nb,low[nb]+fb*(hi[nb]-low[nb]));sb=sec(bn,na,low[na]+fa*(hi[na]-low[na]));samples+=1
     if any(min(x1,y1)-max(x0,y0)>1e-6 for x0,x1 in sa for y0,y1 in sb):collisions.append([an,bn])
 require(not collisions,'Nominal solid collision '+str(collisions[:3]))
 return dict(joints=checked,joint_count=len(checked),collision_slice_samples=samples,nominal_solid_collisions=collisions,
  assembled_mm=[300,110,151],electronic_count=0,assembly_sequence=['Lower hull panels and bulkheads: insert their upper tabs into underside of Main Deck','Anchor: insert upward into bow slot','Cabin sides/front/rear: insert downward into deck; Cabin Roof lowered onto upper tabs','Fly supports: insert into Cabin Roof; Fly Roof lowered onto them','Bench supports: insert into Main Deck; Stern Bench lowered onto them'],
  limitations=['Orthogonal nominal rigid-panel cross-section checks, not a strength test','Press-fit retention depends on measured plywood and kerf; optional small glue spots after dry assembly','Open model hull: no flotation/waterproof claim'])

def build():
 b=Yacht();b.open();b.render();raw=replace_profiles(b.close().getvalue(),b);validate_closed(raw,b)
 packed,layout=pack_sheet(raw,[(p['name'],) for p in b.specs],1500,3000,cluster_width=480);validate_closed(packed,b,True)
 assembly=validate_assembly(b,packed);shapes=local_shapes(packed,b);art=[]
 for n,p in b.art:
  s=shapes[n];q=path_poly(p).scaled(1,-1).translated(complex(s['ox'],s['oy']))
  require(s['outer'].contains(polygon(q)) and all(polygon(q).boundary.distance(h.boundary)>.3 for h in s['holes']),'Engrave intersects cut')
  art.append(dict(part=n,d=q.d()))
 final,bridges=add_bridges(packed,b.expected_parts);root=ET.fromstring(final)
 for a in art:ET.SubElement(root.find(NS+"g[@id='ENGRAVE']"),NS+'path',{'d':a['d'],'data-panel':a['part'],'stroke':'#000000','stroke-width':'.15','fill':'none'})
 for e in root.iter(NS+'path'):e.set('stroke','#000000')
 final=ET.tostring(root,encoding='utf-8',xml_declaration=True);geometry=validate_final(final,bridges,b)
 report=dict(status='STATIC_YACHT_PROTOTYPE_VALIDATED',parts=b.specs,features=b.features,planes=b.planes,bridges=bridges,engravings=art,geometry=geometry,layout=layout,assembly=assembly,components=b.catalog)
 return final,report,b

if __name__=='__main__':
 data,report,b=build();OUT.with_suffix('.svg').write_bytes(data);OUT.with_suffix('.validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'geometry':report['geometry'],'layout':report['layout'],'joints':report['assembly']['joint_count']},indent=2))
