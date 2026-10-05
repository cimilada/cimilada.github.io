# Cimilada

**Cimilada** (Somali for "the weather") is a free, public weather forecasting dashboard for Somalia, in English and Somali: a 7-day hazard outlook in WMO
impact-based colours with CAP 1.2 alerts, forecast maps from NOAA GFS, ECMWF IFS and
ECMWF AIFS, two-week ensemble town forecasts, GloFAS river flow, port wave outlooks,
SWALIM station water balance and the Deyr seasonal outlook.

**Live:** https://cimilada.github.io/

The page is a single static HTML file with its data built in. A GitHub Actions workflow
refetches the forecasts every morning (07:40 Mogadishu time), rebuilds the page and
deploys it to GitHub Pages. If a required source fails, the run stops and the last good
page stays online.

## Contact

Questions, corrections and Somali translation fixes: hmustafa1@hotmail.com

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

## Search engines and icons

`build.py` (with `PAGES=1`) writes the public site with the metadata that
[jekyll-seo-tag](https://github.com/jekyll/jekyll-seo-tag) and
[jekyll-sitemap](https://github.com/jekyll/jekyll-sitemap) generate for GitHub Pages
sites, following [Google Search Central](https://developers.google.com/search/docs):

- one address per language, `/` (English) and `/so/` (Somali), linked with `hreflang`
  and a canonical URL; the language switch moves between them
- title, description, Open Graph and Twitter cards per language
- schema.org JSON-LD: `WebSite`, `Organization`, `WebApplication` and `Dataset`
  (the Dataset entry makes the forecasts eligible for Google Dataset Search)
- `robots.txt`, `sitemap.xml` (daily `lastmod`, language alternates), a `<noscript>` summary
- `favicon.ico`, SVG and PNG icons, Apple touch icon and `site.webmanifest`, so phones can
  install the site like an app

To verify ownership in Google Search Console or Bing Webmaster Tools, choose the
"HTML tag" method and save the code as the repository variable `GOOGLE_SITE_VERIFICATION`
or `BING_SITE_VERIFICATION`, then re-run the workflow and submit `sitemap.xml`.

## Fires, flood water and daily imagery (NASA)

`fetch_wx.py` adds three NASA layers, all keyless and refreshed daily:

- **Fires**: active fire detections from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)
  (VIIRS 375 m on NOAA-21, NOAA-20 and S-NPP; MODIS 1 km), last 7 days, from the open global
  CSV files. The map shows 24 h, 48 h or 7 days; the Fires hazard card and statistics count
  detections inside Somalia only.
- **Flood water**: the VIIRS 2-day flood product from [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/),
  reduced to its flood classes.
- **Latest satellite image**: VIIRS NOAA-21 true colour for the newest complete day.

We acknowledge the use of data and imagery from NASA's Fire Information for Resource
Management System (FIRMS), part of NASA's Earth Science Data and Information System (ESDIS).

## Vegetation, sharing and offline use

- **Vegetation**: VIIRS NOAA-20 8-day NDVI from NASA GIBS, the greenness index FEWS NET uses to
  follow drought and pasture; `fetch_wx.py` keeps the newest composite with full coverage.
- **Share on WhatsApp**: the hazard summary and each town's 7-day forecast can be sent as plain
  text (English or Somali) with a link back to the page.
- **Offline**: on the public site a service worker (`sw.js`, written by `build.py`) keeps each
  page a visitor opens, so it still loads without a connection and says how old the forecast is.
  Only small files are precached, so a first visit downloads nothing extra.
- Desert locust layers were investigated (FAO Locust Hub) but its services now need a token and
  its open extract ends in 2020, so the page links to FAO Locust Watch instead.

## Weather now (after Google Weather)

A town card modelled on the features in Google's
[How Google Weather works](https://support.google.com/websearch/answer/13687874):

- **Current conditions**: temperature, feels-like, sky, humidity, wind and gusts, cloud, UV
  index (WHO bands), sunrise and sunset. "Now" is the hourly forecast for the viewer's current
  hour in Somalia, so it stays right through the day.
- **Next 12 hours**: hour-by-hour chance and amount of rain with a plain summary. Somalia has
  no weather radar, so this comes from forecast models (Google's nowcast also uses radar).
- **Hourly (24 h) and 10-day** strips.
- **Air quality**: US AQI with the EPA category and health advice; PM2.5, PM10, dust, ozone (CAMS).
- **Pollen**: not shown; no open pollen forecast covers Somalia.
- **Record and unusual temperatures**: the week's forecast highs against 1991–2025 NASA POWER
  normals and records for the time of year, corrected for each town's model bias over the past
  month (`fetch_fc.py` stages `now` and `clim`; `data/fc/clim.json` is fetched once).
- **"What's the weather where you are?"**: visitors' reports arrive as Umami events
  (`weather-report`, e.g. `Bosaso-dusty`).
