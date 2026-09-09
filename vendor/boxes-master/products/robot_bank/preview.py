"""Show the actual validated parts, not an image-generated assembly."""
from pathlib import Path
import json,math,sys
from xml.etree import ElementTree as ET
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from products.ressam_robot.generate import parse_path,polygon,NS,Line
from products.robot_bank.orientation import plane,OUTSIDE_NORMALS
ROOT=Path(__file__).resolve().parents[2]
electronic='--electronics' in sys.argv
OUT=ROOT/('output/Payas_STEM_Robot_Kumbara_ELEKTRONIK_REV2' if electronic else 'output/Payas_STEM_Robot_Kumbara_YON_REV1')
report=json.loads(OUT.with_suffix('.validation.json').read_text());root=ET.parse(OUT.with_suffix('.svg')).getroot()
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',21);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
def points(path):return [s.point(i/(1 if isinstance(s,Line) else 24)) for s in path for i in range((1 if isinstance(s,Line) else 24)+1)]
shapes={};arts={}
for i,(spec,rec,group) in enumerate(zip(report['parts'],report['bridges'],root.find(NS+"g[@id='CUT']")),1):
 p=parse_path(rec['closed_design']);x0,x1,y0,y1=p.bbox();es=spec['edges']
 ox=x0+.075+(3 if es[3] in 'fF' else 0);oy=y1-.075-(3 if es[0] in 'fFT' else 0)
 loops=[p]+[parse_path(e.get('d')) for e in group if not e.get('data-holding-bridges')]
 shapes[spec['name']]=[[(z.real-ox,oy-z.imag) for z in points(q)] for q in loops]
 arts[spec['name']]=[[(z.real-ox,oy-z.imag) for z in points(parse_path(a['d']))] for a in report['engravings'] if a['part']==spec['name']]
im=Image.new('RGB',(1480,1500 if electronic else 1400),'white');dr=ImageDraw.Draw(im)
dr.text((30,20),'PAYAS STEM | ROBOT KUMBARA — KESİM YERLEŞİMİ',font=font,fill='black')
dr.text((30,54),f"{len(report['parts'])} parça / {len(report['parts'])*2} tutucu köprü / 3 mm / 0.15 mm kerf / 1500 × 3000 mm levha",font=small,fill='black')
for e in root.iter(NS+'path'):
 for sub in parse_path(e.get('d')).continuous_subpaths():
  dr.line([(25+(z.real-10)*3.6,105+(z.imag-10)*3.6) for z in points(sub)],fill='black',width=1)
for i,rec in enumerate(report['bridges'],1):
 c=polygon(parse_path(rec['closed_design'])).representative_point();dr.text((25+(c.x-10)*3.6,105+(c.y-10)*3.6),str(i),font=small,fill='#666666')
dr.text((30,1450 if electronic else 1350),'Numaralar yalnızca önizlemede. CUT ve ENGRAVE katmanlarını ayrı işlem olarak ayarlayın.',font=small,fill='black')
im.save(OUT.with_suffix('.layout.png'))
def render(front=True,opened=False):
 im=Image.new('RGB',(1250,1120),'#faf9f6');dr=ImageDraw.Draw(im)
 dr.text((35,25),'ROBOT KUMBARA | '+('İÇ YERLEŞİM / ÖN VE ÜST PANELLER ÇIKARILMIŞ' if opened else 'ÖN / SAĞ' if front else 'ARKA / SOL'),font=font,fill='#222222')
 dr.text((35,60),'Gerçek kesim konturlarından montaj önizlemesi — '+('elektronik montaj prototipi' if electronic else 'pasif mekanik prototip'),font=small,fill='#444444')
 def orient(p):
  x,y,z=p
  return (x,y,z) if front else (120-x,85-y,z)
 def screen(p):
  x,y,z=orient(p);return (180+4.4*(.8*x+.6*y),880+4.4*(.3*x-.4*y-.86*z))
 def depth(p):
  x,y,z=orient(p);return .516*x-.688*y+.5*z
 entries=[]
 for name,loops in shapes.items():
  if opened and name in ('Bank Front','Bank Top'):continue
  loop3=[[plane(name,*p) for p in loop] for loop in loops]
  n=OUTSIDE_NORMALS.get(name)
  camera=(.516,-.688,.5) if front else (-.516,.688,.5)
  visible=n is None or sum(a*b for a,b in zip(n,camera))>0
  if name.startswith('Bank ') and not visible and not opened:continue
  if name=='Rear Cover' and front:continue
  # Rear overlay must draw over its supporting wall despite their different heights.
  order=10000 if name=='Rear Cover' else sum(depth(p) for p in loop3[0])/len(loop3[0])
  entries.append((order,name,loop3,visible))
 for _,name,loops,visible in sorted(entries):
  face='#e8cfaa' if name in ('Bank Front','Bank Back','Rear Cover') else '#d7b88a'
  dr.polygon([screen(p) for p in loops[0]],fill=face,outline='#57452e',width=2)
  for loop in loops[1:]:dr.polygon([screen(p) for p in loop],fill='#514838',outline='#3c3429')
  if visible:
   for loop in arts[name]:dr.line([screen(plane(name,*p)) for p in loop],fill='#332b20',width=2)
 if opened:
  x0,y0,z0,x1,y1,z1=report['electronic_assembly']['battery_envelope_xyz_mm']
  for face in [[(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)],[(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)],[(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]]:
   dr.polygon([screen(p) for p in face],fill='#555555',outline='#111111')
  dr.text(screen((x0+10,y0,z0+28)),'3×AA',font=font,fill='white')
  dr.text((45,930),'16: Ayırıcı panel     17: Pil rafı     Gri kutu: doğrulanan pil yuvası dış zarfı',font=small,fill='#333333')
  dr.text((45,958),'Kablo, bağ ve sensör ayrıntıları bu görünümde temsil edilmiyor.',font=small,fill='#333333')
 dr.text((35,1040),'Gövde 120 × 85 × 148 mm; ayaklarla yükseklik 160 mm.',font=font,fill='#222222')
 dr.text((35,1080),'LED/şalter kesitleri mevcut; gerçek elektronik montaj ve para sensörü doğrulanmadı.' if electronic else 'Göz ve kalp kazımadır. Elektronik işlev bu sürümde yoktur. Donanım ve gerçek geçmeler test gerektirir.',font=small,fill='#444444')
 return im
render(True).save(OUT.with_suffix('.assembly.png'));render(False).save(OUT.with_suffix('.rear.png'))
if electronic:render(True,True).save(OUT.with_suffix('.interior.png'))
# Outside-face reading guide, without isometric perspective or backside projection.
guide=Image.new('RGB',(1200,600),'white');gd=ImageDraw.Draw(guide)
gd.text((25,20),'DIŞ YÜZ YÖNLERİ — KAZIMALI YÜZ DIŞARI BAKACAK',font=font,fill='black')
for name,title,xx in [('Bank Front','ÖN',35),('Bank Back','ARKA',355),('Bank Left','SOL',675),('Bank Right','SAĞ',925)]:
 gd.text((xx,65),title,font=font,fill='black')
 def point(p):return(xx+2.3*p[0],450-2.3*p[1])
 gd.polygon([point(p) for p in shapes[name][0]],fill='#faf6ed',outline='black')
 for hole in shapes[name][1:]:gd.polygon([point(p) for p in hole],fill='#cccccc',outline='black')
 for loop in arts[name]:gd.line([point(p) for p in loop],fill='black',width=1)
 if name=='Bank Back':
  def door(p):return point((17+p[0],4+p[1]))
  gd.polygon([door(p) for p in shapes['Rear Cover'][0]],fill='#faf6ed',outline='black')
  for loop in arts['Rear Cover']:gd.line([door(p) for p in loop],fill='black',width=1)
gd.text((25,520),'Sol panel ve sol kolun delik yönleri düzeltildi; sağ parçalarla karıştırmayın.',font=small,fill='black')
gd.text((25,552),'Üst yazı önden okunur; üst yüzeye arkadan bakınca baş aşağı görünmesi normaldir.',font=small,fill='black')
guide.save(OUT.with_suffix('.directions.png'))
print(OUT)
