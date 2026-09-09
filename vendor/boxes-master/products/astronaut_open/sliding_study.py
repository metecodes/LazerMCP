"""Non-fabrication motion study. Does not export SVG or certify assembly."""
import math, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output'
R = 8.0
track = []
for i in range(1441):
    theta = math.tau*i/1440
    left, right = R*math.cos(theta), -R*math.cos(theta)
    assert abs(left + right) < 1e-9
    track.append([i/4, left, right])
assert max(p[1] for p in track)-min(p[1] for p in track) == 16
report = dict(status='KINEMATIC_STUDY_ONLY_NOT_FOR_CUTTING',
    requirement='Stationary body; two feet slide fore/aft in opposite phase',
    proposed_crank_radius_mm=R, proposed_each_foot_stroke_mm=16,
    phase_difference_degrees=180, samples=len(track), track=track,
    transmission='Motor -> opposed crank pins -> two slotted followers -> guided sliding feet',
    unresolved=['Cross-shaft bearings and coupling', 'Follower depth layers and supports',
                'Guide friction and anti-rotation', 'Full swept solid collisions',
                'Tab-slot geometry and holding bridges', 'Physical load test'],
    assembly_validated=False, svg_export_allowed=False)
OUT.mkdir(exist_ok=True)
(OUT/'Payas_STEM_Astronot_KayarAyak_STUDY.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
im=Image.new('RGB',(1400,940),'white'); d=ImageDraw.Draw(im)
font='C:/Windows/Fonts/arial.ttf'
def text(x,y,s,size=23):
    d.text((x,y),s,fill='black',font=ImageFont.truetype(font,size))
text(45,25,'ASTRONOT | YERİNDE KAYAR AYAK',36)
text(45,78,'Hareket şeması — kesim çizimi değildir. Önerilen strok: her ayakta 16 mm.',23)
text(65,135,'ÜST GÖRÜNÜŞ: GÖVDE SABİT',25)
d.rectangle((190,240,440,390),outline='black',width=4)
text(246,294,'GÖVDE')
for x,y,label in [(120,245,'SOL'),(480,325,'SAĞ')]:
    d.line((x+20,190,x+20,460),fill='gray',width=3)
    d.rectangle((x-12,y,x+52,y+100),outline='black',width=4)
    text(x-5,485,label)
    d.line((x+75,220,x+75,430),fill='black',width=2)
    d.polygon([(x+75,215),(x+68,231),(x+82,231)],fill='black')
    d.polygon([(x+75,435),(x+68,419),(x+82,419)],fill='black')
text(200,435,'İleri / geri')
text(730,135,'BİR MOTOR TURUNDA AYAK KONUMU',25)
text(740,182,'Açı          Sol ayak         Sağ ayak',23)
for j,angle in enumerate((0,90,180,270,360)):
    v=R*math.cos(math.radians(angle))
    text(745,230+j*48,f'{angle:3d}°          {v:+.0f} mm           {-v:+.0f} mm')
text(730,495,'+ öne, − arkaya; orta konuma göre',22)
text(55,560,'MOTOR → KARŞIT KRANK PİMLERİ → İKİ KIZAK → AYAKLAR',27)
text(55,620,'Öneri: 8 mm eksantrik, 180° faz farkı. Ayaklar kalkmadan kayar.',24)
text(55,665,'Gövde ayrı sabit taşıyıcıya bağlanır; hareketli ayaklar gövdeyi taşımaz.',24)
text(55,720,'Bu çalışma yalnızca ideal hareket hesabını doğrular.',24)
text(55,763,'Mil, yataklama, kızak ve katman yerleşimi henüz üretim için doğrulanmadı.',24)
text(55,833,'KESİME HAZIR DEĞİL — Şema ölçekli değildir.',28)
im.save(OUT/'Payas_STEM_Astronot_KayarAyak_STUDY.png')
print('1441 motion samples passed; 16 mm stroke; assembly unresolved; SVG export disabled.')
