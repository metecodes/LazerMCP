"""Depth-buffered assembly preview of the actual nominal solids, including slots."""
import numpy as np
import shapely
from shapely.geometry import Polygon
from PIL import Image,ImageDraw
from products.yacht.preview import shapes,arts,world,screen,dep,OUT,font,small,r
W,H=1400,1000
pixels=np.full((H,W,3),[250,249,246],dtype=np.uint8);depth=np.full((H,W),-np.inf)
def project(p):
 x,y,z=p;return np.array([130+3.3*(.9*x+.44*y),660+3.3*(.22*x-.45*y-.865*z),dep(p)])
def triangle(points,color):
 a,b,c=[project(p) for p in points];lo=np.maximum(np.floor(np.minimum(np.minimum(a,b),c)[:2]).astype(int),0);hi=np.minimum(np.ceil(np.maximum(np.maximum(a,b),c)[:2]).astype(int),[W-1,H-1])
 if np.any(hi<lo):return
 denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
 if abs(denom)<1e-9:return
 yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];xx=xx+.5;yy=yy+.5
 u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denom
 v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denom
 zz=u*a[2]+v*b[2]+(1-u-v)*c[2];target=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
 mask=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(zz>target)
 target[mask]=zz[mask];pixels[lo[1]:hi[1]+1,lo[0]:hi[0]+1][mask]=color
def line(pa,pb,color):
 a,b=project(pa),project(pb);n=max(2,int(np.linalg.norm(b[:2]-a[:2])*2));p=a+(b-a)*np.linspace(0,1,n)[:,None]
 xy=np.round(p[:,:2]).astype(int);ok=(xy[:,0]>=0)&(xy[:,0]<W)&(xy[:,1]>=0)&(xy[:,1]<H);p=p[ok];xy=xy[ok]
 ok=p[:,2]>=depth[xy[:,1],xy[:,0]]-.7;xy=xy[ok];pixels[xy[:,1],xy[:,0]]=color
edges=[]
for name,loops in shapes.items():
 q=Polygon(loops[0],loops[1:]);require=q.is_valid
 if not require:q=q.buffer(0)
 normal=r['planes'][name]['axes'][2];color=[232,215,179] if normal==2 else [213,185,144]
 for t in (0,3):
  for tri in shapely.constrained_delaunay_triangles(q).geoms:
   triangle([world(name,p,t) for p in list(tri.exterior.coords)[:3]],color)
 for loop in loops:
  for a,b in zip(loop,loop[1:]+[loop[0]]):
   pa,pb,pc,pd=world(name,a,0),world(name,b,0),world(name,b,3),world(name,a,3)
   triangle([pa,pb,pc],[111,89,62]);triangle([pa,pc,pd],[111,89,62]);edges.extend([(pa,pb),(pc,pd)])
for a,b in edges:line(a,b,[88,73,50])
for name,loops in arts.items():
 normal=r['planes'][name]['axes'][2];t=3.02 if [.38,-.78,.5][normal]>0 else -.02
 for loop in loops:
  for a,b in zip(loop,loop[1:]):line(world(name,a,t),world(name,b,t),[83,66,43])
im=Image.fromarray(pixels);d=ImageDraw.Draw(im)
d.text((30,25),'PAYAS STEM | YAT AHŞAP MAKET',font=font,fill='black')
d.text((30,65),'300 × 110 × 151 mm — gerçek kesim konturlarından montaj önizlemesi',font=small,fill='black')
d.text((30,910),'17 ahşap parça · 43 geçme · 3 mm kavak · statik masaüstü maket',font=font,fill='black')
d.text((30,950),'Önce bir adet kuru montaj denemesi yapılmalı. Yüzdürme / su geçirmezlik amacı taşımaz.',font=small,fill='black')
im.save(OUT.with_suffix('.assembly.png'))
