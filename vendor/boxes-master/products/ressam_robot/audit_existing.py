"""Read-only audit of the existing export. Writes only a separate audit directory."""
from pathlib import Path
import sys,json,hashlib,math
import numpy as np
from scipy.optimize import minimize_scalar
from shapely.geometry import Polygon,LineString,Point,box
from svgpathtools import parse_path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from products.ressam_robot.generate import polygon, RessamRobot, validate_final
OUT=ROOT/'output/ressam_robot_audit';OUT.mkdir(exist_ok=True)
svg=ROOT/'output/Payas_STEM_Ressam_Robot_PROTOTYPE.svg'
data=svg.read_bytes(); sha=hashlib.sha256(data).hexdigest()
d=json.loads(svg.with_suffix('.validation.json').read_text())
result={'input_sha256':sha,'existing_validator':validate_final(data,d['bridges'],RessamRobot()),'profiles':[]}
profiles={}
for i,(spec,rec) in enumerate(zip(d['parts'],d['bridges']),1):
 p=parse_path(rec['closed_design']); xmin,xmax,ymin,ymax=p.bbox()
 if spec['disc']:continue
 es=spec['edges'];ox=xmin+.075+(3 if es[3] in 'fF' else 0);oy=ymax-.075-(3 if es[0] in 'fFT' else 0)
 raw=polygon(p)
 poly=Polygon([(x-ox,oy-y) for x,y in raw.exterior.coords])
 for e,c in enumerate(es):
  if c not in 'fF':continue
  w,h=spec['w'],spec['h']; L=w if e%2==0 else h
  lines=[[(0,-1.5),(w,-1.5)],[(w+1.5,0),(w+1.5,h)],[(0,h+1.5),(w,h+1.5)],[(-1.5,0),(-1.5,h)]]
  line=LineString(lines[e]); seg=poly.intersection(line) if c=='f' else line.difference(poly)
  geoms=list(seg.geoms) if hasattr(seg,'geoms') else [seg]
  intervals=sorted([(min(q.coords[0][e%2],q.coords[-1][e%2]),max(q.coords[0][e%2],q.coords[-1][e%2])) for q in geoms if q.length>1e-6])
  profiles[i,e]=intervals
  result['profiles'].append({'part':i,'edge':e,'type':c,'intervals_mm':intervals})
pairs=[]
for n in (0,6):
 pairs += [(3+n,3,1+n,3),(3+n,1,2+n,3),(4+n,3,1+n,1),(4+n,1,2+n,1)]
 for male,fe in ((5+n,2),(6+n,0)):
  pairs += [(male,0,1+n,fe),(male,2,2+n,fe),(male,3,3+n,fe),(male,1,4+n,fe)]
pairs += [(15,3,13,3),(15,1,14,3),(16,3,13,1),(16,1,14,1),(17,0,13,2),(17,2,14,2),(17,3,15,2),(17,1,16,2)]
result['finger_pairs']=[]
for a,ae,b,be in pairs:
 m,s=profiles[a,ae],profiles[b,be]
 ok=len(m)==len(s) and all(abs((v-u)-6.15)<.002 and abs((y-x)-5.85)<.002 and abs((u+v)-(x+y))<.002 for (u,v),(x,y) in zip(m,s))
 result['finger_pairs'].append(dict(male=a,male_edge=ae,female=b,female_edge=be,count=len(m),compatible=ok))
 assert ok,(a,b,m,s)
def state(t):
 A=18+15j+12*np.exp(1j*t);delta=112+15j-A;dist=abs(delta)
 along=(84**2-30**2+dist**2)/(2*dist)
 B=A+delta/dist*(along-1j*np.sqrt(84**2-along**2));u=(B-A)/84
 return A,B,u
grid=np.linspace(0,2*np.pi,36001)
def extrema(f):
 vals=f(grid);out=[]
 for sign in (1,-1):
  ix=np.argmin(sign*vals);t=grid[ix];step=grid[1]
  opt=minimize_scalar(lambda q:sign*float(f(q)),bounds=(t-step,t+step),method='bounded',options={'xatol':1e-13})
  out.append(float(f(opt.x)))
 return out+[out[1]-out[0]]
def point(t,x,y):
 A,B,u=state(t);return A+u*((x-6)+1j*(y-18))
result['motion']={}
for name,x,y in [('A',6,18),('B',90,18),('pivot_midpoint',48,18),('rectangle_center',48,12),('saddle_center',48,5),('pen_d8',48,-.5),('pen_d14',48,-3.5)]:
 result['motion'][name]={'x_min_max_stroke':extrema(lambda t:point(t,x,y).real),'y_min_max_stroke':extrema(lambda t:point(t,x,y).imag)}
result['motion']['beam_angle_degrees']=extrema(lambda t:np.angle(state(t)[2])*180/np.pi)
vertices=[(0,0),(38,0),(38,8),(58,8),(58,0),(96,0),(96,24),(0,24)]
vertexranges=[(extrema(lambda t:point(t,x,y).real),extrema(lambda t:point(t,x,y).imag)) for x,y in vertices]
result['motion']['beam_max_point_stroke_xy']=[max(v[c][2] for v in vertexranges) for c in (0,1)]
result['motion']['beam_swept_bbox']=[min(v[0][0] for v in vertexranges),min(v[1][0] for v in vertexranges),max(v[0][1] for v in vertexranges),max(v[1][1] for v in vertexranges)]
gaps={'crank_rocker':999.,'moving_head':999.,'pen_feet':999.,'pen_links':999.}
feet=[box(0,0,36,95),box(94,0,130,95)]
crank=Point(18,15).buffer(18,quad_segs=128)
for t in np.linspace(0,2*np.pi,7201):
 A,B,u=state(t);v=(B-(112+15j))/30
 def shape(coords,origin,unit):
  pts=[origin+unit*complex(x,y) for x,y in coords];return Polygon([(z.real,z.imag) for z in pts])
 rocker=shape([(-6,-6),(36,-6),(36,6),(-6,6)],112+15j,v)
 beam=shape([(x-6,y-18) for x,y in vertices],A,u)
 saddle=shape([(22,-14.5),(62,-14.5),(62,-11.5),(22,-11.5)],A,u)
 gaps['crank_rocker']=min(gaps['crank_rocker'],crank.distance(rocker))
 gaps['moving_head']=min(gaps['moving_head'],60-max(p.bounds[3] for p in (crank,rocker,beam,saddle)))
 for r in (4,7):
  z=(A+B)/2-u*1j*(14.5+r);pen=Point(z.real,z.imag).buffer(r,quad_segs=64)
  gaps['pen_feet']=min(gaps['pen_feet'],*(pen.distance(f) for f in feet))
  gaps['pen_links']=min(gaps['pen_links'],*(pen.distance(p) for p in (crank,rocker,beam)))
result['collision']={'samples':7201,'step_degrees':.05,'nominal_minimum_gaps_mm':gaps,'beam_lower_link_vertical_gap_mm':5,'scope':'Nominal rigid wood and assumed 8/14 mm cylindrical pens; hardware and deformation unresolved. Finite angular sampling is not an exact continuous collision proof.'}
result['svg_unchanged']=sha==hashlib.sha256(svg.read_bytes()).hexdigest()
(OUT/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('profiles','finger_pairs')},indent=2))
