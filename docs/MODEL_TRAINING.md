# LaserMCP'nin kendi modelini eğitmek (sağlayıcıya para ödemeden)

Amaç: Studio AI isteklerini OpenAI ya da başka bir sağlayıcıya ödeme yapmadan, bu işe
eğitilmiş küçük bir açık kaynak modelle çizmek. Model senin bilgisayarında çalışır.

Sıfırdan model eğitilmiyor. Küçük bir açık modele, LaserMCP kontrolünün onayladığı
tasarımlar gösteriliyor. Kontrol hakem olduğu için veri elle etiketlenmiyor ve pahalı bir
öğretmen modele gerek kalmıyor: açık modelin kendisi çizer, kontrol geçerli olanları tutar,
model bunlarla eğitilir ve döngü tekrarlanır.

## Donanım

- **Mac mini (M4, 8 GB bellek):** öğretmen modeli çalıştırır, veri toplar ve eğitilen modeli
  sürekli yayında tutar. Yaklaşık 4 milyar parametreli bir modeli 4 bit sıkıştırılmış hâlde
  çalıştırır; eğitmeye belleği yetmez.
- **Kaggle ya da Google Colab:** ücretsiz GPU ile eğitim.
- **Windows laptop:** geliştirme. Aynı araçlar orada da çalışır (RTX 3050, 4 GB).

Mac mini'de tek seferlik kurulum, depo kökünden:

```bash
bash tools/local_model/setup_mac.sh
```

Aşağıdaki komutlar Windows yoluyla yazıldı; Mac'te `.venv/Scripts/python.exe` yerine
`.venv/bin/python` kullan ve uzun işlerin başına `caffeinate -i` ekle.

## Aşamalar

| # | Aşama | Nerede | Komut |
|---|---|---|---|
| 0 | Model çalıştırıcıyı (Ollama) kur, taban modeli indir | bilgisayarın | aşağıda |
| 1 | Taban ölçümü: eğitilmemiş modelin puanı | bilgisayarın | `tools/ai_eval.py --model local:lasermcp-teacher` |
| 2 | Pilot: 50 istek, kaç tanesi kontrolden geçiyor | bilgisayarın | `tools/train.py collect --count 50` |
| 3 | Asıl veri: en az 300 onaylı örnek | bilgisayarın (gece boyu) | `tools/train.py collect --count 2000` |
| 4 | Eğitim dosyaları | bilgisayarın | `tools/train.py build` |
| 5 | İnce ayar (varsayılan taban: Qwen3 4B Instruct) | Kaggle | `tools/kaggle_finetune.py` |
| 6 | Eğitilmiş modeli kur ve ölç | bilgisayarın | aşağıda |
| 7 | Döngü: eğitilmiş modeli öğretmen yapıp 3–6'yı tekrarla | | `collect --teacher local:lasermcp` |
| 8 | Yayın: yalnızca ölçüm iyiyse | Vercel + tünel | aşağıda |

Komutlar depo kökünden `.venv/Scripts/python.exe` ile çalışır. `local:` ile başlayan
modeller ücretsizdir ve `--spend` istemez.

### 0. Kurulum (bir kez)

1. Ollama'yı ollama.com adresinden kur.
2. Taban modeli indir ve LaserMCP'nin uzun istemine yetecek bağlamla kaydet:

```bash
ollama pull qwen3:4b
```

```bash
ollama create lasermcp-teacher -f tools/local_model/Modelfile.teacher
```

Başka bir taban model denemek için `Modelfile.teacher` içindeki `FROM` satırını değiştir.
Ticari kullanımdan önce seçtiğin modelin lisansını oku. Qwen3 düşünen bir modeldir:
toplama sırasında `LASERMCP_LOCAL_THINK=off` ayarla, yoksa çıktı sınırı gizli düşünmeye
harcanır.

Aynı klasöre aynı anda tek bir `collect` çalışabilir (`collect.lock`). İkinci bir collect
reddedilir. Çöken bir collect kilidi bırakırsa dosyayı elle sil.

### 6. Eğitilmiş modeli kurmak ve ölçmek

Kaggle'dan inen `lasermcp.gguf` dosyasını `tools/local_model/` içine koy:

```bash
ollama create lasermcp -f tools/local_model/Modelfile.tuned
```

Sonra bu terminalde `LASERMCP_TUNED_MODEL=lasermcp` ve
`LASERMCP_TUNED_BASE_URL=http://127.0.0.1:11434/v1` ayarlayıp ölç:

```bash
.venv/Scripts/python.exe tools/ai_eval.py --model lasermcp-tuned
```

### 8. Yayın

Vercel senin bilgisayarına doğrudan ulaşamaz; arada şifre korumalı bir tünel gerekir
(örneğin Cloudflare Tunnel). Vercel'e üç değişken eklenir: `LASERMCP_TUNED_MODEL`,
`LASERMCP_TUNED_BASE_URL` (tünel adresi, `/v1` ile biter) ve `LASERMCP_LOCAL_API_KEY`
(tünelin beklediği anahtar). Varsayılan model olması için
`LASERMCP_LLM_DEFAULT_MODEL=lasermcp-tuned`. Bilgisayar kapalıyken istekler hata alır ve
Studio kendiliğinden ücretsiz yerel planlayıcıya düşer. Bu adım henüz kurulmadı.

## Nasıl çalışır

- **İstekler** (`tools/train_prompts.py`): 60 nesne türü, ölçü, özellik ve Türkçe/İngilizce
  ifade birleşimlerinden binlerce farklı istek. Ölçüm setindeki istekler ve şablonun ya da
  düz kutu motorunun zaten çizdiği istekler eğitim setine girmez.
- **Toplama** (`collect`): Her isteği öğretmene çizdirir, canlıdaki aynı otomatik
  düzeltmeyi uygular ve yalnızca kontrolden geçeni `output/train/examples.jsonl` dosyasına
  yazar. Düzeltilen taslaklar ayrıca "reddedilen taslak + kontrol notu → düzeltilmiş
  taslak" örneği olur. Durdurulup yeniden başlatılabilir.
- **Sadakat filtresi** (`train.quality_problems`): Kontrol yalnızca parçanın kesilip
  birleşebileceğini kanıtlar. Kontrolden geçse bile şu taslaklar eğitime girmez: sistem
  istemindeki örneği kopyalayan, yazılan ölçüyü ya da yazıyı yok sayan, stand, raf, sandalye,
  köprü ya da düzenleyici için tek bir kutu çizen, 3B bir nesne için tek bir düz levha çizen,
  istenen bölme/raf/çekmece/delik/kapak/tekerlek/desen/rakamı içermeyen ve bozuk ya da sıfır
  ölçülü parça taşıyan taslaklar. Kesim türü de doğru olmalı: vida için en az 2 yuvarlak delik,
  pencere/LCD için bir yuva, USB/giriş için port ya da yuva, havalandırma için en az 3 kesim,
  sap için el yuvası ya da ek parça. `build` aynı kuralı eski satırlara da uygular.
- **Kısa sistem istemi**: Eğitilmiş model grameri örneklerden öğrenir; hem eğitimde hem
  kullanımda gramersiz kısa istem kullanılır (`llm_client.tuned_system_prompt`). Bu istem
  değişirse model yeniden eğitilmelidir.

## Karar kuralları

- Pilotta 50 istekten 5'ten azı geçiyorsa taban model bu iş için fazla zayıftır: başka bir
  taban model dene. Döngüyü çok az örnekle başlatmak modeli yalnızca en basit tasarımlara
  alıştırır.
- Eğitimden önce `examples.jsonl` içinden 20 örneği Studio'da aç. Kontrolden geçmek "iyi
  tasarım" demek değildir.
- 300 örneğin altında eğitime başlama.
- Eğitilmiş model ölçüm setinde eğitilmemiş hâlini açıkça geçmiyorsa yayına alma.

## Bilinmeyenler

- İlk pilotlar (14 Kasım 2026, istek başına 20'şer, `output/train_cmp/`): kontrolden geçme
  oranı qwen3:4b'de %62, phi4-mini'de %21, qwen3.5:4b'de %6 oldu. Sadakat filtresi
  sonradan uygulandığında qwen3:4b'nin 25 satırından yalnızca 1'i (kapaklı Arduino kutusu), phi4'ün 4 satırından
  hiçbiri kaldı. Geri kalanların çoğu doğru ölçüde düz bir kutuydu. Gerçek verim düşük:
  300 iyi örnek için binlerce istek gerekebilir.
- Hız: tahminen istek başı 30–90 saniye, yani 2000 istek birkaç gece sürebilir.
- İlk tam tur (16 Kasım 2026): öğretmen qwen3:8b, 1927 istekten 380 örnek (%20). Örneklerin
  hepsi tek kutu ya da tek levha; çok parçalı hiç örnek yok. Filtre sonrası 351 eğitim + 40
  doğrulama satırı, Kaggle T4'te Qwen3-4B Instruct, 3 tur, yaklaşık 20 dakika. 58 soruluk
  ölçüm: ücretsiz planlayıcı 24, eğitilmemiş qwen3:8b 28, **eğitilmiş model 34** (istek
  başına 4–10 sn). Model `metecodes/lasermcp-model`, adaptör `metecodes/lasermcp-lora`
  (gizli Kaggle veri setleri).
- İkinci tur (16 Kasım 2026): `tools/synth_multipart.py` ile kontrolden geçen 300 çok parçalı
  örnek (kitaplık, raf, sehpa, bölmeli düzenleyici) eklendi; 621 eğitim satırı, 63 dakika.
  Sonuç **32/58**, ilk modelden (34) iyi değil. Model çok parçalı çizmeyi deniyor ama panel
  koordinatlarını yanlış hesaplıyor (dik olmayan birleşim, hizasız dil-yuva) ve aile dışı
  isteklerde (telefon standı, eğimli stand) aynı kalıbı yanlış yere uyguluyor. Varsayılan
  `lasermcp` ilk model olarak kaldı; ikincisi `lasermcp-v2`. Eğitim `kaggle kernels push`
  ile tarayıcısız çalışır (output/kaggle_kernel).
- Üçüncü tur (16 Kasım 2026): model koordinat yazmak yerine kalıp seçiyor. `panel_kits.py`
  üç kalıp türü ekler (`shelf_unit`, `bench`, `organizer`); paneller, parmak geçmeler ve
  dil-yuvalar kodla hesaplanır. Aynı 300 çok parçalı istek kalıp biçiminde yeniden üretildi
  (örnek başına ~316 karakter). Sonuç **41/58 (%71)**, istek başına ortalama 6 sn. Varsayılan
  `lasermcp` artık bu model; öncekiler `lasermcp-v1` ve `lasermcp-v2`. Kalan hatalar:
  çekmeceli tasarımlar, düz tek parçalar için hiç parça çizmeme, kutu duvarından taşan yuvalar.
- Kaggle'da indirme: notebook panelinden ve veri seti sayfasından tarayıcıyla inmedi.
  Çalışan yol: notebook'ta `kagglehub.dataset_upload`, bilgisayarda `kaggle datasets
  download` (anahtar `~/.kaggle/access_token`).
- Qwen3 sohbet şablonu eğitimde her cevabın önüne boş bir düşünme bloğu koyar. GGUF içindeki
  şablon bunu kullanımda koymadığı için model cevaba `</tool_call>` ile başlıyordu. Çözüm:
  GGUF'tan `tokenizer.chat_template` silinir (`gguf-new-metadata --remove-metadata
  tokenizer.chat_template`), `Modelfile.tuned` içindeki şablon bloğu kendisi ekler.
- Küçük bir model büyük ihtimalle gpt-4o-mini kadar iyi olmayacak. Hedef, ücretsiz yerel
  planlayıcıdan belirgin iyi olması.

## Ücretli alternatif

Aynı araçlar bir sağlayıcı modeliyle de çalışır (`collect --teacher gpt-5.5 --spend`,
`start --spend`). Bu yol sağlayıcıya ödeme gerektirir ve bu planın parçası değildir.
