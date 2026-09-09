from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'output/Payas_STEM_Robot_Kumbara_ELEKTRONIK_REV2'
d=json.loads(out.with_suffix('.validation.json').read_text())
names=['Ön yüz / elektronik servis','Arka gövde','Sol yan','Sağ yan','Üst panel','Alt panel','Para kapağı','Sol kol','Sağ kol','Sol ayak dış kızak','Sol ayak iç kızak','Sağ ayak iç kızak','Sağ ayak dış kızak','Sol basamak','Sağ basamak','Elektronik / para ayırıcı','Pil rafı']
size=['120×148','120×148','85×148','85×148','120×85','120×85','80×66','44×70','44×70']+['101×15']*4+['27×12']*2+['120×142','66×23']
text='''# PAYAS STEM | Robot Kumbara — Elektronik Bölmeli Revizyon 2

Bu dosya elektronik montajına yönelik ahşap prototiptir. Para atılınca LED yakma işlevi henüz uygulanmış veya test edilmiş değildir. Önceki pasif sürümden farklı olarak üç LED deliği, bir şalter deliği, ayırıcı panel, pil rafı ve ön servis bağ yuvaları eklendi.

Malzeme3mm kavak, başlangıç kerf0.15mm. SVG1:1mm,1500×3000mm levhada sol üstte378.6×362.45mm yerleşim; parçalar arasında3mm, levha kenarında10mm pay. Siyah CUT ve siyah ENGRAVE katmanlarına ayrı işlem atayın.34 tutucu köprü korunmuştur; yol açıklığı1mm, tahmini kalan ahşap0.85mm. Köprüleri otomatik kapatmayın.

## Parçalar

Her parça1 adet, kalınlık3mm. Ayak ve yeni parçaların ölçülerine tablar dahildir.

|No|Parça|Dış ölçü mm|
|---|---|---|
'''
for i in range(17):text+=f'|{i+1}|{names[i]}|{size[i]}|\n'
text+='''
## Elektronik delikleri ve iç düzen

Ön panel1'de üç LED deliğiØ5mm; ön panelin yerel koordinatlarında merkezler(33,101),(81,101),(57,43). Tek şalter kesiti13×19mm, merkez(57,126). Bunlar projenin ana components.json dosyasındaki kullanıcı tanımlı kesitlerden aktarılmıştır; üretici/model bilgisi bulunmayan LED ve şalterin gövde/flanş/klips uyumu doğrulanmış değildir. Gerçek şalterin arka uzantısı26mm elektronik bölmesine sığmalı; gerekli kablo payı ayrıca bırakılmalıdır.

Üst panel5'te para slotu34×4mm, yerel merkez(57,39.5). Dünya Y koordinatında slot40.5…44.5mm arasındadır; ayırıcıY29…32mm'dir. Para elektronik bölmesine değil arka para haznesine düşer.

16 numaralı ayırıcı3mm kalınlığındadır. Gövde içindeki elektronik alan114×26×142mm; para alanı114×50×142mm'dir. Para boşaltma açıklığı2 numaralı arka panelde64×50mm,7 numaralı kapak80×66mm'dir. Arka kapak para bölümüne açılır; pil için ön panel sökülür.

Pil yuvası adayı şaltersiz Pololu142,3×AA; üretici boyutu58×48×15mm. Kaynak: https://www.pololu.com/product/142/specs (2026-09-09 kontrolü). Katalogda X yönü58,Z yönü48,Y yönü15mm kullanıldı. Konumu X48…106,Y14…29,Z20…68mm.17 numaralı raf üzerinde durur;16'daki dört bağ yuvasından geçirilen iki sökülebilir bağla tutulur. Vida deliği uydurulmadı.

Pil yuvası önünde11mm boşluk kalır. Bu sayı gerçek LED bacağı veya kablosunun ölçüsü değildir; kurulumda yalıtılmış bağlantıların bu alana sığması gerekir. Katalogdaki10mm bağlantı zarfı bir tasarım sınırıdır. Bağların ve tellerin gerçek yerleşimi fiziksel kontrolden geçmelidir.

## Geçme tablosu

Gövde ve ayakların önceki12 finger kenar çifti (104 diş) ve12 özel geçmesi korunur. Yeni6 eşleşme aşağıdadır. Tab ve slotlar kerf sonrası nominal6×3mm, nominal boşluk0'dır.

|Erkek|Dişi|Merkez X/Y/Z mm|Tab|Slot|Sonuç|
|---|---|---|---|---|---|
'''
for p in d['electronic_assembly']['additional_tab_slot_pairs']:text+=f"|{p['male']}|{p['female']}|{p['center_xyz_mm']}|6×3|6×3|Nominal uyumlu|\n"
text+='''
Toplam18 özel geçme vardır. Tüm tablolar ve gerçek profil kontrol sonuçları aynı isimli validation.json içindedir. Gerçek kerf ve kalınlık sapması sıfır nominal boşluğu sıkı veya gevşek yapabilir; kuponla doğrulanmadan seri kesime geçilmemelidir.

## Montaj ve servis

1. Ayak basamaklarını çift kızakların arasına geçir. Kızakları alt panele tak.
2.17 pil rafının iki tabını16 ayırıcıdaki iki alt slota geçir. Pil yuvasını rafa yerleştir; iki bağla ayırıcıya tuttur. Bağları paraları takılmaya zorlayan uzun kuyruklarla bırakma.
3. Ayırıcının dört yan tabını sol/sağ gövde slotlarına tak. Alt, yan ve arka gövdeyi birleştir; üst paneli yerleştir.
4. Üç LED ve şalteri gerçek parçaların uygunluğu doğrulandıktan sonra ön paneldeki deliklere monte et. Her LED'in akım sınırlaması, yalıtımı ve sensör sürücüsü seçilen devreye göre hazırlanmalıdır; bu revizyonda devre verilmedi.
5. Ön paneli yerine bastır ve iki üst köşe bağlantısını sökülebilir bağlarla tuttur. Ön paneli yapıştırma. Kazımalı yüz dışarı bakmalıdır; sol ve sağ panel/kol yönleri farklıdır.
6. Sabit kolları ve arka para kapağını mevcut M3 bağlantılarıyla tak. Para kapağını yapıştırma.
7. Pil değişiminde ön panelin iki bağını açıp paneli öne al. Pil yuvasının bağlarını gevşeterek değiştirme işlemini yap. Para boşaltmak için arka kapağı kullan.

## Doğrulama durumu

17 parça,61 kapalı tasarım kesim konturu,34 tutucu köprü.0 yinelenen kesim segmenti,0 kesim çakışması,0 beklenmeyen açık yol. Ayırıcı ve rafın gerçek tab profilleri ile slot merkezleri kontrol edildi; para girişi/ayırıcı ve pil/raf yerleşim testleri geçti. Yazıların dış yüz yönü korundu.

Eksikler: gerçek LED ve şalter tutunması, şalterin26mm alana sığması, seçilecek sensörün ölçüsü/yerleşimi ve devresi, para tetikleme testi, yalıtılmış kablo yerleşimi, gerçek press-fit ve dolu kumbara dayanımı. Modeli belirsiz sensör için yeni delik açılmadı. Bu dosya elektriksel çalışma veya seri üretim onayı değildir.
'''
out.with_suffix('.MONTAJ.md').write_text(text,encoding='utf-8')
# Dimensioned section is a explanatory PNG, not an extra cut contour.
im=Image.new('RGB',(1250,1000),'white');dr=ImageDraw.Draw(im)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
dr.text((35,25),'ROBOT KUMBARA | YANDAN İÇ BÖLÜM ŞEMASI',font=font,fill='black')
def rect(y0,z0,y1,z1,fill):dr.rectangle((100+y0*6,890-z1*4,100+y1*6,890-z0*4),fill=fill,outline='black',width=2)
rect(0,12,85,160,'#f6f2e9');rect(3,15,82,157,'white');rect(29,15,32,157,'#bfa780')
rect(14,20,29,68,'#b9b9b9');rect(9,17,32,20,'#bfa780')
dr.text((122,420),'ELEKTRONİK',font=small,fill='black');dr.text((130,450),'26 mm',font=font,fill='black')
dr.text((330,420),'PARA HAZNESİ',font=small,fill='black');dr.text((365,450),'50 mm',font=font,fill='black')
dr.text((190,715),'3×AA',font=font,fill='black');dr.text((690,200),'16: 3 mm ayırıcı',font=font,fill='black')
dr.text((690,240),'17: Pil rafı',font=font,fill='black');dr.text((690,310),'Ön taraftan pil servisi',font=font,fill='black')
dr.text((690,350),'Arka kapaktan para boşaltma',font=font,fill='black')
dr.text((690,425),'LED: 3 × Ø5 mm',font=font,fill='black');dr.text((690,465),'Şalter: 13 × 19 mm',font=font,fill='black')
dr.text((690,540),'Sensör / devre: belirlenmedi',font=font,fill='black')
dr.line([(355,260),(355,360)],fill='black',width=3);dr.polygon([(347,349),(363,349),(355,367)],fill='black')
dr.text((280,210),'Para girişi',font=small,fill='black')
dr.text((95,920),'ÖN',font=font,fill='black');dr.text((565,920),'ARKA',font=font,fill='black')
dr.text((35,965),'Şematik kesit: pilin dış ölçüsü temsil edilir; LED, şalter, kablo ve sensör gövdeleri modellenmedi.',font=small,fill='black')
im.save(out.with_suffix('.section.png'))
print(out.with_suffix('.MONTAJ.md'))
