# Cimilada

**Cimilada** (Somali for "the weather") is a free, public weather forecasting dashboard for Somalia, in English and Somali: a 7-day hazard outlook in WMO
impact-based colours with CAP 1.2 alerts, forecast maps from NOAA GFS, ECMWF IFS and
ECMWF AIFS, two-week ensemble town forecasts, GloFAS river flow, port wave outlooks,
SWALIM station water balance and the Deyr seasonal outlook.

**Live:** https://mustafah1.github.io/somalia-weather-dashboard/

The page is a single static HTML file with its data built in. A GitHub Actions workflow
refetches the forecasts every morning (07:40 Mogadishu time), rebuilds the page and
deploys it to GitHub Pages. If a required source fails, the run stops and the last good
page stays online.

## Contact

Questions, corrections and Somali translation fixes: dedirector99@outlook.com

## Pipeline

| Step | Script | Runs |
|---|---|---|
| Forecast grid, satellite clouds, cyclones, terrain, imagery | `fetch_wx.py` | daily, CI |
| Town ensemble, heat, dust, GloFAS rivers, port waves | `fetch_fc.py` | daily, CI |
| Inject data into the template | `build.py` | daily, CI |
| SWALIM station data and seasonal products | `scrape.py` → `process.py` → `fetch_v2.py` → `process_v2.py` | locally, then commit `site.json` and `site2.json` |

Run everything locally with `./refresh_forecasts.sh` (needs `pip install -r requirements.txt`).

## Data and licences

This is an unofficial, non-commercial project. Official warnings for Somalia come from
the Somali Disaster Management Agency (SoDMA) and FAO SWALIM.

- FAO SWALIM ClimSeries station data and FRRIMS river levels. Owned by FAO SWALIM.
- CHIRPS v3 and CHIRPS3-GEFS, Climate Hazards Center, UC Santa Barbara.
- NOAA GFS (public domain); ECMWF IFS, AIFS and SEAS5 (CC BY 4.0), via Open-Meteo
  (free for non-commercial use).
- GloFAS and CAMS, Copernicus Emergency Management and Atmosphere Monitoring Services.
- Meteosat imagery, EUMETSAT (free for personal, research and educational use).
- IBTrACS v4, NOAA NCEI; GDACS (EC JRC, UN OCHA).
- Sentinel-2 cloudless 2016 by EOX IT Services (CC BY 4.0); AWS Terrain Tiles.

Ideas for the weather layers follow
[God's Eye View](https://github.com/bilawalsidhu/gods-eye-view) (MIT).

## Visitor and feature analytics

The page can count visits and feature use with [GoatCounter](https://www.goatcounter.com)
(free for non-commercial sites, no cookies, no personal data) and/or
[Umami Cloud](https://umami.is) (free up to 100k events a month). Nothing is loaded unless
configured. Set repository variables under Settings → Secrets and variables → Actions →
Variables, then re-run the workflow:

| Variable | Example | Effect |
|---|---|---|
| `GOATCOUNTER_CODE` | `cimilada` | loads GoatCounter for `https://cimilada.goatcounter.com` |
| `UMAMI_WEBSITE_ID` | `a1b2c3d4-…` | loads Umami Cloud |
| `SITE_URL` | `https://cimilada.github.io/` | address used in "Copy link to this view" |

Tracked events (one count per action per 30 s, at most 80 per visit): map layer, field,
model, unit, season, station, overlays, 2D/3D view, timeline play, point forecast, towns
and town tabs, hazard cards, CAP alerts, raw data and CSV copies, share links, section
links and outbound links.

## Custom address

The site is served from GitHub Pages. Free ways to give it a "cimilada" address:

1. **`cimilada.github.io`**: create a free GitHub organization named `cimilada`, transfer
   this repository to it and rename it `cimilada.github.io`. No DNS needed, HTTPS automatic.
2. **`cimilada.dpdns.org` / `cimilada.qzz.io`** via [DigitalPlat FreeDomain](https://github.com/DigitalPlatDev/FreeDomain):
   needs an account with real contact details and an external DNS host (e.g. Cloudflare).
   Then add GitHub Pages A records (185.199.108–111.153) and set the custom domain in
   Settings → Pages.
3. **`cimilada.eu.org`** via [nic.eu.org](https://nic.eu.org): free and permanent, manual
   approval that can take weeks; needs nameservers first.
4. **`cimilada.com`** (or `.org`) costs about US$10 a year and is the most dependable.
