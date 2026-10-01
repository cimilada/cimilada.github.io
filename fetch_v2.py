"""Fetch the external layers used by the v2 dashboard into data/.

  power.json   NASA POWER daily met at each gauge/AWS grid cell (for ETo)
  seas5.json   ECMWF SEAS5 monthly rain forecast (Open-Meteo) at every station
  gefs.npz     CHIRPS3-GEFS 16-day rain forecast over Somalia (latest run)
  rivers.json  SWALIM FRRIMS river levels, thresholds and long-term mean
  indices.txt  NOAA PSL Nino3.4 and DMI monthly series (refreshed)
"""
import concurrent.futures as cf
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

D = "data/"
UA = {"User-Agent": "swalim-water-balance/2 (research dashboard)"}


def get(url, data=None, tries=4, timeout=180):
    """GET/POST with retries. Open-Meteo answers 429 when its per-minute or hourly quota
    is used up (shared CI runners hit this), so a 429 waits a full minute and does not
    use up one of the ordinary retries."""
    i = waits = 0
    while True:
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and waits < 8:
                waits += 1
                print(f"429 rate limited, waiting 60 s ({waits}/8)", url[:70], file=sys.stderr, flush=True)
                time.sleep(60)
                continue
            err = e
        except Exception as e:
            err = e
        i += 1
        if i >= tries:
            print("FAIL", url[:120], err, file=sys.stderr, flush=True)
            return None
        time.sleep(8 * i)


def fix_coords(s):
    """Return (lat, lon) or None. One gauge lost its decimal point in SWALIM's list."""
    la, lo = s.get("latitude"), s.get("longitude")
    if not isinstance(la, (int, float)) or not isinstance(lo, (int, float)):
        return None
    if lo > 1000:
        lo = lo / 1e5
    return (la, lo) if -3 < la < 13 and 40 < lo < 52 else None


def points():
    aws = json.load(open(D + "stations.json"))
    mrs = json.load(open(D + "mrs_stations.json"))
    return [(s["station_number"], *fix_coords(s)) for s in aws + mrs if fix_coords(s)]


def power():
    """POWER met grid is 0.5 x 0.625 deg; fetch each cell once."""
    cells = {}
    for code, la, lo in points():
        key = (round(la / 0.5) * 0.5, round(lo / 0.625) * 0.625)
        cells.setdefault(key, []).append(code)
    end = (dt.date.today() - dt.timedelta(days=1)).strftime("%Y%m%d")

    def one(key):
        la, lo = key
        u = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters="
             "T2M,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PS&community=AG"
             f"&latitude={la}&longitude={lo}&start=20160101&end={end}&format=JSON")
        r = get(u)
        return key, json.loads(r)["properties"]["parameter"] if r else None

    try:
        out = json.load(open(D + "power.json"))  # incremental: only fetch cells not yet on disk
    except (OSError, ValueError):
        out = {}
    for key in list(cells):
        if f"{key[0]},{key[1]}" in out:
            for code in cells.pop(key):
                out[code] = f"{key[0]},{key[1]}"
    with cf.ThreadPoolExecutor(3) as ex:
        for key, par in ex.map(one, cells):
            if par:
                for code in cells[key]:
                    out[code] = f"{key[0]},{key[1]}"
                out[f"{key[0]},{key[1]}"] = par
    json.dump(out, open(D + "power.json", "w"))
    print("power cells", len(cells))


def seas5():
    pts = points()
    try:
        out = json.load(open(D + "seas5.json"))
    except (OSError, ValueError):
        out = {}
    pts = [p for p in pts if p[0] not in out]
    for i in range(0, len(pts), 25):
        chunk = pts[i:i + 25]
        q = urllib.parse.urlencode({
            "latitude": ",".join(str(p[1]) for p in chunk),
            "longitude": ",".join(str(p[2]) for p in chunk),
            "monthly": "precipitation_mean,precipitation_anomaly",
            "models": "ecmwf_seas5"})
        r = get("https://seasonal-api.open-meteo.com/v1/seasonal?" + q)
        if not r:
            continue
        j = json.loads(r)
        j = j if isinstance(j, list) else [j]
        for p, x in zip(chunk, j):
            m = x["monthly"]
            out[p[0]] = {"time": m["time"], "mean": m["precipitation_mean"], "anom": m["precipitation_anomaly"]}
        time.sleep(2)
    json.dump(out, open(D + "seas5.json", "w"))
    print("seas5 points", len(out))


def gefs():
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    base = "https://data.chc.ucsb.edu/products/CHIRPS-GEFS/v3/16_day/"
    for back in range(0, 6):
        d = dt.date.today() - dt.timedelta(days=back)
        url = f"{base}{d.year}/{d.month:02d}/c3g_{d:%Y.%m.%d}.tif"
        try:
            with rasterio.open("/vsicurl/" + url) as r:
                w = from_bounds(40.5, -2, 51.5, 12.5, r.transform)
                a = r.read(1, window=w).astype("float32")
                a[a < 0] = np.nan
                np.savez_compressed(D + "gefs.npz", grid=a, transform=np.array(list(r.window_transform(w))[:6]),
                                    start=str(d))
                print("gefs", d, a.shape, np.nanmax(a))
                return
        except Exception as e:
            print("gefs miss", d, str(e)[:80])


def rivers():
    out = []
    for sid in range(1, 11):
        r = get("https://frrims.faoswalim.org/rivers/graph",
                data=urllib.parse.urlencode({"station_id": sid, "start_timestamp": 0, "end_timestamp": 0}).encode())
        if not r:
            continue
        try:
            j = json.loads(r)
        except ValueError:
            continue
        if not j.get("gaugeReadingList") and not j.get("otherDetails"):
            continue
        prev = j.get("previous_year", {}).get("gaugeReadingList", {}) or {}
        out.append({
            "id": sid, "river": j["otherDetails"].get("riverName"), "name": j["otherDetails"].get("stationName"),
            "ind": j.get("indicator"),
            "cur": [[x["dateOfReadingStr"], x["readingValue"], x.get("longtermMean"), x.get("historicalMax"),
                     x.get("historicalMin")] for x in j.get("gaugeReadingList", [])],
            "prev": [[k, v["readingValue"]] for k, v in (prev.items() if isinstance(prev, dict) else [])],
        })
    json.dump(out, open(D + "rivers.json", "w"))
    print("rivers", [(r["name"], len(r["cur"])) for r in out])


def indices():
    for name, url in [("nino34.txt", "https://psl.noaa.gov/data/correlation/nina34.anom.data"),
                      ("dmi.txt", "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data")]:
        r = get(url)
        if r:
            open(D + name, "wb").write(r)


if __name__ == "__main__":
    jobs = sys.argv[1:] or ["indices", "rivers", "seas5", "gefs", "power"]
    for j in jobs:
        globals()[j]()
