# LaserMCP doğrulama denetimi — 21 Eylül 2026

Kapsam: mevcut yerel çalışma ağacı (HEAD 4c47182 ve commit edilmemiş genel motor değişiklikleri). Canlı endpoint/deploy bu denetimde test edilmedi. Üretim kodu değiştirilmedi. Bu rapor kapsamlı hata bulunmadığı garantisi değildir.

Tekrar üretme: `.venv/Scripts/python.exe tools/audit_validation_gaps.py`

## Deneyle doğrulanan açıklar

1. **Kritik: iç içe iki panel PROTOTYPE READY alıyor.** 100×100×3 mm iki panel aynı origin/u/v ile ve tek finger_joint bildirimiyle render_toolbox → review_built akışından geçirildi. CONNECTIONS, ASSEMBLY ve 3D_ASSEMBLY PASS; final PROTOTYPE READY. Compiler eşit kenar uçlarını bağlantı kanıtı kabul ediyor; yüzey yönelimi ve hacim çakışması bu yolu engellemiyor. `explicit_panel_assembly.py:94`, `assembly.py:332`, `composite_assembly.py:243`.

2. **Kritik: rayın içine gömülü hareketli parça motion PASS alıyor.** Aynı konumdaki iki panelden biri hareketli parça, diğeri ray olarak tanımlandı. 10 mm hareketin beş örneği ve sürekli kontrol PASS. Raylar ve allowed_contact_parts bütünüyle atlanıyor; yalnız izin verilen temas bölgesi muaf tutulmuyor. Bu sonuç motion validator düzeyinde doğrulandı; ayrı tam Final Gate deneyi yapılmadı. `linear_motion.py:50`.

3. **Yüksek: çıkarılan malzemenin içine gravür yerleştirilebiliyor.** 100×100 dış kontur, 40–60 mm arası kare iç kesim, iç boşlukta 45–55 mm gravür çizgisi: tüm gravür kontrolleri PASS. Dış polygon kontrol ediliyor ama iç kesim boşlukları malzeme yüzeyinden çıkarılmıyor. `engraving_validation.py:44`.

4. **Yüksek: isimsiz mükerrer gravür algılanmıyor.** Aynı ENGRAVE çizgisi iki defa eklendi. `unintended engraving overlaps=0`, PASS. OBJ_ kimlikleri overlap kontrolünden dışlanıyor. Fazladan lazer geçişi riski var. `engraving_validation.py:60`.

5. **Yüksek: bozuk path topoloji kontrolünden başarılı dönüyor.** `d="M broken"` için `ok=true`, `cut_paths=1`, `closed=0`, hata listeleri boş. Parse hatası sessizce atlanıyor. Bu topoloji fonksiyonu sonucu; bütün Final Gate'in bu SVG'yi kabul ettiği iddia edilmiyor. `topology.py:61`.

6. **Yüksek: standalone sınıflandırması fiziksel sayıyı preset ile eziyor.** engraving_layout ve iki physical panel verildiğinde `physical_part_count=1`, `mode=standalone`, `valid=true`. Sınıflandırıcı düzeyinde doğrulandı; public API'den bu girdiye ulaşılabilirlik ayrıca test edilmeli. `standalone_validation.py:18`.

## Kod incelemesiyle bulunan ek eksikler

- **Kayıt sonrası reviewer hatasında eski başarı korunabilir:** exception yolundaki setdefault mevcut final_status değerini değiştirmiyor. Önceki PROTOTYPE READY silinmeyebilir. Kayıt/depolama entegrasyonunda hata enjeksiyonu henüz yapılmadı. `boxes_adapter.py:830`.
- **Finger üretimi ile doğrulama ayrı kaynaklardan besleniyor:** compiler raporladığı count/pitch değerlerini doğrudan Boxes.py profiline bağlamıyor; assembly, deklarasyon raporundaki MATCH'i taşıyıp ilgili kenarın eski eşleme kontrolünü atlıyor. Gerçek kesim profili ve montaj outline'ı tek kaynak olmalı. `explicit_panel_assembly.py:112`, `assembly.py:332`, `toolbox.py`.
- **Port keep-out uyarlaması tamamlanmamış:** unsafe durumda doğrudan hata veriliyor. Rapordaki reduce_count_then_shift ifadesine rağmen azaltma/kaydırma araması yok. Port inventory karşılaştırması kimlik listeleri üzerinden; dışa aktarılan SVG'deki konum/ölçüyü kanıtlamıyor. `explicit_panel_assembly.py:108`.
- **Gruplar arası çarpışmalar atlanıyor:** collision sınıflandırıcısı yalnız aynı composite_parent içindeki parçaları kontrol ediyor. Ayrıca joint bildirilen çiftlerde penetrasyon büyüklüğünden bağımsız intended contact atanabiliyor. `composite_assembly.py:243`.
- **Hareket geometrisi yaklaşık:** sweep gerçek delikli katı yerine AABB kullanıyor; clearance parametresi gerekli boşluk yerine izin verilen penetrasyon eşiği gibi uygulanıyor. removable_slide için çarpışmasız kısa hareket, parçanın gerçekten kurtulduğu doğrulanmadan removal_verified sayılıyor. `linear_motion.py:55`, `linear_motion.py:70`.
- **DXF layer kontrolü yapısal değil:** ENGRAVE adı ve ACI 2 kodunun dosyada ayrı ayrı bulunması yeterli; aynı layer kaydına ait oldukları doğrulanmıyor. `engraving_validation.py:70`.

## Önerilen düzeltme sırası

1. Coplanar false-PASS karşı örneğini engelle: gerçek profil/normal/temas doğrulaması ve tüm physical parçalar arasında collision.
2. Rayların toplu muafiyetini kaldır; izin verilen temas bölgelerini ve gerçek sweep/removal mesafesini doğrula.
3. Parse/re-review hatalarını fail-closed yap; standalone fiziksel sayısını gerçek parçadan hesapla.
4. Gravürü delikler çıkarılmış malzeme yüzeyinde kontrol et; duplicate/overlap ve DXF layer doğrulamasını güçlendir.
5. Tek authoritative geometriyi SVG, DXF, assembly ve preview boyunca koru; negatif testleri CI'a ekle.

Bu açıklar kapanmadan genel olarak “tüm geçmeli/kaymalı ürünlerde PASS güvenilirdir” sonucu çıkarılamaz. Mevcut pozitif testler bu karşı örnekleri kapsamıyor.
