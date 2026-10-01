"""Scrape SWALIM ClimSeries automatic weather station data.

The AWS map page embeds the station list as JSON; each station page embeds its
daily (or, for older stations, hourly) series as JavaScript arrays of
[epoch_ms, value]. Writes stations.json and raw.json.
"""
import concurrent.futures as cf
import json
import re
import time
import urllib.request

BASE = "https://climseries.faoswalim.org"
VARS = ["rainfall_daily", "humidity_daily", "temperature_daily", "pressure_daily",
        "radiation_daily", "wind_speed_daily", "wind_direction_daily"]


def fetch(url, tries=3, timeout=180):
    for i in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read().decode("utf-8", "ignore")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def stations(group="aws"):
    html = fetch(BASE + f"/station/map/{group}/")
    m = re.search(r"JSON\.parse\('(\[.*?\])'\)", html, re.S)
    return json.loads(m.group(1).encode().decode("unicode_escape"))


def series(station):
    html = fetch(BASE + station["url"])
    out = {}
    for v in VARS:
        m = re.search(r"var " + v + r"\s*=\s*(\[\[.*?\]\]|\[\]|\"\")\s*;", html, re.S)
        out[v] = json.loads(m.group(1)) if m and m.group(1).startswith("[") else []
    return station["station_number"], out


def all_series(station):
    """Manual-rain and synoptic pages embed every series as `var name = [[ms, v], ...];`."""
    html = fetch(BASE + station["url"])
    out = {}
    for name, arr in re.findall(r"var (\w+)\s*=\s*(\[\[.*?\]\])\s*;", html, re.S):
        try:
            out[name] = json.loads(arr)
        except ValueError:
            pass
    return station["station_number"], out


def scrape_group(group):
    st = stations(group)
    json.dump(st, open(f"data/{group}_stations.json", "w"))
    raw = {}
    with cf.ThreadPoolExecutor(5) as ex:
        for code, data in ex.map(all_series, st):
            raw[code] = data
    json.dump(raw, open(f"data/{group}_raw.json", "w"))
    print(group, len(raw), "stations")


if __name__ == "__main__":
    for group in ("mrs", "ss"):
        scrape_group(group)
    st = stations()
    json.dump(st, open("data/stations.json", "w"))
    raw = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for code, data in ex.map(series, st):
            raw[code] = data
            print(code, {k: len(v) for k, v in data.items()})
    json.dump(raw, open("data/raw.json", "w"))
