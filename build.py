"""Inject pipeline output into the page templates.

  site.json  + template.html                           -> dashboard_v1.html
  site2.json + wx.json + fc.json + template_v2.html    -> dashboard.html   (claude.ai copy, local use)

With PAGES=1 (set by CI) it also writes the public site to _site/:
  index.html (English), so/index.html (Somali), favicon.ico, robots.txt, sitemap.xml,
  site.webmanifest and assets/. Search metadata follows Google Search Central and covers
  what jekyll-seo-tag and jekyll-sitemap generate for GitHub Pages sites: canonical URLs,
  hreflang between the language pages, Open Graph, schema.org JSON-LD and a sitemap with
  language alternates.
"""
import datetime as dt
import html as htmlmod
import json
import os
import re
import shutil

# Share links point at the published page; CI sets SHARE_BASE to the site address.
# The page falls back to its own URL when opened locally.
SHARE_BASE = os.environ.get("SHARE_BASE", "https://claude.ai/artifact/FMSwwJHaP5JkjpxXctXN3Y")
PAGES = bool(os.environ.get("PAGES"))
BASE = SHARE_BASE if SHARE_BASE.endswith("/") else SHARE_BASE + "/"
PAGE_URL = {"en": BASE, "so": BASE + "so/"}

# Contact address shown on the page. Stored split and reversed, and rebuilt by the page's
# script, so simple address harvesters do not pick it up from the HTML.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hmustafa1@hotmail.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "cimilada/cimilada.github.io")

TEXT = {
    "en": {
        "title": "Cimilada: Somalia weather forecasts",
        "desc": "Free weather forecasts for Somalia: 7-day hazard warnings, rain maps from GFS, ECMWF and AI models, "
                "two-week town forecasts, Juba and Shabelle river flow, port waves and the Gu and Deyr outlooks.",
        "locale": "en_US",
        "noscript": "Cimilada shows free weather forecasts for Somalia: 7-day hazard warnings for heavy rain, river "
                    "floods, high seas, heat and dust; rain and wind maps; two-week forecasts for 24 towns; Juba and "
                    "Shabelle river flow; wave forecasts for eight ports; and the Gu and Deyr seasonal outlook. "
                    "Turn on JavaScript to see the forecasts.",
    },
    "so": {
        "title": "Cimilada: Saadaasha hawada Soomaaliya",
        "desc": "Saadaasha hawada Soomaaliya oo bilaash ah: digniinaha khataraha 7 maalmood, khariidadaha roobka, "
                "saadaasha magaalooyinka laba toddobaad, socodka webiyada Jubba iyo Shabeelle, mowjadaha dekedaha "
                "iyo saadaasha xilliyada Gu iyo Deyr.",
        "locale": "so_SO",
        "noscript": "Cimilada waxay bixisaa saadaasha hawada Soomaaliya oo bilaash ah: digniinaha roobka culus, "
                    "daadadka webiyada, badda kacsan, kulaylka iyo boodhka; khariidadaha roobka iyo dabaysha; "
                    "saadaasha 24 magaalo; webiyada Jubba iyo Shabeelle; mowjadaha siddeed deked; iyo saadaasha "
                    "Gu iyo Deyr. Daar JavaScript si aad u aragto saadaasha.",
    },
}


def analytics():
    """Script tags for GoatCounter and/or Umami, from env (set as GitHub repository variables)."""
    tags = []
    gc = os.environ.get("GOATCOUNTER_CODE", "").strip()
    um = os.environ.get("UMAMI_WEBSITE_ID", "").strip()
    if gc:
        tags.append(f'<script data-goatcounter="https://{gc}.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>')
    if um:
        tags.append(f'<script defer src="https://cloud.umami.is/script.js" data-website-id="{um}"></script>')
    return "\n".join(tags)


def contact():
    if "@" not in CONTACT_EMAIL:
        return "null"
    user, domain = CONTACT_EMAIL.split("@", 1)
    return json.dumps({"u": user[::-1], "d": domain[::-1]})


def json_ld(lang, built):
    """schema.org structured data: the site, its publisher, the app and the forecast dataset."""
    t = TEXT[lang]
    day = built[:10]
    end = (dt.date.fromisoformat(day) + dt.timedelta(days=15)).isoformat()
    graph = [
        {"@type": "WebSite", "@id": BASE + "#website", "name": "Cimilada", "url": BASE,
         "inLanguage": ["en", "so"], "description": TEXT["en"]["desc"], "publisher": {"@id": BASE + "#org"}},
        {"@type": "Organization", "@id": BASE + "#org", "name": "Cimilada", "url": BASE,
         "logo": BASE + "assets/icon-512.png", "sameAs": [f"https://github.com/{REPO.split('/')[0]}"],
         "contactPoint": {"@type": "ContactPoint", "contactType": "customer support", "url": BASE + "#contact",
                          "availableLanguage": ["English", "Somali"]}},
        {"@type": "WebApplication", "name": "Cimilada", "url": PAGE_URL[lang], "inLanguage": lang,
         "description": t["desc"], "applicationCategory": "WeatherApplication", "operatingSystem": "Any",
         "isAccessibleForFree": True, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
         "image": BASE + "assets/og.png", "publisher": {"@id": BASE + "#org"}},
        {"@type": "Dataset", "name": "Cimilada weather forecasts for Somalia",
         "description": "Daily-updated weather forecasts for Somalia: 3-hourly rain, temperature and wind from NOAA GFS, "
                        "ECMWF IFS and ECMWF AIFS on a 0.5 degree grid; ECMWF ensemble forecasts for 24 towns; GloFAS "
                        "river discharge for six Juba and Shabelle gauges; wave forecasts for eight ports; and SWALIM "
                        "rain gauge and weather station records.",
         "url": PAGE_URL[lang] + "#datasets", "isAccessibleForFree": True, "dateModified": built,
         "keywords": ["Somalia", "weather forecast", "rainfall", "flood", "Juba", "Shabelle", "Gu", "Deyr",
                      "Soomaaliya", "saadaasha hawada", "roob", "daad"],
         "creator": {"@id": BASE + "#org"},
         "spatialCoverage": {"@type": "Place", "name": "Somalia",
                             "geo": {"@type": "GeoShape", "box": "-2.0 40.4 12.4 51.8"}},
         "temporalCoverage": f"{day}/{end}",
         "variableMeasured": ["Precipitation", "Air temperature", "Wind speed", "River discharge",
                              "Significant wave height", "Dust concentration"]},
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")


def head(lang, built):
    """Everything the public pages carry in <head> besides the template's own title and styles."""
    t, e = TEXT[lang], htmlmod.escape
    other = "so" if lang == "en" else "en"
    tags = [
        f'<script>window.CIMILADA = {json.dumps({"lang": lang, "alt": PAGE_URL})};</script>',
        f'<link rel="canonical" href="{PAGE_URL[lang]}">',
        f'<link rel="alternate" hreflang="en" href="{PAGE_URL["en"]}">',
        f'<link rel="alternate" hreflang="so" href="{PAGE_URL["so"]}">',
        f'<link rel="alternate" hreflang="x-default" href="{PAGE_URL["en"]}">',
        f'<link rel="icon" href="{BASE}favicon.ico" sizes="48x48">',
        f'<link rel="icon" href="{BASE}assets/logo.svg" type="image/svg+xml">',
        f'<link rel="icon" href="{BASE}assets/favicon-32.png" type="image/png" sizes="32x32">',
        f'<link rel="apple-touch-icon" href="{BASE}assets/apple-touch-icon.png">',
        f'<link rel="manifest" href="{BASE}site.webmanifest">',
        '<meta name="theme-color" content="#1b64c4">',
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Cimilada">',
        f'<meta property="og:title" content="{e(t["title"])}">',
        f'<meta property="og:description" content="{e(t["desc"])}">',
        f'<meta property="og:url" content="{PAGE_URL[lang]}">',
        f'<meta property="og:locale" content="{t["locale"]}">',
        f'<meta property="og:locale:alternate" content="{TEXT[other]["locale"]}">',
        f'<meta property="og:image" content="{BASE}assets/og.png">',
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{e(t["title"])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{e(t["title"])}">',
        f'<meta name="twitter:description" content="{e(t["desc"])}">',
        f'<meta name="twitter:image" content="{BASE}assets/og.png">',
        f'<script type="application/ld+json">{json_ld(lang, built)}</script>',
    ]
    # Search Console and Bing Webmaster verification, from repository variables when set
    for env, name in (("GOOGLE_SITE_VERIFICATION", "google-site-verification"), ("BING_SITE_VERIFICATION", "msvalidate.01")):
        if os.environ.get(env, "").strip():
            tags.append(f'<meta name="{name}" content="{e(os.environ[env].strip())}">')
    return "\n".join(tags)


def render(template, payload, lang="en", built=None):
    page = (open(template).read().replace("__SHARE_BASE__", SHARE_BASE).replace("__ANALYTICS__", analytics())
            .replace("__CONTACT__", contact()).replace("__REPO__", REPO))
    if PAGES and built:
        t = TEXT[lang]
        page = page.replace("<title>Cimilada</title>", f"<title>{htmlmod.escape(t['title'])}</title>", 1)
        page = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{htmlmod.escape(t["desc"])}">', page, count=1)
        page = page.replace("__META__", head(lang, built))
        page = page.replace("__NOSCRIPT__", f'<noscript><p style="max-width:70ch;margin:24px auto;padding:0 16px">{htmlmod.escape(t["noscript"])}</p></noscript>')
        # the inline data-URI icon is only for the claude.ai copy; the public site serves icon files
        start = page.find('<link rel="icon" href="data:image/svg+xml')
        if start >= 0:
            page = page[:start] + page[page.index(">", start) + 1:]
        # a full HTML document in standards mode (the claude.ai host adds this wrapper itself)
        page = (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n') + page
    else:
        page = page.replace("__META__", "").replace("__NOSCRIPT__", "")
    return page.replace("__DATA__", payload)


def build(data_path, template, out, extra=None):
    data = json.load(open(data_path))
    for key, fn in (extra or {}).items():
        if os.path.exists(fn):
            data[key] = json.load(open(fn))
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = render(template, payload)
    open(out, "w").write(page)
    print(f"{out} {len(page) / 1e6:.2f} MB")
    return data, payload


def site(template, payload, built):
    """The public site: one page per language plus crawler and install files."""
    out = "_site"
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out + "/so")
    for lang, path in (("en", f"{out}/index.html"), ("so", f"{out}/so/index.html")):
        page = render(template, payload, lang, built)
        open(path, "w").write(page)
        print(f"{path} {len(page) / 1e6:.2f} MB")
    shutil.copytree("assets", f"{out}/assets")
    shutil.copy("assets/favicon.ico", f"{out}/favicon.ico")
    open(f"{out}/.nojekyll", "w").close()
    open(f"{out}/robots.txt", "w").write(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}sitemap.xml\n")
    links = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{h}" href="{u}"/>'
                    for h, u in (("en", PAGE_URL["en"]), ("so", PAGE_URL["so"]), ("x-default", PAGE_URL["en"])))
    urls = "".join(f"\n  <url>\n    <loc>{PAGE_URL[l]}</loc>\n    <lastmod>{built[:10]}</lastmod>\n"
                   f"    <changefreq>daily</changefreq>{links}\n  </url>" for l in ("en", "so"))
    open(f"{out}/sitemap.xml", "w").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}\n</urlset>\n')
    manifest = {
        "name": "Cimilada: Somalia weather forecasts", "short_name": "Cimilada",
        "description": TEXT["en"]["desc"], "lang": "en", "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#f1f4f3", "theme_color": "#1b64c4",
        "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/assets/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    }
    json.dump(manifest, open(f"{out}/site.webmanifest", "w"), indent=1)
    # Service worker: network first, so visitors get today's forecast when online; each page they
    # open is kept, so it still loads offline. Only small files are precached, which keeps a first
    # visit as light as before on metered mobile data.
    open(f"{out}/sw.js", "w").write(f"""const CACHE = 'cimilada-{built[:10]}';
const SMALL = ['/favicon.ico', '/assets/logo.svg', '/assets/icon-192.png', '/site.webmanifest'];
self.addEventListener('install', e => {{ self.skipWaiting(); e.waitUntil(caches.open(CACHE).then(c => c.addAll(SMALL))); }});
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE && k.startsWith('cimilada-')).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {{
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== location.origin) return;
  e.respondWith(fetch(r).then(res => {{
    if (res.ok) {{ const copy = res.clone(); caches.open(CACHE).then(c => c.put(r, copy)); }}
    return res;
  }}).catch(() => caches.match(r, {{ignoreSearch: true}}).then(m => m || caches.match(u.pathname.startsWith('/so/') ? '/so/' : '/'))));
}});
""")
    print(f"{out}/: robots.txt, sitemap.xml, site.webmanifest, sw.js, favicon.ico, assets/")


build("site.json", "template.html", "dashboard_v1.html")
data, payload = build("site2.json", "template_v2.html", "dashboard.html", extra={"wx": "wx.json", "fc": "fc.json"})
if PAGES:
    built = (data.get("fc") or data.get("wx") or {}).get("built") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    site("template_v2.html", payload, built)
