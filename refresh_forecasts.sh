#!/bin/sh
# Refresh the fast-moving forecast layers and rebuild the page.
# Station data (scrape.py -> process.py -> fetch_v2.py -> process_v2.py) is refreshed separately.
set -e
cd "$(dirname "$0")"
python3 fetch_wx.py          # wind/rain/temperature grid (GFS, ECMWF, AIFS), Meteosat clouds, active cyclones
python3 fetch_fc.py          # town ensemble, heat and dust, GloFAS rivers, port waves
python3 build.py
