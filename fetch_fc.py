"""Fetch the point forecasts for the v2 dashboard into fc.json.

Built after the products Somali forecasters and responders already read: SWALIM's
3-day rainfall forecast and Flood Watch, ICPAC's weekly forecast and East Africa
Hazards Watch, and the town/port outlooks of Windy and meteoblue. All keyless:

  towns   ECMWF IFS 51-member ensemble, daily rain and max temperature, 15 days
          + apparent max temperature (best-match forecast) and CAMS dust, 5 days
  rivers  GloFAS v4 river discharge ensemble, 30 days, at the six FRRIMS gauges,
          with the Oct 2023 - Jan 2024 flood (the worst since 1997) as reference
  marine  wave height, swell and period at eight ports, 7 days

Each stage is cached in data/fc/<stage>.json; name stages on the command line to refresh.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse

import numpy as np

from fetch_v2 import get

D = "data/fc/"
TOWNS = [  # name, lat, lon, region; north to south
    ("Bosaso", 11.28, 49.18, "Bari"), ("Erigavo", 10.62, 47.37, "Sanaag"), ("Berbera", 10.44, 45.01, "Sahil"),
    ("Borama", 9.94, 43.18, "Awdal"), ("Hargeisa", 9.56, 44.06, "Woqooyi Galbeed"), ("Burao", 9.52, 45.53, "Togdheer"),
    ("Qardho", 9.50, 49.09, "Bari"), ("Las Anod", 8.48, 47.36, "Sool"), ("Garowe", 8.40, 48.48, "Nugaal"),
    ("Galkayo", 6.77, 47.43, "Mudug"), ("Dhusamareb", 5.53, 46.39, "Galgaduud"), ("Hobyo", 5.35, 48.53, "Mudug"),
    ("Beledweyne", 4.74, 45.20, "Hiraan"), ("Dolow", 4.16, 42.08, "Gedo"), ("Hudur", 4.12, 43.89, "Bakool"),
    ("Luuq", 3.80, 42.55, "Gedo"), ("Garbaharey", 3.33, 42.22, "Gedo"), ("Baidoa", 3.11, 43.65, "Bay"),
    ("Jowhar", 2.78, 45.50, "Middle Shabelle"), ("Bardhere", 2.34, 42.28, "Gedo"), ("Mogadishu", 2.04, 45.34, "Banadir"),
    ("Marka", 1.71, 44.77, "Lower Shabelle"), ("Afmadow", 0.52, 42.07, "Lower Juba"), ("Kismayo", -0.36, 42.55, "Lower Juba")]
RIVERS = {  # FRRIMS station id -> (lat, lon); GloFAS snaps to the largest river within 5 km
    1: (3.80, 42.55), 2: (4.16, 42.08), 3: (1.25, 42.58), 4: (4.74, 45.20), 5: (3.85, 45.57), 6: (2.78, 45.50)}
PORTS = [  # a few km offshore so the wave model has sea
    ("Berbera", 10.55, 45.05), ("Bosaso", 11.40, 49.20), ("Caluula", 12.05, 50.85), ("Eyl", 7.95, 49.95),
    ("Hobyo", 5.30, 48.65), ("Mogadishu", 2.00, 45.45), ("Marka", 1.65, 44.90), ("Kismayo", -0.45, 42.65)]


def multi(base, pts, params):
    """One Open-Meteo request for many points; returns a list in the order of pts."""
    q = dict(params, latitude=",".join(f"{p[1]}" for p in pts), longitude=",".join(f"{p[2]}" for p in pts))
    r = get(base + "?" + urllib.parse.urlencode(q))
    if not r:
        return None
    j = json.loads(r)
    if isinstance(j, dict) and j.get("error"):
        print("error", j.get("reason"), file=sys.stderr)
        return None
    return j if isinstance(j, list) else [j]


def r1(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 1)


def towns():
    out = []
    for i in range(0, len(TOWNS), 6):               # ensemble responses are large; keep requests small
        chunk = TOWNS[i:i + 6]
        ens = multi("https://ensemble-api.open-meteo.com/v1/ensemble", chunk,
                    {"daily": "precipitation_sum,temperature_2m_max", "models": "ecmwf_ifs025",
                     "forecast_days": 15, "timezone": "Africa/Mogadishu"})
        if ens is None:
            return None
        for t, e in zip(chunk, ens):
            d = e["daily"]
            P = np.array([d[k] for k in d if k.startswith("precipitation_sum")], dtype="float64")   # member x day
            T = np.array([d[k] for k in d if k.startswith("temperature_2m_max")], dtype="float64")
            day = []
            for j in range(P.shape[1]):
                p = P[:, j][~np.isnan(P[:, j])]
                if not len(p):
                    day.append(None)
                    continue
                tq = T[:, j][~np.isnan(T[:, j])]
                pc = lambda a, q: r1(np.percentile(a, q)) if len(a) else None
                # ECMWF EPSgram percentiles: min, 10, 25, median, 75, 90, max
                day.append({"med": pc(p, 50), "p10": pc(p, 10), "p90": pc(p, 90), "p25": pc(p, 25), "p75": pc(p, 75),
                            "min": pc(p, 0), "max": pc(p, 100),
                            "pr1": round(float((p >= 1).mean()), 2), "pr10": round(float((p >= 10).mean()), 2),
                            "pr30": round(float((p >= 30).mean()), 2), "tx": pc(tq, 50),
                            "txq": [pc(tq, q) for q in (0, 10, 25, 50, 75, 90, 100)]})
            # chance of 50 mm or more in any 3 consecutive days, member by member (SWALIM's 72 h window)
            c3 = np.array([np.nansum(P[:, j:j + 3], 1) for j in range(P.shape[1] - 2)])
            out.append({"name": t[0], "lat": t[1], "lon": t[2], "region": t[3], "days": d["time"], "n": int(P.shape[0]),
                        "d": day, "pr50_72h": round(float((c3 >= 50).mean(1).max()), 2)})
        time.sleep(3)
    # apparent temperature (heat stress) and dust, all towns in one request each
    fc = multi("https://api.open-meteo.com/v1/forecast", TOWNS,
               {"daily": "apparent_temperature_max,temperature_2m_max,relative_humidity_2m_mean", "forecast_days": 7,
                "timezone": "Africa/Mogadishu"})
    aq = multi("https://air-quality-api.open-meteo.com/v1/air-quality", TOWNS,
               {"hourly": "dust,pm10", "forecast_days": 5, "timezone": "Africa/Mogadishu"})
    for o, f, a in zip(out, fc or [None] * len(out), aq or [None] * len(out)):
        if f:
            o["heat"] = {"days": f["daily"]["time"], "at": [r1(v) for v in f["daily"]["apparent_temperature_max"]],
                         "tx": [r1(v) for v in f["daily"]["temperature_2m_max"]],
                         "rh": [r1(v) for v in f["daily"]["relative_humidity_2m_mean"]]}
        if a:
            h = a["hourly"]
            days = sorted({t[:10] for t in h["time"]})
            mx = lambda k: [r1(max([v for t, v in zip(h["time"], h[k]) if t.startswith(dd) and v is not None], default=None))
                            for dd in days]
            o["dust"] = {"days": days, "dust": mx("dust"), "pm10": mx("pm10")}
    print("towns", len(out), "members", out[0]["n"])
    return out


def river_cells():
    """Snap each gauge to the nearest GloFAS cell carrying at least half the local peak flow of 2023.
    Open-Meteo's own snapping put four of six gauges on dry side channels."""
    fn = D + "river_cells.json"
    if os.path.exists(fn):
        return {int(k): tuple(v) for k, v in json.load(open(fn)).items()}
    best = {}
    for sid, (la, lo) in RIVERS.items():
        pts = [(round(la + dy, 3), round(lo + dx, 3)) for dy in np.arange(-.2, .201, .05) for dx in np.arange(-.2, .201, .05)]
        r = get("https://flood-api.open-meteo.com/v1/flood?" + urllib.parse.urlencode(
            {"latitude": ",".join(str(p[0]) for p in pts), "longitude": ",".join(str(p[1]) for p in pts),
             "daily": "river_discharge", "start_date": "2023-10-01", "end_date": "2023-12-31"}))
        pk = np.array([max([v for v in j["daily"]["river_discharge"] if v is not None] or [0]) for j in json.loads(r)])
        dist = np.array([np.hypot(p[0] - la, (p[1] - lo) * np.cos(np.radians(la))) for p in pts])
        ok = np.where(pk >= 0.5 * pk.max())[0]
        i = int(ok[np.argmin(dist[ok])])
        best[sid] = (float(pts[i][0]), float(pts[i][1]))
        time.sleep(2)
    json.dump(best, open(fn, "w"))
    return best


def rivers():
    meta = {r["id"]: r for r in json.load(open("data/rivers.json"))}
    cells = river_cells()
    out = []
    for sid, (la, lo) in cells.items():
        q = {"latitude": la, "longitude": lo, "forecast_days": 30, "past_days": 61,
             "daily": "river_discharge,river_discharge_median,river_discharge_max,river_discharge_min,"
                      "river_discharge_p25,river_discharge_p75"}
        r = get("https://flood-api.open-meteo.com/v1/flood?" + urllib.parse.urlencode(q))
        if not r:
            return None
        d = json.loads(r)["daily"]
        out.append({"id": sid, "name": meta[sid]["name"], "river": meta[sid]["river"], "lat": la, "lon": lo,
                    **{k.replace("river_discharge", "q") or "q": [r1(v) for v in vals] for k, vals in d.items() if k != "time"},
                    "time": d["time"]})
        time.sleep(1)
    # reference: the 2023 Deyr flood, cached once (it does not change)
    ref_fn = D + "rivers_2023.json"
    if os.path.exists(ref_fn):
        ref = json.load(open(ref_fn))
    else:
        ref = {}
        for sid, (la, lo) in cells.items():
            r = get("https://flood-api.open-meteo.com/v1/flood?" + urllib.parse.urlencode(
                {"latitude": la, "longitude": lo, "daily": "river_discharge",
                 "start_date": "2023-10-01", "end_date": "2024-01-31"}))
            if r:
                d = json.loads(r)["daily"]
                q = [v if v is not None else -1 for v in d["river_discharge"]]
                i = int(np.argmax(q))
                ref[str(sid)] = {"peak": r1(q[i]), "date": d["time"][i]}
            time.sleep(1)
        json.dump(ref, open(ref_fn, "w"))
    for o in out:
        o["ref2023"] = ref.get(str(o["id"]))
    print("rivers", [(o["name"], o["q"][61] if len(o["q"]) > 61 else None, o["ref2023"]) for o in out])
    return out


def marine():
    m = multi("https://marine-api.open-meteo.com/v1/marine", PORTS,
              {"daily": "wave_height_max,swell_wave_height_max,wave_period_max,wave_direction_dominant",
               "forecast_days": 7, "timezone": "Africa/Mogadishu"})
    if m is None:
        return None
    out = [{"name": p[0], "lat": p[1], "lon": p[2], "days": x["daily"]["time"],
            "hs": [r1(v) for v in x["daily"]["wave_height_max"]], "sw": [r1(v) for v in x["daily"]["swell_wave_height_max"]],
            "tp": [r1(v) for v in x["daily"]["wave_period_max"]], "dir": x["daily"]["wave_direction_dominant"]}
           for p, x in zip(PORTS, m)]
    print("marine", [(o["name"], max([v for v in o["hs"] if v is not None], default=None)) for o in out])
    return out


def main():
    os.makedirs(D, exist_ok=True)
    refresh = set(sys.argv[1:]) or {"towns", "rivers", "marine"}
    out = {"built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")}
    for name, fn in [("towns", towns), ("rivers", rivers), ("marine", marine)]:
        p = f"{D}{name}.json"
        if name in refresh or not os.path.exists(p):
            v = fn()
            if v is None:
                sys.exit(f"{name}: fetch failed, nothing written")
            json.dump(v, open(p, "w"), separators=(",", ":"))
        out[name] = json.load(open(p))
        print(name, "ok", flush=True)
    json.dump(out, open("fc.json", "w"), separators=(",", ":"))
    print("fc.json", f"{os.path.getsize('fc.json') / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
