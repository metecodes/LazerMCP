# LazerMCP

Payas STEM lazer kesim için MCP sunucusu. Boxes.py’yi Python’dan çağırır; kaynak kodunu modele dökmez.

Bu sunucu bir **takım çantası**dır, ürün kataloğu değil. Gelen AI fotoğrafa bakar, `plan_laser_job` çağırır, sonra `create_design` ile primitive’lerden (kutu, panel, disk, üçgen, pervane, kontur) kesimi **besteler**. Her maket için yeni `create_*` aracı eklenmez.

Yerel arayüz: `http://127.0.0.1:8000`  
MCP: `http://127.0.0.1:8000/mcp`  
Canlı: `https://mcp.metehanavci.com/mcp`

## İş akışı

Designer → Reviewer → Repair → Reviewer → Final Gate → SVG

Bu döngü `create_design` içinde çalışır. Gelen AI adımları atlayamaz. Yeni ürün için kit aracı eklenmez.

1. Fotoğrafa bak (`what_you_see`).
2. `plan_laser_job` — dilbilgisi, ölçek, sonraki araç.
3. `create_design` — Boxes.py ile primitive’leri derler, mekanik review/repair uygular, kapıdan geçmeden kesime hazır demez.
4. `final_status`:
   - `BLOCKED` — kesme, primitive’i düzelt, tekrar `create_design`
   - `PROTOTYPE READY` — dijital kontroller geçti; ilk levha prototiptir. **LAZER KESİME HAZIR** değil.
   - `LASER READY` — yalnızca o zaman LAZER KESİME HAZIR
5. İsteğe bağlı `validate_assembly` / `validate_svg` kapıyı tekrar okur.

SVG oluşmuş olması ürünün doğru olduğu anlamına gelmez. Çalışan kod ≠ monte edilebilir ürün.

2D sanat (logo, siluet, yapboz kazıması) için `create_from_reference`. Duvar/çatı/pervane için **değil**.

İsimli kitler yalnız mevcut Payas ürünleridir: trafik lambası, robot kumbara, ressam, ürün kutusu, yat, astronot.

Kalibrasyon: `{type: coupon}` bir kez (f/F deneme + 100 mm çubuk). Her değirmene eklenmez.

## Gereksinimler

- Python 3.12+
- [Boxes.py](https://github.com/florianfesti/boxes) ağacı (`BOXES_PATH` veya `vendor/boxes-master`)
- `pip install -r requirements.txt`

## Çalıştırma

```powershell
cd C:\Project\boxes-mcp
.\.venv\Scripts\python.exe server.py
```

Tarayıcıda `http://127.0.0.1:8000`. Cursor MCP: `http://127.0.0.1:8000/mcp`.  
Claude connector: `https://mcp.metehanavci.com/mcp` (kök `/` değil).

## Ortam değişkenleri

Hepsi isteğe bağlıdır.

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `BOXES_PATH` | `C:\Project\boxes-master` veya `vendor/boxes-master` | Boxes.py kök dizini |
| `MCP_HOST` | `127.0.0.1` | Bind adresi. Dışarı açmak için `0.0.0.0` |
| `MCP_PORT` | `8000` | Port |
| `MCP_PUBLIC_BASE_URL` | (boş) | Dosya URL kökü |
| `MCP_AUTH_TOKEN` | (boş) | Boşsa herkese açık. Dolarsanız `/mcp`, `/api/*`, `/files/*` Bearer ister |

## MCP araçları

Tercih edilen: `plan_laser_job`, `create_design`, `create_from_reference`, `validate_assembly`, `validate_svg`, `payas_defaults`

Plan söylemedikçe: `generate_svg`, `get_generator_schema`

İsimli kit: `create_traffic_light`, `create_robot_bank`, `create_drawing_robot`, `create_product_box`, `create_yacht`, `create_astronaut`

## Payas varsayılanları

- 3 mm kavak kontrplak
- Kerf/burn kilitli: **0.15 mm**
- Tabla: **1500 × 3000 mm**
- Çıktı: SVG (`file_id` + `svg_url`), isteğe bağlı DXF
- Kesim `#FF0000`, kazıma `#000000`, LaserCAD Y-up
- Kapalı kesimlerde ~1 mm tutucu nick
- Nesting yalnızca öteleme (döndürme/ayna yok)

## Vercel

`server.py` top-level ASGI `app` export eder. Boxes.py `vendor/boxes-master` ile gelir.

Hobby yeter. Push sonrası isteğe bağlı: `MCP_PUBLIC_BASE_URL`. **Deployment Protection** kapalı olsun.

SVG Vercel’de `/tmp` altındadır (geçici).

## Sağlık

`GET /health` Boxes.py importunu ve generator kataloğunu doğrular.
