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


def build(data_path, template, out, extra=None):
    data = json.load(open(data_path))
    for key, fn in (extra or {}).items():
        if os.path.exists(fn):
            data[key] = json.load(open(fn))
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = (open(template).read().replace("__SHARE_BASE__", SHARE_BASE).replace("__ANALYTICS__", analytics())
            .replace("__DATA__", payload))
    open(out, "w").write(html)
    print(f"{out} {len(html) / 1e6:.2f} MB")


build("site.json", "template.html", "dashboard_v1.html")
build("site2.json", "template_v2.html", "dashboard.html", extra={"wx": "wx.json", "fc": "fc.json"})
