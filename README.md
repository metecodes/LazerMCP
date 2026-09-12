# LazerMCP

Payas STEM lazer kesim MCP sunucusu. Python **Boxes.py’yi çağırır**; kaynağını modele dökmez, SVG’yi elle yazdırmaz.

Bu sunucu bir **takım çantası**dır, ürün kataloğu değil. Gelen AI (ChatGPT / Claude) fotoğrafa bakar, `plan_laser_job` çağırır, `create_design` ile primitive’lerden kesimi **besteler**. Her maket için yeni `create_*` aracı eklenmez.

| | |
| --- | --- |
| Canlı MCP | `https://mcp.metehanavci.com/mcp` |
| Yerel MCP | `http://127.0.0.1:8000/mcp` |
| Landing | `https://mcp.metehanavci.com` · yerel `http://127.0.0.1:8000` |
| Atölye | `http://127.0.0.1:8000/app` |
| Repo | [metecodes/LazerMCP](https://github.com/metecodes/LazerMCP) |

Claude / ChatGPT connector adresi **kök `/` değil**, `/mcp` yoludur.

---

## Temel kural

Çalışan kod ≠ doğru ürün.  
Oluşmuş SVG ≠ üretilebilir ürün.  
Güzel önizleme ≠ monte edilebilir ürün.

Yazılım fiziksel testi yapamaz. Dijital PASS + fiziksel NOT VERIFIED → prototip SVG. Üretim export’u yazılım asla açmaz.

Gelen AI `speak` kartını aynen yapıştırır:

```
FINAL STATUS: PROTOTYPE READY

Digital Geometry        PASS
Part Completeness       PASS
Connections             PASS
Assembly                PASS
Collision               PASS
Kinematics              PASS
SVG Geometry            PASS
Manufacturing Geometry  PASS

Physical Kerf Test      NOT VERIFIED
Physical Assembly       NOT VERIFIED
Movement Test           NOT VERIFIED
After Assembly Use      NOT VERIFIED

AUTHORIZED OUTPUT:
Prototype SVG

PRODUCTION EXPORT:
BLOCKED
```

| `final_status` | Anlamı |
| --- | --- |
| `BLOCKED` | Dijital satır FAIL / NOT VERIFIED. `AUTHORIZED OUTPUT: None`. `look_again` oku, primitive’i düzelt, `create_design` tekrar çağır. |
| `PROTOTYPE READY` | Dijital satırlar PASS. Yetkili çıktı **Prototype SVG**. Fiziksel satırlar ölçülmediyse NOT VERIFIED. |
| `PRODUCTION READY` | Dijital PASS + insan kerf/montaj/(hareket)/kullanım. Yetkili çıktı **Production SVG**. |

Yazılım fiziksel satırı uydurmaz. İnsan 100 mm çubuğu ölçüp `measured_bar_mm` verir; kerf PASS olabilir. `physical_assembly=verified`, `movement_test=verified` ve `use_test=verified` yalnız gerçek denemeden sonra. Hepsi (yoksa N/A) PASS ise `PRODUCTION READY` ve `PRODUCTION EXPORT: AUTHORIZED`. LED/şalter çalışmasını yazılım uydurmaz. Uydurma flag = FAIL.

`error` / `errors` dönülmez. Öğretme `look_again` ve `speak` ile yapılır.

---

## İş hattı

```
Fotoğraf / istek
    → plan_laser_job
    → create_design
         Designer → Reviewer → Repair → Reviewer → Final Gate → SVG
```

Bu döngü `create_design` **içinde** çalışır. Gelen AI adımı atlayamaz; review için ayrı araç istemez.

1. Fotoğrafa bak. Parçaları `what_you_see` ile anlat.
2. `plan_laser_job` — dilbilgisi, ölçek, `next_tool`.
3. `create_design` — Boxes.py `rectangularWall` / FingerJoint / kontur. Ölçek: `parameters.reference = {feature, mm, drawn_mm}`.
4. Reviewer parça haritası (P01…), bağlantı grafiği (C01…), PASS / WARNING / FAIL / NOT_VERIFIED üretir.
5. Repair minimum parametrik düzeltir (çatı kilidi, eksik gable, koaksiyel mil, tab-slot kalınlığı). Ürünü sıfırdan yazmaz.
6. Final Gate `speak` kartını üretir. Dijital PASS olsa bile yetkili çıktı yalnızca Prototype SVG’dir; `PRODUCTION EXPORT` BLOCKED kalır.

2D sanat (logo, siluet, yapboz kazıması) için `create_from_reference`. Duvar / çatı / pervane için **değil**.

---

## Primitive’ler

`create_design` `primitives` listesi alır. Kapı / pencere **ayrı parça değildir**; ön duvara slot kesilir.

| `type` | Ne üretir |
| --- | --- |
| `box` | FingerJoint duvarlar + taban. `x,y,h` iç ölçü mm. `walls.front.holes` / `slots`. |
| `panel` | Motor plakası, güneş paneli, çatı, destek. `w,h`, `edges` (`e` / `f` / `F`). |
| `triangle` / `gable` | Çatı alınlığı. Çatı varsa duvar üstüne FingerJoint kilitlenir. |
| `disc` | Pul / mil adaptörü. Pervane için kullanma. |
| `propeller` | n kanatlı rotor. Fotoğraftaki kanat sayısını oku. |
| `contour` | Kapalı siluet. `points: [[x,y], …]` mm. |
| `coupon` | Kerf kalibrasyonu: `f`/`F` deneme + 100 mm çubuk. **Bir kez.** Her makete eklenmez. |

Opsiyonel işaret (parça üzerine gravür / kesim). Ayrı parça değildir. `part.markings` veya `{type:marking, target_part}`:

| Alan | |
| --- | --- |
| `kind` | `text` · `path` / `logo` · `icon` · `line` |
| `target_part` | Parça `label` veya kutu duvarı (`front`, `back`, …) |
| `x`, `y` | o parçanın sol-altından mm |
| `width` veya `height` | mm; ikisi de varsa kutuya sığdır |
| `rotation` | derece |
| `align` | `center` · `left` · `right` · `top` · `bottom` |
| `operation` | `engrave` (siyah) veya `cut` (kırmızı) |

İkonlar: `plus`, `arrow`, `star`, `heart`, `circle`, `x`, `square`, `triangle`. Metin outline path (Arimo). Logo için `d` (SVG path) veya `points`.

Kenarlar: `rectangularWall` sırası alt, sağ, üst, sol. `e` düz, `f` erkek parmak, `F` dişi parmak deliği. Parmak geometrisini uydurma; Boxes.py FingerJoint üretir.

Ölçek: kullanıcı cm/mm verdiyse o ayaktır. Vermediyse fotoğraftan **tek** uzunluk seç, `parameters.reference = {feature, mm, drawn_mm}` geç. İkinci ölçü uydurma.

---

## MCP araçları

Tercih edilen:

| Araç | Görev |
| --- | --- |
| `plan_laser_job` | Fotoğrafa baktıktan sonra dilbilgisi + `next_tool`. |
| `create_design` | Besteci + reviewer + repair + kapı. |
| `create_from_reference` | Yalnız 2D iz / yapboz kazıması. |
| `validate_assembly` | Kapıyı tekrar oku (`file_id` veya `primitives`). |
| `validate_svg` | XML, tabla, nesting, topoloji. |
| `payas_defaults` | 3 mm kavak, kerf 0.15, 1500×3000, malzeme/makine profilleri. |
| `studio` | Profiller, kerf kaydı, projeler, kullanım, anahtar. Kit değildir. |

Plan söylemedikçe: `generate_svg`, `get_generator_schema`.

İsimli kitler **yalnız mevcut Payas ürünleridir:**

- `create_traffic_light`
- `create_robot_bank`
- `create_drawing_robot`
- `create_product_box`
- `create_yacht`
- `create_astronaut`

Yeni değirmen / ev / puzzle için kit isteme.

---

## Payas varsayılanları

- Malzeme: 3 mm kavak kontrplak
- Kerf / burn kilitli: **0.15 mm**
- Tabla: **1500 × 3000 mm**
- Çıktı: SVG + DXF (`file_id`, `svg_url`, `dxf_url`) + otomatik nest önizlemesi
- Malzeme / makine: `parameters.material` (`poplar_3mm`, `poplar_4mm`, `mdf_3mm`, `acrylic_3mm`), `parameters.machine` (`payas_workshop`, `desktop_400`, `lasercad_900`)
- Kerf: insan `measured_bar_mm` verir; kalibrasyon makine+malzeme için saklanır. Kerf uydurma.
- BOM: kit veya bestelenmiş işte malzeme listesini **MCP yazar** (`bom`, `MATERIALS (MCP)`). Donanımı uydurma.
- Proje: `parameters.project` ile sürüm geçmişi. Studio: `/dashboard`
- Kesim `#FF0000`, kazıma `#000000`, LaserCAD **Y-up**
- Kapalı kesimlerde ~1 mm tutucu nick (parça düşmesin)
- Nesting yalnız öteleme (döndürme / ayna yok)
- Yazılar outline path (paketlenmiş Arimo). SVG `<text>` yok.

Paketler (fiyat landing’de yok; beta açık): **Free** 10 tasarım/ay · SVG · standart profil. **Maker** SVG+DXF · özel malzeme/makine · fotoğraf → tasarım · gelişmiş doğrulama. **Pro** BOM · gelişmiş nesting · proje geçmişi · API · ticari kullanım. `LASERMCP_BETA=1` (varsayılan) kotayı kaldırır, özellikleri açık tutar.

---

## Kurulum

Python 3.12+ (geliştirme 3.14 ile de çalışır). Boxes.py `BOXES_PATH` veya `vendor/boxes-master`.

```powershell
cd C:\Project\boxes-mcp
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Tarayıcı landing: `http://127.0.0.1:8000` · atölye: `/app`  
Cursor MCP: `http://127.0.0.1:8000/mcp`

---

## Ortam değişkenleri

Hepsi isteğe bağlıdır.

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `BOXES_PATH` | `C:\Project\boxes-master` veya `vendor/boxes-master` | Boxes.py kökü |
| `MCP_HOST` | `127.0.0.1` | Bind. Dışarı açmak için `0.0.0.0` |
| `MCP_PORT` | `8000` | Port |
| `MCP_PUBLIC_BASE_URL` | (boş) | Dosya URL kökü |
| `MCP_AUTH_TOKEN` | (boş) | Dolarsa `/mcp`, `/api/*`, `/files/*` Bearer ister. UI ve `/health` açık kalır. `studio` ile ek hashed anahtar üretilebilir |
| `MCP_OUTPUT_DIR` | `output` veya Vercel `/tmp` | Kalıcı SVG klasörü |
| `MCP_DATA_DIR` | `output/studio` | Profiller, kerf, projeler, kullanım, telemetry |
| `LASERMCP_BETA` | `1` | `0` olursa Free/Maker/Pro kotaları uygulanır |
| `BLOB_READ_WRITE_TOKEN` | (boş) | Varsa SVG Vercel Blob’a yazılır; `svg_url` kalır |

## Vercel

`server.py` top-level ASGI `app` export eder. Boxes.py `vendor/boxes-master` ile gelir.

Hobby yeter. Push sonrası isteğe bağlı `MCP_PUBLIC_BASE_URL`. **Deployment Protection** kapalı olsun; aksi halde Claude connector 401 alır.

SVG Vercel’de `/tmp` altındadır (geçici). Canlı connector’ın yeni kodu görmesi için deploy gerekir; ChatGPT/Claude oturumunu yeniden bağla.

## Sağlık

`GET /health` Boxes.py importunu ve generator kataloğunu doğrular.

## Ne yapılmaz

- SVG / DXF elle yazmak
- Geometriyi çevirmek, döndürmek, aynamak
- Parmak eklemini uydurmak (Boxes.py FingerJoint kullan)
- Kapı / pencereyi kayan ayrı parça yapmak
- Pervane yerine `disc` kullanmak
- Her işe kupon eklemek
- LAZER KESİME HAZIR veya üretim export’u yetkili demek (insan ölçüsü / montajı olmadan)
- `measured_bar_mm` veya `physical_assembly` uydurmak
- Kerf veya vida/LED/motor listesini uydurmak (MCP `bom` yazar)
- Her yeni maket için yeni MCP aracı istemek
