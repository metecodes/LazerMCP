"""Non-fabrication schematic and Turkish report from the read-only audit."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parents[2]/'output/ressam_robot_audit'
d=json.loads((P/'audit.json').read_text())
im=Image.new('RGB',(1700,1150),'#f7fafc');dr=ImageDraw.Draw(im)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',21);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17);big=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',29)
dr.text((35,20),'RESSAM ROBOT | Mevcut tasarımın mekanik şeması',font=big,fill='#132b40')
dr.text((35,62),'Kesim çizimi değildir. Ölçüler mm. Poz: krank açısı 0°. Donanım detayları şematiktir.',font=font,fill='#334e68')
def state(t):
 A=18+15j+12*complex(math.cos(t),math.sin(t));delta=112+15j-A;dd=abs(delta);aa=(84**2-30**2+dd**2)/(2*dd)
 B=A+delta/dd*complex(aa,-math.sqrt(84**2-aa**2));return A,B,(B-A)/84
A,B,u=state(0);O=112+15j;v=(B-O)/30;pen=(A+B)/2-21.5j*u
verts=[(0,0),(38,0),(38,8),(58,8),(58,0),(96,0),(96,24),(0,24)]
def top(z):return (110+4.3*z.real,560-4.3*z.imag)
def poly(pts,fill,outline='#334e68',width=2):dr.polygon(pts,fill=fill,outline=outline,width=width)
def rectmap(x0,y0,x1,y1,fun,fill):poly([fun(complex(x0,y0)),fun(complex(x1,y0)),fun(complex(x1,y1)),fun(complex(x0,y1))],fill)
dr.text((45,110),'ÜST GÖRÜNÜŞ (X–Y)',font=big,fill='#132b40')
for x in (0,94):rectmap(x,0,x+36,95,top,'#e7d3b0')
rectmap(10,60,120,95,top,'#c7d2de')
dr.text((290,170),'Gövde 13–17',font=small,fill='#132b40')
c=top(18+15j);r=18*4.3;dr.ellipse((c[0]-r,c[1]-r,c[0]+r,c[1]+r),fill='#f4aa55',outline='#9c570b',width=2)
poly([top(O+v*complex(x,y)) for x,y in [(-6,-6),(36,-6),(36,6),(-6,6)]],'#73c9a4')
poly([top(A+u*complex(x-6,y-18)) for x,y in verts],'#82b7ef')
track=[]
for i in range(721):
 aa,bb,uu=state(i*math.tau/720);track.append(top((aa+bb)/2-21.5j*uu))
dr.line(track,fill='#c12d69',width=3)
poly([top(A+u*complex(x,y)) for x,y in [(22,-14.5),(62,-14.5),(62,-11.5),(22,-11.5)]],'#dd9663')
for z,label,off in [(18+15j,'O1 / 18',(-70,0)),(O,'O2 / 19',(8,-35)),(A,'A',(0,-28)),(B,'B',(7,7)),(pen,'Kalem / 21',(-60,24))]:
 x,y=top(z);dr.ellipse((x-4,y-4,x+4,y+4),fill='#172e43');dr.text((x+off[0],y+off[1]),label,font=small,fill='#172e43')
dr.text((365,490),'20',font=font,fill='#132b40');dr.text((60,740),'Pembe eğri: Ø14 varsayılan kalem ekseninin izi.',font=small,fill='#a02b5a')
dr.text((60,770),'O1=(18,15), O2=(112,15); A–B=84',font=font,fill='#132b40')
def front(z):return (865+4*z.real,820-4*z.imag)
dr.text((855,110),'ÖN GÖRÜNÜŞ (X–Z)',font=big,fill='#132b40')
for x in (0,94):rectmap(x,0,x+36,40,front,'#e7d3b0')
rectmap(10,40,120,160,front,'#eedcc0')
for x,label in ((41,'22'),(89,'23')):
 a,b=front(complex(x,128));dr.ellipse((a-56,b-56,a+56,b+56),fill='white',outline='#132b40',width=2);dr.text((a-13,b-10),label,font=font,fill='#132b40')
for x0,x1,z0,z1,color in [(0,36,46,49,'#f4aa55'),(min(O.real,B.real)-6,max(O.real,B.real)+6,46,49,'#73c9a4'),(min((A+u*complex(x-6,y-18)).real for x,y in verts),max((A+u*complex(x-6,y-18)).real for x,y in verts),54,57,'#82b7ef')]:rectmap(x0,z0,x1,z1,front,color)
rectmap(pen.real-7,0,pen.real+7,97,front,'#d7457b')
dr.line([front(-5+0j),front(140+0j)],fill='#334e68',width=2)
dr.text((870,835),'Kâğıt Z=0; gözler sabit dekoratif diskler.',font=small,fill='#132b40')
dr.text((50,855),'YAN GÖRÜNÜŞ / MEKANİZMA KATMANLARI (Y–Z)',font=font,fill='#132b40')
def side(z):return (230+3*z.real,1110-2.5*(z.imag-35))
rectmap(0,37,95,40,side,'#e7d3b0');rectmap(60,40,95,120,side,'#eedcc0')
rectmap(-3,46,33,49,side,'#f4aa55');rectmap(-25,54,25,57,side,'#82b7ef');rectmap(-15,57,-12,97,side,'#dd9663')
dr.text((620,925),'18 ve 19: Z=46–49',font=font,fill='#a55a10');dr.text((620,960),'20: Z=54–57 → arada 5 mm',font=font,fill='#245d93');dr.text((620,995),'21: Z=57–97; tablar Z=54–57',font=font,fill='#985528');dr.text((620,1030),'Kalem dikey bağlanır; yaylı Z telafisi yok.',font=font,fill='#a02b5a')
im.save(P/'mechanism_views.png')
names=['Sol ayak ön','Sol ayak arka','Sol ayak dış yan','Sol ayak iç yan','Sol ayak üst','Sol ayak alt','Sağ ayak ön','Sağ ayak arka','Sağ ayak dış yan','Sağ ayak iç yan','Sağ ayak üst','Sağ ayak alt','Gövde ön','Gövde arka servis','Gövde sol','Gövde sağ','Gövde üst','Krank','Salıncak','Hareketli kalem kolu','Kalem taşıyıcı','Sol göz','Sağ göz']
sizes=['36×40','36×40','95×40','95×40','36×95','36×95']*2+['110×120','110×120','35×123','35×123','110×35','Ø36','42×12','96×24','40×43','Ø28','Ø28']
connections=['3,4,5,6','3,4,5,6','1,2,5,6','1,2,5,6','1–4,15; motor','1–4','9,10,11,12','9,10,11,12','7,8,11,12','7,8,11,12','7–10,16,19','7–10','15,16,17,22,23','15,16,17; pil','13,14,17,5','13,14,17,11','13–16','Motor göbeği,20','11,20','18,19,21','20,kalem','13','13']
functions=['Kutu kapama ve rijitlik','Kutu kapama, kablo geçişi','Motor ayağı duvarı','Motor ayağı duvarı','Motor sabitleme ve gövde tabı','Taban ve kâğıda oturma','Kutu kapama ve rijitlik','Kutu kapama','Salıncak ayağı duvarı','Salıncak ayağı duvarı','Sabit pivot ve gövde tabı','Taban ve kâğıda oturma','Ayakları bağlayan gövde, yüz','Pil tutma ve servis erişimi','Gövde rijitliği, sol ayağa bağlantı','Gövde rijitliği, sağ ayağa bağlantı','Gövde kapama ve rijitlik','12 mm eksantrik giriş','30 mm yarıçapla B pivotunu kısıtlama','84 mm biyel, kalem hareketi','Kalemi kelepçe/bantla tutma','Dekoratif, hareket için zorunlu değil','Dekoratif, hareket için zorunlu değil']
rows=['|PARÇA NO|PARÇA ADI|ÖLÇÜ (mm)|ADET|BAĞLANDIĞI PARÇA|İŞLEVİ|','|---|---|---|---|---|---|']
rows += [f'|{i+1}|{names[i]}|{sizes[i]} × 3 kalınlık|1|{connections[i]}|{functions[i]}|' for i in range(23)]
joint=['|ERKEK PARÇA / KENAR|SLOT PARÇASI / KENAR|ADET|TAB (mm)|SLOT (mm)|NOMİNAL BOŞLUK|SONUÇ|','|---|---|---|---|---|---|---|']
for q in d['finger_pairs']:joint.append(f"|{q['male']} / {q['male_edge']}|{q['female']} / {q['female_edge']}|{q['count']}|6×3|6×3|0|Nominal uyumlu|")
joint += ['|15 alt tab|5|1|10×3|10×3|0|Nominal uyumlu|','|16 alt tab|11|1|10×3|10×3|0|Nominal uyumlu|','|21 sol tab|20, merkez (33,5)|1|6×3|6×3|0|Nominal uyumlu|','|21 sağ tab|20, merkez (63,5)|1|6×3|6×3|0|Nominal uyumlu|']
text='''# Mevcut Ressam Robot mekanik denetimi

SVG değiştirilmedi; yeni SVG üretilmedi. Sonuç: nominal ahşap geometri ve ideal dört çubuk kinematiği uyumlu; fiziksel çalışma henüz kanıtlanmış değil.

Koordinatlar: montajda sol ayağın ön-sol köşesi X=Y=Z=0; X sağa, Y arkaya, Z yukarı. Parça delikleri nominal parça yerel koordinatında, sol-alt köşeden verilir; levha yerleşim koordinatları değildir.

MOTOR → satın alınan metal mil göbeği → 18 krank → A pivotu → 20 biyel/kalem kolu → 21 kalem taşıyıcı → kalem. 19 salıncak, 20'nin B ucunu 11'deki sabit O2 pivotuna bağlar. 22 ve 23 gözlerdir; hareket aktarmaz.

O1=(18,15), O2=(112,15), sabit açıklık94; eksantrik12; biyel84; salıncak30 mm. Grashof:12+94=106<84+30=114. O2–A uzaklığı82–106; kapanma aralığı54<d<114. Ön montaj dalında tam tur mümkün, ölü nokta yok. Ters montaj dalı bu denetimin kapsamı değildir.

18: merkez(18,18) Ø3.4 mil boşluğu; eksantrik(30,18) Ø3.2. Göbek bağlantıları(11.65,18),(24.35,18),(18,11.65),(18,24.35), tümüØ3.2. Eksantrik12. Mil boşluğu tork aktarmaz; metal göbek aktarır.
19: (6,6),(36,6), Ø3.2; merkez aralığı30, eksantrik değildir.
20: (6,18),(90,18), Ø3.2; merkez aralığı84, eksantrik değildir.
22/23: (14,14), Ø3.2; sabit bağlama deliği, hareket0. Dünya merkezleri(41,57,128),(89,57,128).

18/19 ahşap Z46–49, 20 Z54–57: düşey açıklık5. 21 gövdesi Z57–97, tabları54–57. 3mm malzeme için tasarım; gerçek kalınlık ölçülmedi.

## Tüm parçalar

'''+ '\n'.join(rows)+'''

15/16 ve21 ölçülerine 3mm tab çıkıntısı dahildir. Tüm ölçüler kerf sonrası nominal dış zarftır. 22/23 estetik amaçlıdır; mekanizma için çıkarılabilir. Diğer parçaların yapısal veya taşıyıcı işlevi vardır.

## Bütün geçmeler

Kenar numarası yerel çizimde 0=alt,1=sağ,2=üst,3=sol. 32 kenar çiftinde toplam134 finger; ayrıca4 tab-slot: toplam138 erkek geçme. Karşılıkları mevcut. Kenar profilleri mevcut SVG'nin kayıtlı kapalı tasarım konturundan ölçüldü; mevcut kesim yolları da doğrulandı.

'''+ '\n'.join(joint)+'''

Tabloda kerf sonrası nominal ölçüler vardır. 0.15mm kerf için erkek6'nın yol genişliği6.15; dişi6'nın5.85; slot3'ün2.85mm. 10mm için erkek10.15/dişi9.85. Üretim toleransı belirlenmiş değildir. Gerçek kerf k ise genişlik boşluğu2(k−0.15); levha kalınlığı t ise slot kalınlık boşluğu2.85+k−t. Köprü kalıntıları sıfırlanmalı. Sıfır nominal boşluk gerçek montaj kuvvetini garanti etmez.

## Hareket ve çarpışma

Tam hesap değerleri audit.json içindedir; x_min_max_stroke ve y_min_max_stroke sırasıyla minimum, maksimum ve farktır. 20 pivot orta noktası stroku22.49×15.10; dikdörtgen merkezinin21.92×15.40mm. Herhangi bir malzeme noktasının en büyük eksen stroku X25.17,Y26.92mm; iki maksimum aynı nokta olmak zorunda değil. Kol açısı−26.54…−9.66°, salınım16.88°. Tüm kol süpürme zarfı X−3.90…116.81,Y−33.85…34.99; zarf büyüklüğü kol stroku değildir.

0.05° adımlı7201 pozda nominal çarpışma taraması: krank–salıncak45.56mm; hareketli ahşap–gövde25.01mm; Ø8 veØ14 silindirik kalem varsayımlarında kalem–ayak en az5.19, kalem–yatay kollar3.59mm. Bu son iki sayı gerçek kalem doğrulaması değildir; katalogda kalem modeli belirsiz. Vidalar, somunlar, kablo, esneme ve ara çapların tamamı bu taramada modellenmedi. Sonlu örnekleme sürekli çarpışmasızlığın matematiksel ispatı değildir.

Kalem21'e dik bağlanır, ucu Z0'a elle ayarlanır. İdeal yatay rijit mekanizmada Z sabit kalır; kalem yatay bir deliğin içinde kaymadığından böyle bir kızak sıkışması yoktur. Buna karşılık yaylı yükseklik telafisi yok: gerçek kâğıt/tabla eğriliği, keçenin basıncı, bağlantı boşluğu ve bağların kayması sıkışma veya temas kaybı oluşturabilir. Pivot vidaları ahşabı sıkıştıracak kadar sıkılırsa mekanizma kilitlenir; dönen mafsalda kontrollü eksenel boşluk ve uygun ara parça gerekir. Donanım boyutları ve sıkma düzeni kesinleştirilmemiştir.

Eksantrik vida başı ile Ø17.5 göbek arasındaki radyal mesafe12−8.75=3.25mm. Aynı Z düzeyindeki baş çapı6.5mm olursa teorik sıfır açıklık olur; gerçek baş çapı ve Z konumu doğrulanmalı. Önceki 3mm vida başı zarfı, satın alınmış donanım ölçüsü değildir. Motorun kalem sürtünmesini yenmesi, ahşap dayanımı ve geçmelerin yük altında tutması hesap/test ile doğrulanmış değildir.

## Montaj sırası ve karar

Önce iki ayak kutusunun duvarlarını ve altlarını kur; motoru5'e takıp gövdeyi kapat. Gövde13–17'yi kurup15/16 tablarını5/11'e indir. Pil ve servis bağlarını yerleştir. Metal göbeği motor miline,18'i göbeğe sabitle.19'u11'e6mm ara parçayla bağla.20'yi18/19 üzerine5mm ara parçalarla, ön montaj dalında yerleştir.21'i20'ye iki tabıyla takıp tutucu bağlarını uygula. Kalemi dik ve ucu kağıtta olacak şekilde bağla.22/23'ü13'e tak. Bu bir geometrik montaj sırasıdır; fiziksel montaj denemesi yapılmadı.

Kontrol:23 parça,65 kapalı tasarım konturu,0 yinelenen çizgi,0 kesim çakışması,0 beklenmeyen açık yol. Dış kesimlerde46 kayıtlı tutucu köprü nedeniyle kasıtlı açıklık var; bunlar kapalı lazer yolları değildir. Sayfa1500×3000mm.

Sonuç: tasarım ideal geometri bakımından kurulabilir görünüyor; gerçek monte edilip çalıştığı kanıtlanmadı. Üretim onayı için gerçek kalem/donanım ölçüleri, kerf-kalınlık kuponu, elle360° çevrim ve motorla kâğıt üstünde yük/temas testi gerekir. Mevcut SVG korunmuştur.

SHA256: '''+d['input_sha256']+'\n'
(P/'MEKANIK_DENETIM.md').write_text(text,encoding='utf-8')
print(P)
