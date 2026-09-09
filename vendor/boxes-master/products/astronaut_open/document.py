import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'output/Payas_STEM_Astronot_AcikSase_V1'
r=json.loads(out.with_suffix('.validation.json').read_text());c=r['components']
rows=[]
for key in ('motor','hub','battery','switch'):
 v=c[key];rows.append([key,v['quantity'],v.get('model',v.get('candidate')),v.get('source','')])
for key,v in c['hardware'].items():
 if 'quantity' in v:rows.append([key,v['quantity'],v.get('model',v.get('specification')),v.get('source','')])
rows.append(['AA pil',3,'1,5V AA; aynı tür üç pil',''])
with out.with_suffix('.BOM.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f);w.writerow(['Parça','Adet','Model / şartname','Kaynak']);w.writerows(rows)
parts='\n'.join(f"|{i}|{p['name']}|{p['w']} × {p['h']} × 3|1|" for i,p in enumerate(r['parts'],1))
joints='\n'.join(f"|{j['id']}|{j['male']} / {j['edge']}|{j['female']}|{j['slot_center']}|10 × 3|{j['slot_size']}|0|Uyumlu|" for j in r['assembly']['joints'])
bom='\n'.join('| '+' | '.join(str(x) for x in row[:3])+' |' for row in rows)
sources='\n'.join(f'- [{row[0]}]({row[3]})' for row in rows if row[3])
doc=f'''# PAYAS STEM — Açık şaseli astronot V1

Yeni iki referans görsele göre oluşturulan tasarım: yuvarlak uçlu açık kılavuz çerçevesi, H biçimli çift kat taban, arkada dar motor/pil kutusu ve önde hareketli astronot. Eski `astronaut_demo` klasörü ile 18 `Astronot_Gosteri` çıktısı kaldırıldı. Bu yeni sürüm önceki tercihe uygun **yerinde hareket eden gösteri modeli**; yürüyen robot değildir. Görseldeki arka bağlantılar görünmediğinden birebir mekanizma kopyası iddiası yoktur.

## Üretim

3 mm kavak, başlangıç tam kerf 0,15 mm. Taraf başına 0,075 mm telafi SVG'de vardır; CAM'de tekrar telafi uygulamayın. Birim mm, ölçek 1:1. 1500 × 3000 mm levhada sol üstte **403,60 × 330,30 mm** alan; 10 mm kenar payı, en az 3 mm parça aralığı.

15 parça, 30 tutucu köprü: her dış konturda 2 adet. Kesilmeyen yol 1 mm, tahmini kalan malzeme 0,85 mm. Kapalı tasarım konturları raporda bulunur; makine yolları yalnızca kayıtlı köprülerde açıktır. CUT ve ENGRAVE ayrı siyah katmanlardır; önce gravür sonra kesim. Yazı/logo yüzünü aynalamayın.

Bu sürüm nominal geometri kontrollerini geçmiş prototiptir. Gerçek kontrplak/kerf numunesi, havşa işlemi, elle serbest hareket ve motor yük deneyi yapılmadan seri üretim onayı verilmez.

## Ahşap parçalar

Tablar dahil dış nominal sınır, mm. Dairesel parçaların ölçüsü sınırlayıcı kare olarak verilmiştir: 9 krank Ø44; 12–15 ara pullar Ø18'dir.

|No|SVG parça adı|Ölçü|Adet|
|---|---|---|---|
{parts}

1 açık şase; 2–6 arka kutu; 7–8 taban; 9 krank; 10 yatay sürgü; 11 astronot. 12+14 sol, 13+15 sağ 6 mm kalınlıklı ara pul çiftidir. Parça numaraları yalnızca PNG önizlemesinde gösterilir.

## Seçilmiş donanım

|Parça|Adet|Model / şartname|
|---|---:|---|
{bom}

İki sökülebilir pil bağı (en fazla 2,5 mm genişlik), kırmızı/siyah esnek kablo, iki yalıtılmış 4,8 mm dişi şalter terminali, makaron, taban için ahşap tutkalı ve metal bağlantılara uygun sökülebilir düşük kuvvetli vida sabitleyici gerekir. Satın alma işlemi yapılmadı; stok ve teslim süresi garanti edilmez. Elektronik boyutlar `products/astronaut_open/components.json` içindeki kaynaklardan alınmıştır; fotoğraftaki sarı motorun ölçüsü tahmin edilmemiştir.

## Motor, pil, şalter

X sağ-sol, Y arkaya, Z zeminden yukarı. Motor mili ekseni (X,Z)=(0,99); motor ön montaj yüzeyi Y=3. Ø4,2 boss açıklığı, merkez aralığı 9 olan iki Ø1,8 motor vida deliği vardır. M1.6×4 gömme vidaların başları ön yüzle tam sıfır olmalı: **kesimden sonra 90° havşa açılacak**. Ø1,8 deliği Ø3 olarak baştan sona büyütmeyin. Vida baş çapı 3, nominal motora giriş 1 mm; gerçek oturma ve serbest dönüş kontrol edilir.

Pololu göbek ön panelden 0,5 mm uzakta; krank Y=−8,5…−5,5. Göbeği D milin düzlüğüne sabitleyin. Krank–göbek dört M3×6 ve birer çelik pul ile bağlanır, nominal tutunma 2,5 mm.

Dar kutuda pil yuvasının **58 mm boyu düşey** çevrildi. 48 mm boy X yönünde, 15 mm derinlik Y yönünde: X=−24…24, Y=18…33, Z=20…78. İki yan duvar arasındaki açıklık 54 mm; her tarafta 3 mm nominal boşluk kalır. Pil arka panele bağlarla sabitlenir. Kablo/terminal çıkıntıları fiziksel montajda kontrol edilir.

Şalter üst panelde: merkez X=0, Y=18, Z=156. Kesit **13,05 × 19,55 mm**; seçilen E-Switch için 3 mm panel sınırındadır. 3 mm'den kalın levhada klips uyumu varsayılmaz. Bağlantı: pil artı → şalter → motor → pil eksi. Önceki 6V motor seçimi korunmuştur; 3×AA nominal 4,5V altında yük testi gerekir.

## Hareket ve donanım sırası

Motor → metal göbek → Ø44 krank → Ø4 omuzlu pim → 40 × 4,4 yatay yuva → çift ahşap ara pullar → astronot. Krank eksantrik yarıçapı 16 mm; astronot toplam **32 mm düşey** hareket eder. Alt kenar Z=57+16 sinθ; üst kenar Z=217+16 sinθ. En yüksek nokta 233 mm; taban 140 × 100 mm.

İki kılavuz yuvası **4,4 × 44 mm**, merkezleri X=±40, Z=149. Figürün kılavuz pimleri X=±40, Z=149+16 sinθ. Ø4 pim merkezinin kullanılabilir düşey aralığı 40 mm; hareket 32 mm, uçlarda 4 mm pay. Yatay yuvada uç payı 2 mm. Nominal eksenel çalışma boşluğu 5−3−0,8−0,8=**0,4 mm**.

Kılavuz montajı içten öne: omuzlu vida başı → PC pul 0,8 → sabit şase 3 → PC pul 0,8 → çelik M3 durdurma pulu 0,5 → Harwin 25 mm dişi/dişi ara bağlantı → figür. Figürün önünden M3×8 ve çelik pul ile ara bağlantıya vidalayın. Omuz Ø4, diş M3; tam dişli sıradan vida kayma pimi yerine geçmez.

Krank bağlantısı: arka M3×8 başı altında **üç adet** çelik pul → krank → bir çelik pul → Harwin 7 mm ara bağlantı → bir çelik durdurma pulu → omuzlu vida. Omuzlu vida önden girer; sürgünün iki yanında birer PC pul vardır. Karşılıklı diş tutunmaları 3 ve 3,5 mm; içeride 0,5 mm uç aralığı kalır.

Figür/sürgü sabit bağlantısı: M3×16 başı → çelik pul → figür 3 → iki ahşap ara pul (3+3) → sürgü 3 → çelik pul → M3 somun. İki takım kullanılır. Bu bağlantı sıkılır; kayma yuvaları sıkılmaz.

21 M3 çelik pul dağılımı: kılavuzlar 4; krank pim bağlantısı 5; göbek 4; figür/sürgü 4; taban somunları 4. Toplam 6 PC pul kayma yüzeylerine gider.

## Montaj sırası

1. Köprüleri temizleyin, gerçek malzeme geçmelerini deneyin ve motor havşalarını açın.
2. Motoru 1 açık şasenin arkasına, göbek/krankı önüne monte edin. Kılavuz omuzlu vidalarını kutu kapanmadan yerleştirin.
3. 2 ve 3 yan kutu panellerinin ön tablarını şaseye, arka tablarını 4 arka panele takın. 6 alt paneli alttan, 5 üst paneli üstten kapatın. Arka panel pil servisi için yapıştırılmaz.
4. Şasenin alt tablarını 7 üst tabana indirin. 6 kutu altını 7'ye dört M3×10 ile bağlayın: başların altında pul yok; içeride birer çelik pul ve somun var. 8 alt tabanın Ø8 cepleri vida başlarını içerir. İki H tabanı birbirine yapıştırın.
5. Pil bağlarını ve kabloları takın; hareketli parçalardan uzak tutun. Şalteri üst panele yerleştirin.
6. 10 sürgü, dört ara pul ve 11 figürü birleştirin. Krank pimini yatay yuvaya, kılavuzları düşey yuvalara bağlayın. Vidaların diş sabitleyicisini kendi ürün talimatına göre kullanın.
7. Enerji vermeden bir tam tur çevirin. Sıkışma yoksa 3AA ile kısa çalışma deneyi yapın; akım/ısınma, kablo sürtmesi, tutunma ve taban kararlılığını kontrol edin. Bu fiziksel test henüz yapılmadı.

## Geçme tablosu

Slot merkezleri ilgili parçanın sol-alt yerel koordinatındadır. Tab genişliği 10, derinliği 3 mm. Slot yönüne göre 10×3 veya 3×10. Telafili tab 10,15 ve slot 9,85 / 2,85 mm; nominal kerf sonrası 10 / 3 hedeflenir. Sıfır nominal boşluk ölçülmemiş levhada garantili press-fit değildir.

|No|Erkek / kenar|Slot parçası|Slot merkezi|Tab|Slot|Boşluk|Sonuç|
|---|---|---|---|---|---|---|---|
{joints}

## Otomatik kontrol

15 parça, 81 kapalı tasarım kesim konturu, 26 eşleşmiş geçme, 30 kayıtlı köprü. Mükerrer kesim, beklenmedik açık yol ve levhada parça çakışması sıfır. Sabit panellerin dik katı kesitlerinde çakışma bulunmadı. Motor/krank, figür/sürgü, kılavuz ve taban vida merkezleri kontrol edildi. Hareket 1441 açıda örneklendi; 5 test başarılı. Sonuç nominal mekanik prototip doğrulamasıdır, fiziksel dayanım veya çalışma sertifikası değildir.

## Kaynaklar

{sources}
'''
out.with_suffix('.MONTAJ.md').write_text(doc,encoding='utf-8')
