# LazerMCP

Payas STEM lazer kesim için MCP sunucusu. Boxes.py’yi Python’dan çağırır; kaynak kodunu modele dökmez.

Kurum içi, ücretsiz katman: tüm CAD ürünleri (kutu, trafik lambası, kumbara, ressam, yat, astronot) ve generator’lar açıktır. Ücretli Vercel, ChatGPT Plus veya token zorunlu değildir.

Yerel arayüz: `http://127.0.0.1:8000`  
MCP: `http://127.0.0.1:8000/mcp`

## Gereksinimler

- Python 3.12+
- [Boxes.py](https://github.com/florianfesti/boxes) ağacı (`BOXES_PATH` veya `vendor/boxes-master`)
- `pip install -r requirements.txt`

## Çalıştırma

```powershell
cd C:\Project\boxes-mcp
.\.venv\Scripts\python.exe server.py
```

Tarayıcıda `http://127.0.0.1:8000` — Payas CAD veya generator seç, SVG üret.

Cursor MCP: `http://127.0.0.1:8000/mcp`  
Claude connector URL: `https://mcp.metehanavci.com/mcp` (kök `/` değil; Claude POST atar, `/mcp` gerekir)

## Ortam değişkenleri

Hepsi isteğe bağlıdır.

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `BOXES_PATH` | `C:\Project\boxes-master` veya `vendor/boxes-master` | Boxes.py kök dizini |
| `MCP_HOST` | `127.0.0.1` | Bind adresi. Dışarı açmak için `0.0.0.0` |
| `MCP_PORT` | `8000` | Port |
| `MCP_PUBLIC_BASE_URL` | (boş) | Dosya URL kökü. Boşsa istek host’u veya Vercel URL’si kullanılır |
| `MCP_AUTH_TOKEN` | (boş) | Kurum içi varsayılan: boş bırakın. Dolarsanız `/mcp`, `/api/*`, `/files/*` Bearer ister |

## MCP araçları

Ürün: `create_traffic_light`, `create_robot_bank`, `create_drawing_robot`, `create_product_box`, `create_yacht`, `create_astronaut`

Yardım: `payas_defaults`, `list_cad_tools`, `list_generator_names`, `get_generator_schema`, `generate_svg`, `validate_svg`, `render_preview`

Tam generator listesi UI’da `GET /api/generators`.

Kullanıcı görsel gönderdiğinde `create_from_reference` kullanılır (yapboz, çizim, logo, foto). İsimli kit araçları isteğe bağlıdır.

## Payas varsayılanları

- 3 mm kavak kontrplak
- Kerf/burn kilitli: **0.15 mm**
- Tabla: **1500 × 3000 mm**
- Çıktı: SVG (`file_id` + `svg_url`)

## Vercel (Hobby / ücretsiz)

`server.py` top-level ASGI `app` export eder. Boxes.py `vendor/boxes-master` ile gelir.

Hobby yeter: fonksiyon süresi 300 sn’ye kadar. Yat/astronot yerelde ~3–6 sn.

Push sonrası isteğe bağlı: `MCP_PUBLIC_BASE_URL`. Token koymayın; herkes tüm araçları kullanır.

Vercel proje ayarında **Deployment Protection** kapalı olsun (Standard Protection off), yoksa yalnızca Vercel hesabı olanlar açar.

SVG Vercel’de `/tmp` altındadır (geçici).

## Sağlık

`GET /health` Boxes.py importunu ve generator kataloğunu doğrular.
