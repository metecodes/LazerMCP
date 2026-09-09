"""Use the repository's raster triangle kernel to preview the new actual contours."""
from pathlib import Path
import sys,json,ast
import numpy as np
import shapely
from shapely.geometry import Polygon
from PIL import Image,ImageDraw,ImageFont
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from products.astronaut_open.generate import OUT
from products.ressam_robot.generate import NS,parse_path,polygon,Line
r=json.loads(OUT.with_suffix('.validation.json').read_text());root=ET.parse(OUT.with_suffix('.svg')).getroot()
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
def pts(p):return [s.point(i/(1 if isinstance(s,Line) else 24)) for s in p for i in range((1 if isinstance(s,Line) else 24)+1)]
shapes={};arts={}
for spec,rec,g in zip(r['parts'],r['bridges'],root.find(NS+"g[@id='CUT']")):
 p=parse_path(rec['closed_design']);a,b,c,d=p.bbox();ox=a+.075;oy=d-.075
 loops=[p]+[parse_path(e.get('d')) for e in g if not e.get('data-holding-bridges')]
 shapes[spec['name']]=[[(z.real-ox,oy-z.imag) for z in pts(q)] for q in loops]
 arts[spec['name']]=[[(z.real-ox,oy-z.imag) for z in pts(parse_path(a['d']))] for a in r['engravings'] if a['part']==spec['name']]
im=Image.new('RGB',(1450,1300),'white');dr=ImageDraw.Draw(im)
dr.text((30,20),'PAYAS STEM | ASTRONOT AÇIK ŞASE — KESİM YERLEŞİMİ',font=font,fill='black')
dr.text((30,60),'15 parça / 26 geçme / 30 tutucu köprü / 3 mm kavak / 0,15 mm kerf',font=small,fill='black')
dr.text((30,90),'1500 × 3000 mm levhada sol üstte 403,60 × 330,30 mm alan',font=small,fill='black')
for e in root.iter(NS+'path'):
 for sub in parse_path(e.get('d')).continuous_subpaths():dr.line([(30+(z.real-10)*3.4,130+(z.imag-10)*3.4) for z in pts(sub)],fill='black',width=1)
for i,rec in enumerate(r['bridges'],1):
 q=polygon(parse_path(rec['closed_design'])).representative_point();dr.text((30+(q.x-10)*3.4,130+(q.y-10)*3.4),str(i),font=small,fill='#777777')
dr.text((30,1260),'Parça numaraları yalnızca önizlemede; üretim SVG dosyasında kesilmez.',font=small,fill='black')
im.save(OUT.with_suffix('.layout.png'))
def world(n,p,t=0):
 pl=r['planes'][n];v=pl['origin'].copy()
 for k,value in zip(pl['axes'],(*p,t)):v[k]+=value
 return v
W,H=1600,1000
pixels=np.full((H,W,3),[250,249,246],dtype=np.uint8);depth=np.full((H,W),-np.inf)
offset=420
def dep(p):return .516*p[0]-.688*p[1]+.5*p[2]
def project(p):
 x,y,z=p;return np.array([offset+3.4*(.8*x+.6*y),835+3.4*(.3*x-.4*y-.86*z),dep(p)])
# Reuse only the pure raster kernels; importing the yacht preview would regenerate its files.
source=ast.parse((ROOT/'products/yacht/render_solid.py').read_text(encoding='utf-8'))
kernel=ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('triangle','line')],type_ignores=[])
exec(compile(kernel,'yacht_raster_kernel','exec'))
for opened in (False,True):
 offset=420 if not opened else 1160;edges=[]
 for n,loops in shapes.items():
  if opened and n=='Astronaut':continue
  q=Polygon(loops[0],loops[1:]);require=q.is_valid
  if not require:q=q.buffer(0)
  color=[228,207,169] if r['planes'][n]['axes'][2]==2 else [217,188,145]
  for t in (0,3):
   for tri in shapely.constrained_delaunay_triangles(q).geoms:triangle([world(n,p,t) for p in list(tri.exterior.coords)[:3]],color)
  for loop in loops:
   for a,b in zip(loop,loop[1:]+[loop[0]]):
    pa,pb,pc,pd=world(n,a,0),world(n,b,0),world(n,b,3),world(n,a,3)
    triangle([pa,pb,pc],[105,84,58]);triangle([pa,pc,pd],[105,84,58]);edges.extend([(pa,pb),(pc,pd)])
 for a,b in edges:line(a,b,[85,68,46])
 if not opened:
  for n,loops in arts.items():
   t=-.02 if [.516,-.688,.5][r['planes'][n]['axes'][2]]<0 else 3.02
   for loop in loops:
    for a,b in zip(loop,loop[1:]):line(world(n,a,t),world(n,b,t),[55,46,32])
im=Image.fromarray(pixels);dr=ImageDraw.Draw(im)
dr.text((30,25),'PAYAS STEM | YENİ ASTRONOT — AÇIK ŞASE V1',font=font,fill='black')
dr.text((30,65),'Gerçek kesim geometrisinden önizleme / sabit taban üzerinde 32 mm düşey hareket',font=small,fill='black')
dr.text((240,110),'MONTAJLI GÖRÜNÜM',font=font,fill='black');dr.text((925,110),'FİGÜR ÇIKARILMIŞ GÖRÜNÜM',font=font,fill='black')
dr.text((30,935),'Motor, pil ve metal bağlantılar bu görselde çizilmedi; ölçüleri parça listesinde tanımlıdır.',font=small,fill='black')
dr.text((30,970),'Önce bir adet prototip: motor havşaları, kuru montaj ve gerçek hareket testi gerekir.',font=small,fill='black')
im.save(OUT.with_suffix('.assembly.png'))
