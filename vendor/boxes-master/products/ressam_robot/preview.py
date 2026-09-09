"""Preview actual validated paths; no image-generation or fabrication substitutions."""
import json
import math
import sys
from pathlib import Path as FilePath
from xml.etree import ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from generate import ROOT, NS, polygon, parse_path, Line, RessamRobot, validate_final

revision='--reference' in sys.argv
OUT=ROOT/("output/Payas_STEM_Ressam_Robot_REFERENCE_REV1" if revision else "output/Payas_STEM_Ressam_Robot_PROTOTYPE")
report=json.loads(OUT.with_suffix(".validation.json").read_text())
data=OUT.with_suffix(".svg").read_bytes()
if revision:
    from reference_revision import ReferenceRobot
    robot=ReferenceRobot()
else:robot=RessamRobot()
validate_final(data,report["bridges"],robot)
root=ET.fromstring(data)
font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",23)
small=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",17)


def points(path):
    result=[]
    for s in path:
        n=1 if isinstance(s,Line) else 32
        result.extend(s.point(i/n) for i in range(n+1))
    return result


canvas=Image.new("RGB",(1400,1560),"#f6f3ed")
draw=ImageDraw.Draw(canvas)
draw.text((30,20),"PAYAS STEM | DENE YAP - RESSAM ROBOT",font=font,fill="#18404a")
draw.text((30,55),f"1500 x 3000 mm levha | {report['layout']['occupied_mm']} mm kompakt alan",font=font,fill="#18404a")
draw.text((30,90),f"{len(robot.specs)} parca / {len(robot.specs)*2} tutucu kopru / CUT: siyah - ENGRAVE: yesil",font=small,fill="#745831")
scale=3.65
for p in root.iter(NS+"path"):
    path=parse_path(p.get("d"))
    color="#16785c" if p.get("stroke")=="rgb(0,255,0)" else "#222222"
    for sub in path.continuous_subpaths():
        draw.line([(30+(q.real-10)*scale,145+(q.imag-10)*scale) for q in points(sub)],fill=color,width=2)
for i,record in enumerate(report["bridges"]):
    shape=polygon(parse_path(record["closed_design"]))
    c=shape.representative_point()
    draw.text((30+(c.x-10)*scale,145+(c.y-10)*scale),str(i+1),font=small,fill="#9c6c29")
draw.text((30,1515),"Numaralar sadece onizlemededir. Kopru araliklarini yazilimda otomatik kapatmayin.",font=small,fill="#745831")
canvas.save(OUT.with_suffix(".layout.png"))


# Assemble the actual outline polygons into their stated installation planes.
groups=root.find(NS+"g[@id='CUT']").findall(NS+"g")
shapes={}
for spec,group,record in zip(robot.specs,groups,report["bridges"]):
    outer=polygon(parse_path(record["closed_design"]))
    x0,y0,x1,y1=outer.bounds
    if spec["disc"]:
        ox,oy=(x0+x1)/2,(y0+y1)/2
    else:
        ox=x0+(.075)+(3 if spec["edges"][3] in "fF" else 0)
        oy=y1-(.075)-(3 if spec["edges"][0] in "fFT" else 0)
    all_shapes=[outer]+[polygon(parse_path(p.get("d"))) for p in group.findall(NS+"path") if not p.get("data-holding-bridges")]
    shapes[spec["name"]]=[[(x-ox,oy-y) for x,y in poly.exterior.coords] for poly in all_shapes]


angle=math.radians(225)
A=complex(18+12*math.cos(angle),15+12*math.sin(angle));O=complex(112,15)
delta=O-A;length=abs(delta);along=(84**2-30**2+length**2)/(2*length)
B=A+delta/length*complex(along,-math.sqrt(84**2-along**2))
u=(B-A)/84;v=(B-O)/30


def plane(name,x,y):
    if ' Foot ' in name:
        base=0 if name.startswith('Left') else 94
        suffix=name.split()[-1]
        if suffix=='Front':return (base+3+x,0,3+y)
        if suffix=='Back':return (base+3+x,95,3+y)
        if suffix=='Outer':return (base,3+x,3+y)
        if suffix=='Inner':return (base+36,3+x,3+y)
        return(base+3+x,3+y,40 if suffix=='Top' else 0)
    if name.startswith('Head '):
        suffix=name.split()[-1]
        if suffix in ('Front','Back'):return(13+x,60 if suffix=='Front' else 95,40+y)
        if suffix in ('Left','Right'):return(10 if suffix=='Left' else 120,63+x,40+y)
        return(13+x,63+y,144 if revision else 160)
    if name=='Rounded Face':return(5+x,57,40+y)
    if name.startswith('Eye '):return(41+x if name=='Eye Left' else 89+x,54 if revision else 57,(116 if revision else 128)+y)
    if name=='Crank':return(18+x,15+y,46)
    if name=='Rocker':p=O+v*complex(x-6,y-6);return(p.real,p.imag,46)
    if name=='Pen Beam':p=A+u*complex(x-6,y-18);return(p.real,p.imag,54)
    if name=='Pen Saddle':p=A+u*complex(x+22,-13);return(p.real,p.imag,57+y)


def screen(p):
    x,y,z=p
    return(160+4.8*(.8*x+.6*y),940+4.8*(.3*x-.4*y-.86*z))


def depth(p):return .516*p[0]-.688*p[1]+.5*p[2]


canvas=Image.new('RGB',(1250,1300),'#f6f3ed');draw=ImageDraw.Draw(canvas)
draw.text((30,20),'PAYAS STEM | RESSAM ROBOT',font=font,fill='#18404a')
draw.text((30,55),'Gercek parca konturlarindan montaj onizlemesi',font=small,fill='#745831')
paper=[screen(p) for p in [(20,-48,0),(90,-48,0),(90,-2,0),(20,-2,0)]]
draw.polygon(paper,fill='white',outline='#bbc1c3')
draw.line([screen((x,y,0)) for x,y in report['motion']['track']],fill='#3973bb',width=3)
panels=[]
for name,loops in shapes.items():
    loops3=[[plane(name,x,y) for x,y in loop] for loop in loops]
    panels.append((10000 if name.startswith('Eye') else 9000 if name=='Rounded Face' else sum(depth(p) for p in loops3[0])/len(loops3[0]),name,loops3))
for _,name,loops in sorted(panels):
    fill='#eacb94' if 'Front' in name or 'Eye' in name else '#ceaa75'
    if name=='Pen Beam':fill='#e3b66c'
    draw.polygon([screen(p) for p in loops[0]],fill=fill,outline='#694a29',width=2)
    for hole in loops[1:]:draw.polygon([screen(p) for p in hole],fill='#75604a',outline='#634625')
    if name.startswith('Eye'):
        def ring(radius):return [screen(plane(name,radius*math.cos(t),radius*math.sin(t))) for t in [math.tau*i/64 for i in range(65)]]
        draw.polygon(ring(16 if revision else 11),fill='#f5eee0',outline='#694a29')
        draw.polygon(ring(9 if revision else 6),fill='#2c3035')
        hi=[screen(plane(name,-2+1.4*math.cos(t),3+1.4*math.sin(t))) for t in [math.tau*i/32 for i in range(33)]]
        draw.polygon(hi,fill='white')
    if name==('Rounded Face' if revision else 'Head Front'):
        smile=[screen(plane(name,(60 if revision else 52)+11*math.cos(t),(51 if revision else 61)-11*math.sin(t))) for t in [math.pi*i/40 for i in range(41)]]
        draw.line(smile,fill='#634625',width=3)
pen=(A+B)/2+u*complex(0,-20.5)
draw.line([screen((pen.real,pen.imag,3)),screen((pen.real,pen.imag,125))],fill='#ddae26',width=20)
draw.line([screen((pen.real,pen.imag,108)),screen((pen.real,pen.imag,129))],fill='#333d43',width=20)
draw.line([screen((pen.real,pen.imag,0)),screen((pen.real,pen.imag,8))],fill='#253245',width=5)
draw.text((35,1200),'1 motor -> krank -> yatay kol -> 1 kalem',font=font,fill='#18404a')
draw.text((35,1240),f'{149 if revision else 160} mm ahsap yuksekligi. Renkler ve kalem temsilidir; fiziksel prototip testi gerekir.',font=small,fill='#745831')
canvas.save(OUT.with_suffix('.assembly.png'))
