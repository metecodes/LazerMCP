"""PNG layout and assembly derived from validated yacht SVG contours."""
from pathlib import Path
import sys,json,math
from xml.etree import ElementTree as ET
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from products.yacht.generate import OUT
from products.ressam_robot.generate import NS,parse_path,polygon,Line
r=json.loads(OUT.with_suffix('.validation.json').read_text());root=ET.parse(OUT.with_suffix('.svg')).getroot()
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',25);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
def points(p):return [s.point(i/(1 if isinstance(s,Line) else 24)) for s in p for i in range((1 if isinstance(s,Line) else 24)+1)]
shapes={};arts={}
for p,rec,g in zip(r['parts'],r['bridges'],root.find(NS+"g[@id='CUT']")):
 outer=parse_path(rec['closed_design']);x0,x1,y0,y1=outer.bbox();ox=x0+.075;oy=y1-.075
 paths=[outer]+[parse_path(e.get('d')) for e in g if not e.get('data-holding-bridges')]
 shapes[p['name']]=[[(z.real-ox,oy-z.imag) for z in points(q)] for q in paths]
 arts[p['name']]=[[(z.real-ox,oy-z.imag) for z in points(parse_path(a['d']))] for a in r['engravings'] if a['part']==p['name']]
im=Image.new('RGB',(1500,1150),'white');d=ImageDraw.Draw(im)
d.text((30,20),'PAYAS STEM | YAT — 1:1 KESİM YERLEŞİMİ ÖNİZLEMESİ',font=font,fill='black')
d.text((30,60),'17 parça · 43 tab-slot çifti · 34 tutucu köprü · 3 mm kavak · 0,15 mm kerf',font=small,fill='black')
d.text((30,89),'1500 × 3000 mm levhada kullanılan alan: 479,60 × 313,75 mm (sol üst)',font=small,fill='black')
for e in root.iter(NS+'path'):
 for sub in parse_path(e.get('d')).continuous_subpaths():d.line([(30+(z.real-10)*2.95,130+(z.imag-10)*2.95) for z in points(sub)],fill='black',width=1)
for i,rec in enumerate(r['bridges'],1):
 q=polygon(parse_path(rec['closed_design'])).representative_point();d.text((30+(q.x-10)*2.95,130+(q.y-10)*2.95),str(i),font=small,fill='#777777')
d.text((30,1100),'Numaralar yalnızca bu önizlemede. CUT ve ENGRAVE ayrı katmanlardır; ikisi de siyahtır.',font=small,fill='black')
im.save(OUT.with_suffix('.layout.png'))
def world(n,p,t=0):
 a=r['planes'][n];v=a['origin'].copy()
 for k,value in zip(a['axes'],(*p,t)):v[k]+=value
 return v
def screen(p):
 x,y,z=p;return (130+3.5*(.9*x+.44*y),730+3.5*(.22*x-.45*y-.865*z))
def dep(p):
 x,y,z=p;return .38*x-.78*y+.5*z
im=Image.new('RGB',(1400,1000),'#faf9f6');d=ImageDraw.Draw(im)
d.text((30,25),'PAYAS STEM | YAT AHŞAP MAKET',font=font,fill='black')
d.text((30,65),'300 × 110 × 151 mm — doğrulanmış kesim konturlarından montaj önizlemesi',font=small,fill='black')
entries=[]
for n,loops in shapes.items():
 normal=r['planes'][n]['axes'][2];cam=[.38,-.78,.5][normal];th=3 if cam>0 else 0
 q=[[world(n,p,th) for p in loop] for loop in loops]
 entries.append((sum(dep(p) for p in q[0])/len(q[0]),n,q,th))
for _,n,loops,th in sorted(entries):
 # Render narrow edge strips to make the actual 3 mm thickness visible.
 for pa,pb in zip(shapes[n][0],shapes[n][0][1:]):
  quad=[screen(world(n,pa,0)),screen(world(n,pb,0)),screen(world(n,pb,3)),screen(world(n,pa,3))]
  d.polygon(quad,fill='#79644b')
 d.polygon([screen(p) for p in loops[0]],fill='#e6d4b3' if r['planes'][n]['axes'][2]==2 else '#d8bd93',outline='#554934',width=2)
 for hole in loops[1:]:d.polygon([screen(p) for p in hole],fill='#4f483d',outline='#554934')
 for art in arts[n]:d.line([screen(world(n,p,th)) for p in art],fill='#604d32',width=1)
d.text((30,905),'Statik masaüstü maket. Motor veya elektronik içermez; su geçirmez/yüzer gövde olarak tasarlanmadı.',font=small,fill='black')
d.text((30,940),'Referans görsele göre tasarlandı; ölçüler fotoğraftan alınmadı. Gerçek malzemede kuru montaj denemesi gerekli.',font=small,fill='black')
im.save(OUT.with_suffix('.assembly.png'))

# Document dimensions, exact joint registry and ordered assembly.
names=['Ana güverte','Sol alt gövde','Sağ alt gövde','Arka alt bölme','Ön alt bölme','Sol kabin','Sağ kabin','Ön cam paneli','Arka kabin / kapı','Kabin çatısı','Sol üst köprü desteği','Sağ üst köprü desteği','Üst köprü çatısı','Kıç oturağı','Sol oturak desteği','Sağ oturak desteği','Çapa']
parts='\n'.join(f"|{i}|{names[i-1]} / {p['name']}|{p['w']} × {p['h']} × 3|1|" for i,p in enumerate(r['parts'],1))
joints='\n'.join(f"|{j['id']}|{j['male']} / {j['edge']} / {j['center']}|{j['female']}|{j['slot_center'][0]}, {j['slot_center'][1]}|10 × 3|{j['slot_size'][0]} × {j['slot_size'][1]}|0|Uyumlu|" for j in r['assembly']['joints'])
doc=f'''# PAYAS STEM — Yat maketi

Görsel esas alınarak tasarlanmış statik, elektroniği olmayan 17 parçalı maket. Tasarlanan dış ölçü **300 × 110 × 151 mm**; fotoğraftaki ürünün ölçüsü olduğu iddia edilmez. Kabin yanları eğimli profillidir; ön cam paneli montajı basitleştirmek için diktir. Alt gövde açık bir maket iskeletidir; yüzdürme ve su geçirmezlik amacı taşımaz.

## Üretim

SVG mm ve 1:1; 3 mm kavak kontrplak, tam kerf 0,15 mm. Taraf başına 0,075 mm telafi dosyaya uygulanmıştır. CAM'de yeniden kerf telafisi uygulamayın. 1500 × 3000 mm levhada sol üstten 10 mm pay; kullanılan alan 479,60 × 313,75 mm; parça arası en az 3 mm.

CUT ve ENGRAVE ayrı siyah katmanlar. İlk gravür, ardından kesim yapılır. 34 tutucu köprü var: her dış konturda 2 adet, kesilmeyen yol uzunluğu 1 mm; tahmini kalan malzeme 0,85 mm. Kapalı tasarım konturları raporda saklanır. Makine yolları yalnızca kayıtlı köprülerde açıktır. Önizleme numaraları SVG'de kesilecek/gravürlenecek şekil değildir.

## Parçalar

Ölçüler tablar dahil nominal dış sınır, mm; adetler tek ürün içindir.

|No|Parça|Ölçü|Adet|
|---|---|---|---|
{parts}

## Montaj

1. Köprüleri temizleyin; gerçek levha kalınlığı ve kerfi bir geçme numunesinde deneyin. Çok sıkı geçmeyi zorlayıp kırmayın.
2. 2–5 alt gövde parçalarının üst tablarını, 1 ana güvertenin **altından yukarı** takın. Boyuna yanlar ile enine bölmeler aynı seviyede yere basar.
3. 17 çapayı güvertenin burun slotuna **alttan yukarı** takın.
4. 6–9 kabin parçalarının alt tablarını güverteye **üstten aşağı** yerleştirin. 8 ön cam buruna, 9 kapılı panel kıça bakar. Yan panellerde can simidi yok; pencereler ve merdiven gravürü bulunur.
5. 10 kabin çatısını dört kabin panelinin üst tablarına birlikte indirin. Dört panelin altı önce güvertede hizalanmış olmalıdır.
6. 11–12 köprü desteklerini kabin çatısına takın; 13 üst çatıyı ikisinin üst tablarına indirin.
7. 15–16 oturak desteklerini kıç güverteye takın; 14 oturağı üstlerine indirin.

Kuru montajdan sonra gevşek kalan bağlantılarda küçük tutkal noktaları kullanılabilir. Sıfır nominal boşluk, ölçülmemiş kontrplakta garantili sıkılık anlamına gelmez. Yan parçalardaki gravür yüzleri dışarı bakacak şekilde takılır; geometrileri sağ-sol simetriktir.

## Geçme tablosu

Merkezler ilgili düz parçanın sol-alt köşesinden ölçülür. Male bottom=alt, top=üst kenar. Bütün tablar 10 mm genişlik × 3 mm derinliktedir. Karşı slot yönüne göre 10×3 veya 3×10 görünür. Telafili yol genişlikleri 10,15 / 9,85 ve slot dar kenarı 2,85; kesimden sonra nominal 10 ve 3 hedeflenir.

|No|Erkek / kenar / merkez|Slot parçası|Slot merkezi X,Y|Tab|Slot|Nominal boşluk|Sonuç|
|---|---|---|---|---|---|---|---|
{joints}

## Kontrol sonucu

17 ahşap parça; elektronik parça sayısı 0. 43 tab-slot çifti: gerçek SVG tab genişlikleri, slot konumları ve montajdaki üç boyutlu merkezleri karşılaştırıldı. 74 kapalı kesim tasarım konturu, 34 kayıtlı köprü. Mükerrer kesim, beklenmedik açık yol ve levhada parça çakışması sıfır.

Montajdaki nominal katı panellerin dik kesitlerinde {r['assembly']['collision_slice_samples']} kesit örneği incelendi; parça iç içe geçmesi bulunmadı. Bu kontrol fiziksel dayanım veya tutunma deneyi değildir. Önce bir adet prototip kesip kuru montaj yapılmalıdır.

Dosyalar: `Payas_STEM_Yat_PROTOTYPE.svg`, `.layout.png`, `.assembly.png`, `.validation.json`. Kaynak üretici `products/yacht/generate.py`; mevcut Boxes.py çizim, kerf, yerleşim, kapalı kontur ve tutucu köprü yardımcılarını kullanır.
'''
OUT.with_suffix('.MONTAJ.md').write_text(doc,encoding='utf-8')
