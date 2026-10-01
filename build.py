"""Inject pipeline output into the page templates.

  site.json  + template.html                -> dashboard_v1.html
  site2.json + wx.json + fc.json + template_v2.html   -> dashboard.html   (published)
"""
import json
import os

# Share links point at the published page; CI sets SHARE_BASE to the GitHub Pages URL.
# The page falls back to its own URL when opened locally.
SHARE_BASE = os.environ.get("SHARE_BASE", "https://claude.ai/artifact/FMSwwJHaP5JkjpxXctXN3Y")


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


# Contact address shown on the page. Stored split and reversed, and rebuilt by the page's
# script, so simple address harvesters do not pick it up from the HTML.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hmustafa1@hotmail.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "cimilada/cimilada.github.io")


def contact():
    if "@" not in CONTACT_EMAIL:
        return "null"
    user, domain = CONTACT_EMAIL.split("@", 1)
    return json.dumps({"u": user[::-1], "d": domain[::-1]})


def meta():
    """Icons and link-preview tags, only for the GitHub Pages build (PAGES=1), which serves assets/."""
    if not os.environ.get("PAGES"):
        return ""
    base = SHARE_BASE if SHARE_BASE.endswith("/") else SHARE_BASE + "/"
    desc = "Free weather forecasts for Somalia: 7-day hazards, rain, rivers, seas, Gu and Deyr outlooks. English and Somali."
    return "\n".join([
        f'<link rel="apple-touch-icon" href="{base}assets/apple-touch-icon.png">',
        '<meta name="theme-color" content="#1b64c4">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Cimilada">',
        '<meta property="og:title" content="Cimilada: Somalia weather forecasts">',
        f'<meta property="og:description" content="{desc}">',
        f'<meta property="og:url" content="{base}">',
        f'<meta property="og:image" content="{base}assets/og.png">',
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
    ])


def build(data_path, template, out, extra=None):
    data = json.load(open(data_path))
    for key, fn in (extra or {}).items():
        if os.path.exists(fn):
            data[key] = json.load(open(fn))
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = (open(template).read().replace("__SHARE_BASE__", SHARE_BASE).replace("__ANALYTICS__", analytics())
            .replace("__META__", meta()).replace("__CONTACT__", contact()).replace("__REPO__", REPO)
            .replace("__DATA__", payload))
    open(out, "w").write(html)
    print(f"{out} {len(html) / 1e6:.2f} MB")


build("site.json", "template.html", "dashboard_v1.html")
build("site2.json", "template_v2.html", "dashboard.html", extra={"wx": "wx.json", "fc": "fc.json"})
