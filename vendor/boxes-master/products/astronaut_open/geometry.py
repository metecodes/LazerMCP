import math,json
from pathlib import Path
from shapely.geometry import Polygon,Point,LineString,box
from shapely.affinity import scale
from products.ressam_robot.generate import polygon,parse_path,require
from products.robot_bank.generate import local_shapes
ROOT=Path(__file__).resolve().parents[2]
def poly_path(p):return parse_path('M '+' L '.join(f'{x},{y}' for x,y in p.exterior.coords)+' Z')

def figure_shape():
 body=Polygon([(28,0),(84,0),(89,45),(105,41),(112,47),(110,64),(103,98),(90,112),(72,118),(40,118),(22,110),(10,98),(2,64),(0,47),(7,41),(23,45)])
 return body.union(Point(56,133).buffer(27,quad_segs=64))

def motion_check(b):
 pin=next(f for f in b.features if f['kind']=='crank-pin');r=pin['x']-22;require(pin['y']==22 and r==16,'Crank geometry changed')
 slot=next(f for f in b.features if f['kind']=='horizontal-slot');guides=[f for f in b.features if f['kind']=='vertical-guide']
 require((slot['x'],slot['y'],slot['w'],slot['h'])==(47,12,40,4.4),'Yoke slot changed')
 require(len(guides)==2 and all((g['w'],g['h'])==(4.4,44) for g in guides),'Guide slot changed')
 require(slot['w']/2-2-r>0 and min(g['h']/2-2-r for g in guides)>0,'Pin strikes slot end')
 positions=[]
 for i in range(1441):
  t=i*math.tau/1440;x=r*math.cos(t);dz=r*math.sin(t)
  require(abs(x)+2<20 and abs(dz)+2<22,'Pin/slot collision')
  positions.append([x,99+dz,57+dz,217+dz])
 # Depth layers separate moving figure, yoke and crank from stationary wall.
 layers={'figure':[-29.7,-26.7],'spacers':[-26.7,-20.7],'yoke':[-20.7,-17.7],'crank':[-8.5,-5.5],'hub':[-5.5,-.5],'front_wall':[0,3]}
 require(abs(layers['crank'][0]-layers['yoke'][1]-9.2)<1e-8,'Crank/yoke wood gap')
 require(layers['front_wall'][0]-layers['hub'][1]==.5,'Rotating hub rubs frame')
 require(57-r>6,'Astronaut hits base')
 return dict(type='Scotch yoke, constrained vertical translation',radius_mm=r,figure_stroke_mm=2*r,
  ideal_motion='Z_figure_bottom=57+16*sin(theta); X_crank_pin=16*cos(theta); Y_fixed',samples=1441,
  horizontal_slot_mm=[40,4.4],vertical_slots_mm=[4.4,44],pin_nominal_diameter_mm=4,
  lateral_slot_clearance_mm=.4,horizontal_end_margin_mm=2,vertical_end_margin_mm=4,
  minimum_figure_base_gap_mm=35,depth_layers_y_mm=layers,wood_gap_crank_yoke_mm=9.2,track=positions,
  caveat='Rigid nominal geometric check only. Pins must slide on smooth shafts; fasteners must not clamp guides or yoke. Physical motor/load testing required.')

def artwork(b,packed):
 shapes=local_shapes(packed,b);s=shapes['Astronaut'];paths=[]
 def poly(pts):return parse_path('M '+' L '.join(f'{x},{y}' for x,y in pts)+' Z')
 def ellipse(x,y,rx,ry):return poly([(x+rx*math.cos(i*math.tau/128),y+ry*math.sin(i*math.tau/128)) for i in range(128)])
 def stroke(pts):return poly_path(LineString(pts).buffer(.3,cap_style=1,join_style=1))
 paths +=[ellipse(56,133,20,22),ellipse(56,133,23,25)]
 # Suit seams and glove fingers, deliberately simple monochrome engraving.
 for sign in (-1,1):
  paths.append(stroke([(56+sign*23,105),(56+sign*31,87),(56+sign*32,65)]))
  for y in (55,61,67):paths.append(stroke([(56+sign*40,y),(56+sign*49,y+3)]))
 paths.append(poly([(43,73),(69,73),(69,89),(43,89)]))
 moon=scale(Point(53,81).buffer(1,quad_segs=48),4,5,origin=(53,81)).difference(scale(Point(55,82).buffer(1,quad_segs=48),3.3,4,origin=(55,82)))
 paths.append(poly_path(moon))
 star=[(62+(3 if i%2==0 else 1.3)*math.cos(math.pi/2+i*math.pi/5),81+(3 if i%2==0 else 1.3)*math.sin(math.pi/2+i*math.pi/5)) for i in range(10)]
 paths.append(poly(star))
 logo=json.loads((ROOT/'assets/payas/logo-school.contours.json').read_text());sc=34/logo['width']
 for ring in logo['rings']:
  # Existing asset contours use Y-up, unlike source bitmap pixels.
  shape=Polygon([(39+x*sc,9+y*sc) for x,y in ring]).buffer(0)
  for q in (list(shape.geoms) if hasattr(shape,'geoms') else [shape]):
   if q.area>.001:paths.append(poly_path(q))
 out=[]
 for p in paths:
  q=p.scaled(1,-1).translated(complex(s['ox'],s['oy']));shape=polygon(q)
  require(s['outer'].contains(shape),'Engraving outside figure')
  require(all(shape.boundary.distance(h.boundary)>.3 for h in s['holes']),'Engraving hits figure hole')
  out.append(dict(part='Astronaut',d=q.d()))
 return out
