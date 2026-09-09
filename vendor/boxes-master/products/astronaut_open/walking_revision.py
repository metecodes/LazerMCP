"""Walking revision: dimensioned review drawing, never a fabrication export."""
import sys, math, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from products.astronaut_open.geometry import figure_shape

OUT=ROOT/'output'
CONFIG=dict(material_mm=3,kerf_mm=.15,sheet_mm=[1500,3000],
    radius_mm=8,foot_mm=[32,90],foot_centres_x_mm=[-42,42],
    proposed_body_mm=[106,60],phase_degrees=180,
    stationary_base=False,mode='forward_shuffling',
    export_svg=False)

def simulate(directional=True):
    # Quasistatic idealization: backwards slip is forbidden, forward slip is free.
    # This is a proposed contact law, NOT measured friction or a dynamics solver.
    r=CONFIG['radius_mm']; body=0.; previous=r; rows=[]
    for i in range(1441):
        t=math.tau*i/1440;s=r*math.cos(t)
        body += abs(s-previous) if directional else 0
        rows.append([i/4,body,s,-s,body+s,body-s])
        previous=s
    return rows

def build():
    ideal=simulate(); symmetric=simulate(False)
    assert abs(ideal[-1][1]-32)<1e-8
    assert symmetric[-1][1]==0
    assert all(abs(p[2]+p[3])<1e-10 for p in ideal)
    assert all(ideal[i][j]>=ideal[i-1][j]-1e-8 for i in range(1,len(ideal)) for j in (4,5))
    foot_gap=84-32
    assert foot_gap>0
    report=dict(status='REVIEW_ONLY_ASSEMBLY_UNRESOLVED',parameters=CONFIG,
        samples=1441,foot_stroke_mm=16,foot_to_foot_lateral_gap_mm=foot_gap,
        ideal_one_way_contact_advance_mm_per_turn=ideal[-1][1],
        symmetric_contact_counterexample_advance_mm=0,
        note='32 mm is an ideal one-way-contact result; not a predicted measured walking distance.',
        unresolved=['Directional sole material, contact law and attachment',
                    'Secondary shaft, bearings and motor transmission',
                    'Slider anti-rotation and mechanical retention',
                    'Motor torque under load and centre of mass',
                    'Full assembly swept collision and tab-slot validation'],
        fabrication_export_allowed=False,track_columns=['degrees','body_y','left_relative_y','right_relative_y','left_world_y','right_world_y'],track=ideal)
    (OUT/'Payas_STEM_Astronot_Yuruyen_V2.review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    im=Image.new('RGB',(1600,1150),'white');d=ImageDraw.Draw(im)
    def txt(x,y,s,n=23):d.text((x,y),s,fill='black',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n))
    txt(45,22,'ASTRONOT V2 | İLERİ KAYARAK YÜRÜME',36)
    txt(45,76,'Ölçülü mekanizma incelemesi • Siyah-beyaz • Üretim geometrisi değildir',24)
    txt(65,137,'ÖN GÖRÜNÜŞ',26)
    shape=figure_shape()
    pts=[(270+(x-56)*2.2,535-y*2.2) for x,y in shape.exterior.coords]
    d.polygon(pts,outline='black',width=4)
    d.ellipse((224,203,312,294),outline='black',width=2)
    for x in (-42,42):
        d.rectangle((270+(x-16)*2.2,550,270+(x+16)*2.2,580),outline='black',width=4)
        d.line((270+x*2.2,490,270+x*2.2,550),fill='black',width=4)
    txt(83,601,'İki ayrı ayak; sabit H taban yok',22)
    txt(590,137,'ÜST GÖRÜNÜŞ / ORTA KONUM',26)
    sc=2.5;cx=800;cy=374
    d.rectangle((cx-53*sc,cy-30*sc,cx+53*sc,cy+30*sc),outline='gray',width=3)
    for x in (-42,42):
        d.rectangle((cx+(x-16)*sc,cy-45*sc,cx+(x+16)*sc,cy+45*sc),outline='black',width=4)
        d.line((cx+x*sc,cy-53*sc,cx+x*sc,cy+53*sc),fill='gray',width=2)
    d.line((cx,240,cx,190),fill='black',width=4)
    d.polygon([(cx,181),(cx-9,199),(cx+9,199)],fill='black')
    txt(850,185,'İLERİ',22)
    txt(632,521,'Ayak: 32 × 90 mm (öneri)',23)
    txt(632,559,'Merkez aralığı: 84 mm',23)
    txt(632,597,'Her ayak: ±8 mm kayma',23)
    txt(1110,137,'BİR TUR / İDEAL TEMAS',25)
    txt(1100,191,'Açı     Gövde     Sol / Sağ*',22)
    for k,i in enumerate((0,360,720,1080,1440)):
        p=ideal[i]
        txt(1110,241+k*51,f'{p[0]:.0f}°      {p[1]:.0f} mm      {p[2]:+.0f} / {p[3]:+.0f}',21)
    txt(1100,520,'* Gövdeye göre, mm',21)
    txt(1100,562,'32 mm/tur: yalnızca ideal',21)
    txt(1100,594,'tek yönlü tutunma halinde.',21)
    txt(50,686,'MOTOR → AKTARMA MİLİ → 180° FAZLI KRANKLAR → KIZAKLAR → AYAKLAR',25)
    txt(50,741,'1. Sol ayak zemine tutunur; gövde ilerlerken sağ ayak öne kayar.',24)
    txt(50,784,'2. Sağ ayak tutunur; sonraki yarım turda sol ayak öne kayar.',24)
    txt(50,841,'GEREKLİ: Öne kayabilen, geriye tutunan taban. Malzemesi ve bağlantısı henüz çözülmedi.',23)
    txt(50,889,'Düz, simetrik sürtünmeli ahşap tabanda bu krank hareketi tek başına yürümeyi kanıtlamaz.',23)
    txt(50,947,'Mil/yataklama, kızaklar ve montaj çarpışmaları tamamlanmadan SVG ihracı kapalı.',23)
    txt(50,1030,'KESİME HAZIR DEĞİL • Fiziksel yürüme testi gerekiyor',30)
    im.save(OUT/'Payas_STEM_Astronot_Yuruyen_V2.png')
    return report

if __name__=='__main__':
    r=build(); print(json.dumps({k:v for k,v in r.items() if k!='track'},ensure_ascii=False,indent=2))
