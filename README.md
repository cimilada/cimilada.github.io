# Somalia Station Water Balance

A free, public weather forecasting dashboard for Somalia: a 7-day hazard outlook in WMO
impact-based colours with CAP 1.2 alerts, forecast maps from NOAA GFS, ECMWF IFS and
ECMWF AIFS, two-week ensemble town forecasts, GloFAS river flow, port wave outlooks,
SWALIM station water balance and the Deyr seasonal outlook.

**Live:** https://mustafah1.github.io/somalia-weather-dashboard/

The page is a single static HTML file with its data built in. A GitHub Actions workflow
refetches the forecasts every morning (07:40 Mogadishu time), rebuilds the page and
deploys it to GitHub Pages. If a required source fails, the run stops and the last good
page stays online.

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
