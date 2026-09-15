# Editör yenileme

## Ek aylık servis/API gideri
Yeni ücretli servis, paket veya AI API eklenmedi. Mevcut sunucu ve depolama kotaları yeterliyse öngörülen ek aylık servis/API gideri **0 TL**. Mevcut abonelik, sunucu ve alan adı giderleri buna dahil değildir; kota aşımı hesaplanmadı.

## Uygulanan özellikler
- Referansa uygun üç sütunlu düzen, ızgara, gerçek SVG mm cetveli ve seçim ölçüleri.
- Parça arama, yeniden adlandırma, görünürlük ve düzenleme kilidi. Görünürlük/kilit oturumluk görüntüleme ayarlarıdır; kesim çıktısını değiştirmez.
- Yakınlaştırma, kaydırma ve ekrana sığdırma.
- Panel/kutu/disk/üçgen ekleme, nominal ölçü ve malzeme/geçme boşluğu düzenleme.
- Dikdörtgen ve dairesel delikler; genişlik/çap, yükseklik ve merkez X/Y alanları; kutu yüzü seçimi. Konum seçici nominal yüzü açar; koordinatlar sol alttan ölçülür. Delik seçilen yüzün sınırları içinde kalmalıdır.
- Delik silme, taslak geri al/ileri al (Ctrl+Z / Ctrl+Shift+Z).
- Kaydet (Ctrl+S), kayıt durumu ve mevcut proje deposundan sürüm geçmişi; eski sürümü taslağa yükleyip yeni sürüm olarak kaydetme.
- Panel bağlantılarında kenar eşleştirme, düzenleme/silme; f/F ve uzunluk denetimi. Otomatik çıkarılan bağlantılar doğrulama raporunda ayrıca gösterilir.
- Gerçek Boxes.py önizlemesi ve mevcut mekanik doğrulama raporu; bağlantıyı SVG üzerinde bulma.

## Kullanım
Özellikleri değiştirip “Ölçüleri uygula” veya “Deliği ekle” seçin. Bunlar taslağı değiştirir. “MCP ile doğrula” mevcut motorla SVG önizlemesini günceller ve raporu getirir. “Kaydet” yeni dosya ve proje sürümü oluşturur. Kaydedilmemiş değişiklik varsa eski SVG'yi güncel çıktı sanarak indirmemek için indirme kapalıdır.

## Teknik sınırlar
- Kayıtlar mevcut projects.json deposunda tutulur; kalıcı diskli kurulumlarda oturumlar arasında korunur. Geçici dosya sistemi kullanan sunucusuz dağıtımlarda bu mevcut depo kalıcı değildir; böyle bir dağıtım için depoyu mevcut kalıcı depolamaya bağlamak gerekir. Yeni bulut servisi kurulmadı.
- SVG'de data-panel bilgisi yoksa ya da aynı yüz adı birden fazla kutuya aitse tuval eşleştirmesi yapılmaz; sağdaki/sol paneldeki parça seçimi kullanılabilir.
- Elle kenar eşleştirme panel parçalarında desteklenir. Yazılım fiziksel montajı veya kerf testini yapmış saymaz. Geometri değişince montaj/hareket/kullanım onayları yeniden doğrulama bekler.
- Değişiklikler yerel çalışma alanında; canlıya dağıtım yapılmadı.

## Kontrol
Python testleri: ` .venv/Scripts/python.exe -m unittest tests.test_editor tests.test_auth tests.test_workshop tests.test_pipeline tests.test_manufacturing -q `

Tarayıcı testi: `node tests/editor.test.cjs`. Playwright ve Edge gerekir; gerekirse PLAYWRIGHT_MODULE ile kurulu modül yolunu, PYTHON ile Python yolunu belirtin. Test fixture'ı gerçek derleyiciyle izole geçici proje deposunda üretilir. Tarayıcı testinde HTTP yanıtları örneklenir.

Ayrıca gerçek kaydetme ve editor_context üzerinden yeniden yükleme çalıştırıldı; delik koordinatlarının ve proje kimliğinin korunduğu doğrulandı.
