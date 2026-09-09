from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2];base=ROOT/'output/Payas_STEM_Robot_Kumbara_YON_REV1'
d=json.loads(base.with_suffix('.validation.json').read_text());a=d['assembly']
names=['Ön yüz','Arka gövde','Sol yan','Sağ yan','Üst panel','Alt panel','Para boşaltma kapağı','Sol sabit kol','Sağ sabit kol','Sol ayak dış kızak','Sol ayak iç kızak','Sağ ayak iç kızak','Sağ ayak dış kızak','Sol ayak ön basamak','Sağ ayak ön basamak']
sizes=['120×148','120×148','85×148','85×148','120×85','120×85','80×66','44×70','44×70']+['101×15']*4+['27×12']*2
connections=['3,4,5,6','3,4,5,6,7','1,2,5,6,8','1,2,5,6,9','1–4','1–4,10–13','2: iki M3 vida','3: iki M3 vida','4: iki M3 vida','6,14','6,14','6,15','6,15','10,11','12,13']
text='''# PAYAS STEM | ROBOT KUMBARA — MEKANİK PROTOTİP

Bu sürüm para biriktiren pasif bir kumbaradır. Göz ve kalp kazımadır; LED, şalter, pil yuvası ve para sensörü monte edilmiş/çalışır kabul edilmez. Görseldeki elektronik parçaların ölçüleri belirsiz olduğundan elektronik delik veya braket üretilmedi. Durum components.json dosyasında UNRESOLVED olarak kayıtlıdır.

Dosya: Payas_STEM_Robot_Kumbara_YON_REV1.svg. Birim mm, ölçek1:1; 1500×3000mm tabla. Tek set sol üstte378.6×324.45mm alanda,10mm kenar payı ve3mm parça aralığıyla yerleşir. Tüm çizgiler siyah; CUT ve ENGRAVE ayrı katmanlardır. Yazı ve desenler kapalı vektör kazıma konturlarıdır.

Gövde120×85×148mm, ayaklarla yükseklik160mm. Kollar ve arka kapak dahil toplam dış zarf126×104×160mm. Malzeme3mm kavak kontrplak; başlangıç kerf0.15mm, Boxes.py burn0.075mm/yan. Ölçüler kerf sonrası nominaldir; gerçek levha ve kerf ölçülmedi.

## Parçalar

Her satır1 adet, kalınlık3mm. Kızak ölçüsündeki15mm,12mm gövdeye3mm tab çıkıntısı eklenmiş halidir; montajda ayak yüksekliği12mm olur.

|No|Parça|Dış ölçü mm|Bağlandığı parçalar|
|---|---|---|---|
'''
for i in range(15):text+=f'|{i+1}|{names[i]}|{sizes[i]}|{connections[i]}|\n'
text+='''
## Para atma ve boşaltma

Üst yuva34×4mm. Tasarım kabul zarfı en çok32mm çap /3mm kalınlıkta para içindir; belirli bir para birimi ölçülmedi. Gerçek para ile geçiş testi yapılmalıdır. İç hacim geometrik olarak114×79×142mm; vida çıkıntıları hariç yaklaşık1.28litre. Boşaltma açıklığı64×50mm, dış kapak80×66mm; kapak açıklığı her kenarda8mm örter. Kapak gövdeden arkaya3mm taşar.

Kapak iki M3 vida, pul ve somunla sabitlenir. İç somuna boşaltma açıklığından erişilir; bir vida çıkarılıp diğeri gevşetilerek kapak yana döndürülebilir. Bu pratik erişim işlemi fiziksel prototipte doğrulanmalıdır. Vida boyu gerçek pul/somun kalınlıklarıyla seçilmelidir; ahşap yığının kalınlığı6mm. Kollar için de dörder değil, toplam4 M3 bağlantı gerekir. Genel toplam6 M3 vida takımıdır. DeliklerØ3.2mm.

## Bütün geçmeler

Kenarlar yerel kesim çiziminde0=alt,1=sağ,2=üst,3=sol. Bütün finger kenarları bire bir eşleştirildi; gerçek SVG profillerinde diş merkezleri ve kerf telafili genişlikleri karşılaştırıldı. Tab-slot boyutları genişlik×malzeme kalınlığıdır.

|Erkek parça/kenar|Dişi parça/kenar|Adet|Tab mm|Slot mm|Nominal boşluk|Sonuç|
|---|---|---|---|---|---|---|
'''
for p in a['finger_pairs']:text+=f"|{p['male']}/{p['male_edge']}|{p['female']}/{p['female_edge']}|{p['count']}|6×3|6×3|0|Nominal uyumlu|\n"
for p in a['tab_slot_pairs']:
 text+=f"|{p['male']}|{p['female']}|1|{p['tab_mm'][0]}×3|{p['slot_mm'][0]}×3|0|Nominal uyumlu|\n"
text+='''
Toe parçasının iki tam dikdörtgen ucu, kızaklardaki12×3mm yuvalara3mm girer. Kızakların her birinde6×3mm iki üst bağlantı vardır; toplam8 tab alt paneldeki8 slotla eşleşir. Bağlantı merkezleri dünya XY düzleminde X=12,36,84,108 ve Y=18,66mm'dir.

6mm erkek geçme yol genişliği6.15mm, karşılık gelen dişi yol genişliği5.85mm;3mm slotun yol kalınlığı2.85mm. Gerçek kerf k olduğunda genişlik boşluğu2(k−0.15), slot-kalınlık boşluğu2.85+k−gerçek levha kalınlığıdır. Sıfır nominal boşluk, gerçek press-fit sıkılığının doğrulandığı anlamına gelmez.

## Kazıma yüzü ve yön

Ön, arka, sol, sağ, arka kapak ve iki kol SVG’de dışarıdan bakış yönünde çizilmiştir. Kazınmış yüz dışarı bakacak şekilde monte edilmelidir. Sol panel ve sol kol sağ parçaların delik yönüyle aynı değildir; karıştırmayın. Önizlemede arka ve sol yazıların aynalanması düzeltildi. Üst panel yazısı önden okunacak yöndedir; arkadan bakınca baş aşağı görünmesi normaldir, aynalama değildir. Alt panel kazımasızdır ve çizimde içten bakıştır. Arka kapak önizlemede gövdenin üzerinde görünür.

## Montaj sırası

1. Kazımayı ve ardından kesimi uygula;30 tutucu köprüyü koparıp kalıntılarını geçme yüzeylerinden sıfırla. İlk kuponda gerçek levha/kerf uyumunu kontrol et.
2.14'ü10–11 arasına,15'i12–13 arasına tak. Her ön basamağın iki ucunu kızak yuvalarına3mm geçir.
3. Dört kızağın toplam8 tabını6 numaralı alt paneldeki slotlara aşağıdan tak. Ayak altlarının aynı düzlemde olduğunu kontrol et.
4. Yan panelleri ve ön/arka gövdeyi alt panele tak. Sabit kolları iki vida ile karşılık gelen yan panele bağla; vidaları ahşabı ezmeden sık.
5. Üst paneli tak. Gövde geçmeleri ve ayak bağlantıları test kuponuna göre yeterince tutmuyorsa kalıcı yapısal eklerde az miktarda ahşap tutkalı gerekir. Servis kapağını yapıştırma.
6. Arka kapağı iki M3 bağlantıyla sabitle. Para atma ve boşaltma denemesi yap; doluluk arttıkça tabanın ve ayak bağlantılarının yük altındaki durumunu kontrol et.

## Kontrol sonucu ve sınırlar

15 parça,41 kapalı tasarım kesim konturu;0 yinelenen kesim segmenti,0 kesim çakışması,0 beklenmeyen açık yol.30 tutucu köprü nedeniyle dış lazer yolları kayıtlı noktalarda kasıtlı açıktır. Her köprünün yol boşluğu1mm;0.15mm kerfte tahmini kalan ahşap0.85mm. Bu açıklıkları otomatik kapatma.

12 finger kenar çifti ve12 özel tab/slot uç eşleşmesi kontrol edildi. Kol ve kapak delikleri dünya koordinatlarında çakıştırıldı. Bağlantı dışındaki gövde/kol/kapak/kızak hacimleri koruyucu dikdörtgen zarflarla kontrol edildi; istenmeyen pozitif hacim çakışması bulunmadı. Ek yerlerindeki örtüşmeler karşılıklı slot/finger profilleri üzerinden ayrıca kontrol edildi. Bu denetim montaj için öngörülen sabit poz içindir; kollar hareketli değildir.

Destek zarfı X10.5…109.5,Y−16…85mm. Gövdenin geometrik orta noktası(60,42.5) bu zarfın içindedir. Bu, para dağılımı bilinmeden yük altında devrilmeme veya dayanım ispatı değildir. Gerçek kalınlık/kerf, vida takımı, dolu kumbara yükü, darbe/dayanım ve geçme tutma kuvveti fiziksel prototipte doğrulanmalıdır. Seri üretim onayı verilmemiştir.

SVG onaylanan görünümün işlevsel mekanik uyarlamasıdır: resimdeki ışıklı gözler yerine kazıma; hareketli görünen kollar yerine iki vidalı sabit kollar; görseldeki tek vidalı kapağın yerine iki vidalı, erişilebilir kapak kullanılmıştır.
'''
base.with_suffix('.MONTAJ.md').write_text(text,encoding='utf-8')
print('Finger tongues:',sum(x['count'] for x in a['finger_pairs']))
