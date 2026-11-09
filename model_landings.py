"""SEO landing pages for Studio generators. Digital only — physical NOT_VERIFIED."""

from __future__ import annotations

from typing import Any

MODELS: dict[str, dict[str, Any]] = {
    "parametric-box": {
        "slug": "parametric-box",
        "title": "Parametrik kutu jeneratörü",
        "lead": "Finger-joint kutu: iç/dış ölçü, kapak tipi, bölücü, raf ve çekmece. Stüdyoda 3D önizle, SVG/DXF indir.",
        "produces": [
            "Taban, duvarlar ve seçilen kapak panelleri",
            "İsteğe bağlı X/Y bölücüler ve ara raflar",
            "Çekmece tepsileri (hücreye sığan)",
            "Nest’lenmiş SVG + DXF kesim paftası",
        ],
        "assembly": [
            "Tabanı düz koy; duvar finger’larını oturt.",
            "Bölücü ve rafları geçmelere kaydır.",
            "Kapağı tipine göre yerleştir (finger / sürtünme / menteşe / kayar).",
            "Çekmeceleri önden hücreye kaydır.",
        ],
        "tips": [
            "Kalınlığı malzeme profilinden al; X/Y/H ile büyütme.",
            "Kerf ölçülmeden burn alanını boş bırak.",
            "«Üstten» görünümde bölücü konumunu mm ile yaz.",
        ],
        "faq": [
            {
                "q": "Fiziksel montaj doğrulandı mı?",
                "a": "Hayır. Dijital Final Gate geçer; dry-fit ve kerf NOT_VERIFIED kalır.",
            },
            {
                "q": "Misafir kullanabilir miyim?",
                "a": "Evet — önizleme açık. SVG/DXF indirme için giriş ve (gerekirse) hesap onayı gerekir.",
            },
        ],
        "studio": "/studio?tab=box",
        "tags": ["finger-joint", "parametrik", "SVG", "DXF"],
    },
    "name-ornament": {
        "slug": "name-ornament",
        "title": "İsim süsü jeneratörü",
        "lead": "Asılı isim plakası: yuvarlak köşeli panel, ası deliği ve ENGRAVE yazı. AI yok — sabit parametrik tarif.",
        "produces": [
            "Tek dekoratif panel (CUT)",
            "Üst ası deliği",
            "Merkez ENGRAVE isim / yazı",
        ],
        "assembly": [
            "Paneli yataktan çıkar; holding nick varsa kır.",
            "İpi veya halkayı ası deliğinden geçir.",
            "Kazıma yüzeyi önde kalacak şekilde as.",
        ],
        "tips": [
            "Yazı uzunsa genişliği artır; font yüksekliği panelin %45’ini geçmesin.",
            "Ası deliği kalınlıktan biraz büyük seçilir.",
        ],
        "faq": [
            {
                "q": "AI kullanıyor mu?",
                "a": "Hayır. Stüdyo Süs sekmesindeki name_ornament tarifidir; prompt yok.",
            },
            {
                "q": "Nereden üretirim?",
                "a": "Stüdyo → Süs → İsim süsü, veya aşağıdaki Stüdyo bağlantısı.",
            },
        ],
        "studio": "/studio?tab=makers&maker=name_ornament",
        "tags": ["süs", "engrave", "ası", "parametrik"],
    },
    "birdhouse": {
        "slug": "birdhouse",
        "title": "Kuş evi jeneratörü",
        "lead": "Finger-joint kuş evi: giriş deliği ve kaldırılabilir çatı. Boxes.py BirdHouse paftası yerine gate’lenebilir kutu tarifi.",
        "produces": [
            "Finger-joint gövde panelleri",
            "Ön yüzde giriş deliği (amaç: ventilation/entrance)",
            "Çıkarılabilir çatı / kapak",
        ],
        "assembly": [
            "Taban ve dört duvarı finger-joint ile kur.",
            "Giriş delikli ön yüzü dışarı bakacak şekilde yerleştir.",
            "Çatıyı sürtünme / finger tipine göre oturt; kaldırmayı dene.",
        ],
        "tips": [
            "Giriş deliği türüne göre Ø seç (ör. 32 mm).",
            "Delik üst kenara ve finger bölgesine taşmasın.",
            "Dış kullanımda malzeme ve boya seçimi fiziksel test ister.",
        ],
        "faq": [
            {
                "q": "Neden eski BirdHouse indirme vermiyordu?",
                "a": "Katalog çok parçalı pafta Final Gate’i geçemiyordu. Bu tarif stüdyo kutusu gibi doğrulanır.",
            },
            {
                "q": "Fiziksel güvenlik?",
                "a": "Dijital uyarılar vardır; sahada montaj ve hava koşulları NOT_VERIFIED.",
            },
        ],
        "studio": "/studio?tab=makers&maker=birdhouse",
        "tags": ["kuş evi", "finger-joint", "parametrik"],
    },
}


def get_model(slug: str) -> dict[str, Any] | None:
    key = str(slug or "").strip().lower()
    return MODELS.get(key)


def list_models() -> list[dict[str, Any]]:
    return [dict(row) for row in MODELS.values()]


def render_model_html(model: dict[str, Any]) -> str:
    tags = "".join(f"<span>{t}</span>" for t in (model.get("tags") or []))
    produces = "".join(f"<li>{x}</li>" for x in (model.get("produces") or []))
    assembly = "".join(f"<li>{x}</li>" for x in (model.get("assembly") or []))
    tips = "".join(f"<li>{x}</li>" for x in (model.get("tips") or []))
    faq = "".join(
        f"<details><summary>{row['q']}</summary><p>{row['a']}</p></details>"
        for row in (model.get("faq") or [])
    )
    title = model.get("title") or model.get("slug")
    lead = model.get("lead") or ""
    studio = model.get("studio") or "/studio"
    slug = model.get("slug") or ""
    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — LaserMCP</title>
  <meta name="description" content="{lead}">
  <link rel="canonical" href="/models/{slug}">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    :root {{ --ink:#151a21; --mute:#5d6a78; --line:#ddd6cb; --cut:#d10600; --bg:#f3f1ec; --card:#fff; }}
    body {{ margin:0; background:linear-gradient(180deg,#ebe6dc,#f3f1ec 40%); color:var(--ink); font:16px/1.55 "Segoe UI",system-ui,sans-serif; }}
    main {{ max-width:920px; margin:auto; padding:28px 20px 64px; }}
    a {{ color:var(--cut); }}
    .back {{ font-size:14px; }}
    h1 {{ font-size:clamp(28px,5vw,48px); line-height:1.15; margin:18px 0 10px; }}
    .lead {{ font-size:18px; color:var(--mute); max-width:720px; }}
    .tags {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0; }}
    .tags span {{ border:1px solid var(--line); border-radius:999px; padding:6px 12px; font-size:13px; background:var(--card); }}
    .actions {{ display:flex; gap:12px; flex-wrap:wrap; margin:22px 0 8px; }}
    .actions a {{ display:inline-block; padding:12px 18px; border-radius:10px; text-decoration:none; font-weight:600; }}
    .actions a.primary {{ background:var(--cut); color:#fff; }}
    .actions a.ghost {{ background:var(--card); color:var(--ink); border:1px solid var(--line); }}
    section {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:18px 20px; margin:16px 0; }}
    h2 {{ margin:0 0 10px; font-size:18px; }}
    ul {{ margin:0; padding-left:1.2em; }}
    details {{ margin:8px 0; }}
    summary {{ cursor:pointer; font-weight:600; }}
    small {{ color:var(--mute); }}
  </style>
</head>
<body>
<main>
  <a class="back" href="/studio">← Stüdyo</a>
  <h1>{title}</h1>
  <p class="lead">{lead}</p>
  <div class="tags">{tags}</div>
  <div class="actions">
    <a class="primary" href="{studio}">Stüdyoda aç</a>
    <a class="ghost" href="/studio">Tüm jeneratörler</a>
  </div>
  <section>
    <h2>Ne üretir?</h2>
    <ul>{produces}</ul>
  </section>
  <section>
    <h2>Montaj (dijital sıra)</h2>
    <ul>{assembly}</ul>
    <p><small>Fiziksel montaj NOT_VERIFIED — dry-fit ölçümü gerekir.</small></p>
  </section>
  <section>
    <h2>İpuçları</h2>
    <ul>{tips}</ul>
  </section>
  <section>
    <h2>SSS</h2>
    {faq}
  </section>
  <p><small>LaserMCP dijital prototip. Kerf, güç ve çocuk güvenliği fiziksel test olmadan PASS sayılmaz.</small></p>
</main>
</body>
</html>
"""
