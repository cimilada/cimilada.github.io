"""Turn raw SWALIM AWS series into a QC'd daily water balance.

Steps per station:
  1. Convert timestamps to East Africa Time dates; aggregate hourly series to daily.
  2. Quality-control each variable (range, spike and consistency checks).
  3. Compute FAO-56 Penman-Monteith reference evapotranspiration (ETo).
  4. Summarise each Somali season: rainfall, ETo, P/ETo, rainy days,
     longest dry spell, and rainy-season onset.
Writes site.json for the dashboard.
"""
import datetime as dt
import json
import math
import statistics as st
from collections import defaultdict

EAT = dt.timedelta(hours=3)
SEASONS = [("Jilaal", 1, 3), ("Gu", 4, 6), ("Hagaa", 7, 9), ("Deyr", 10, 12)]
ONSET_SEARCH = {"Gu": (3, 1), "Deyr": (9, 15)}  # (month, day) search start
KEY = {"rainfall_daily": "P", "temperature_daily": "T", "humidity_daily": "RH",
       "pressure_daily": "pres", "radiation_daily": "Rs", "wind_speed_daily": "U"}


def to_date(ms):
    return (dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) + EAT).date()


def daily(series, var):
    """Group [ms, value] pairs by EAT date. Hourly input is aggregated."""
    if len(series) < 2:
        return {}
    step = st.median(b[0] - a[0] for a, b in zip(series[:500], series[1:501]))
    groups = defaultdict(list)
    for ms, v in series:
        if v is not None:
            groups[to_date(ms)].append(v)
    if step >= 20 * 3600e3:  # already daily
        return {d: vs[0] for d, vs in groups.items()}
    out = {}
    for d, vs in groups.items():
        if var == "P":
            if len(vs) >= 22:
                out[d] = sum(vs)
        elif len(vs) >= 18:
            out[d] = sum(vs) / len(vs)
    return out


def qc(days, var):
    """Return (clean, n_flagged). Rejected values are dropped."""
    if not days:
        return {}, 0
    vals = list(days.values())
    med = st.median(vals)
    clean, bad = {}, 0
    dates = sorted(days)
    for i, d in enumerate(dates):
        v = days[d]
        ok = True
        if var == "P":
            ok = 0 <= v <= 250
        elif var == "T":
            window = [days[x] for x in dates[max(0, i - 15):i + 16]]
            ok = 0 < v < 45 and abs(v - st.median(window)) <= 8
        elif var == "RH":
            ok = 3 <= v <= 100
        elif var == "pres":
            ok = abs(v - med) <= 12
        elif var == "Rs":
            ok = 5 < v <= 400  # daily-mean W/m2
        elif var == "U":
            ok = 0 <= v <= 45  # km/h
        if ok:
            clean[d] = v
        else:
            bad += 1
    return clean, bad


def elevation_from_pressure(hpa):
    """Invert FAO-56 eq. 7 to estimate station elevation (m) from pressure."""
    return 293 / 0.0065 * (1 - (hpa / 1013) ** (1 / 5.26))


def rso(d, lat, z):
    """Clear-sky solar radiation, MJ/m2/day (FAO-56 eqs. 21 and 37)."""
    J = d.timetuple().tm_yday
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * J / 365)
    dec = 0.409 * math.sin(2 * math.pi * J / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(dec))
    Ra = 24 * 60 / math.pi * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    return (0.75 + 2e-5 * z) * Ra


def eto(d, lat, z, T, RH, pres, Rs_wm2, U_kmh):
    """FAO-56 Penman-Monteith daily ETo (mm/day).

    Uses daily mean T and RH (no Tmax/Tmin published). Wind is assumed to be
    km/h measured at 2 m. Soil heat flux G = 0 at daily step.
    """
    J = d.timetuple().tm_yday
    phi = math.radians(lat)
    P = pres / 10
    gamma = 0.000665 * P
    es = 0.6108 * math.exp(17.27 * T / (T + 237.3))
    ea = es * RH / 100
    delta = 4098 * es / (T + 237.3) ** 2
    dr = 1 + 0.033 * math.cos(2 * math.pi * J / 365)
    dec = 0.409 * math.sin(2 * math.pi * J / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(dec))
    Ra = 24 * 60 / math.pi * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    Rso = (0.75 + 2e-5 * z) * Ra
    Rs = Rs_wm2 * 0.0864
    ratio = min(Rs / Rso, 1.0)
    Rnl = 4.903e-9 * (T + 273.16) ** 4 * (0.34 - 0.14 * math.sqrt(ea)) * (1.35 * ratio - 0.35)
    Rn = 0.77 * Rs - Rnl
    u2 = U_kmh / 3.6
    num = 0.408 * delta * Rn + gamma * 900 / (T + 273) * u2 * (es - ea)
    return max(num / (delta + gamma * (1 + 0.34 * u2)), 0.0)


def season_of(d):
    for name, a, b in SEASONS:
        if a <= d.month <= b:
            return name


def onset(P, start, end):
    """First day with >=20 mm in 3 days and no 10-day dry spell in the next 30."""
    d = start
    while d <= end:
        three = [P.get(d + dt.timedelta(i)) for i in range(3)]
        if None not in three and sum(three) >= 20:
            run, spell = 0, False
            for i in range(3, 33):
                v = P.get(d + dt.timedelta(i))
                run = run + 1 if v is not None and v < 1 else 0
                if run >= 10:
                    spell = True
                    break
            if not spell:
                return d
        d += dt.timedelta(1)
    return None


def seasons(P, E, first, asof):
    rows = []
    for y in range(first.year, asof.year + 1):
        for name, a, b in SEASONS:
            s = dt.date(y, a, 1)
            e = dt.date(y + (b == 12), 1 if b == 12 else b + 1, 1) - dt.timedelta(1)
            if e < first or s > asof:
                continue
            end = min(e, asof)
            days = [s + dt.timedelta(i) for i in range((end - s).days + 1)]
            n = (e - s).days + 1
            pv = [P[d] for d in days if d in P]
            ev = [E[d] for d in days if d in E]
            cov = len(pv) / len(days)
            if cov < 0.5:
                continue
            run = longest = 0
            for d in days:
                v = P.get(d)
                run = run + 1 if v is not None and v < 1 else 0
                longest = max(longest, run)
            row = {"y": y, "s": name, "P": round(sum(pv), 1), "cov": round(cov, 2),
                   "rainy": sum(v >= 1 for v in pv), "dry": longest,
                   "prog": end < e, "n": n}
            if len(ev) >= 0.6 * len(days):
                row["E"] = round(st.mean(ev) * len(days), 1)
                row["ratio"] = round(row["P"] / row["E"], 3) if row["E"] else None
            if name in ONSET_SEARCH:
                m, dd = ONSET_SEARCH[name]
                o = onset(P, dt.date(y, m, dd), end)
                row["onset"] = o.isoformat() if o else None
            rows.append(row)
    return rows


def main():
    stations = json.load(open("data/stations.json"))
    raw = json.load(open("data/raw.json"))
    out = []
    asof = None
    per = {}
    for s in stations:
        code = s["station_number"]
        clean, flags, totals = {}, {}, {}
        for src, k in KEY.items():
            d = daily(raw[code].get(src, []), k)
            totals[k] = len(d)
            clean[k], flags[k] = qc(d, k)
        per[code] = (s, clean, flags, totals)
        last = max((max(v) for v in clean.values() if v), default=None)
        if last and (asof is None or last > asof):
            asof = last

    for code, (s, c, flags, totals) in per.items():
        P, T, RH, pres, Rs, U = (c[k] for k in ("P", "T", "RH", "pres", "Rs", "U"))
        pmed = st.median(pres.values()) if pres else 1013
        z = elevation_from_pressure(pmed)
        umed = st.median(U.values()) if U else 7.2
        # Days darker than 20% of clear-sky are a degraded or dirty sensor,
        # not weather: even heavy overcast in the tropics passes ~25%.
        for d in list(Rs):
            if Rs[d] * 0.0864 < 0.2 * rso(d, s["latitude"], z):
                del Rs[d]
                flags["Rs"] += 1
        # Radiation sensors fail more often than the rest; fill gaps with the
        # station's own monthly median so ETo stays available (flagged in Ef).
        by_month = defaultdict(list)
        for d, v in Rs.items():
            by_month[d.month].append(v)
        rs_clim = {m: st.median(v) for m, v in by_month.items() if len(v) >= 20}
        E, filled = {}, set()
        for d in T:
            rs = Rs.get(d)
            if rs is None and d.month in rs_clim:
                rs = rs_clim[d.month]
                filled.add(d)
            if d in RH and rs is not None:
                E[d] = eto(d, s["latitude"], z, T[d], RH[d], pres.get(d, pmed), rs, U.get(d, umed))
        alld = set().union(*[set(v) for v in c.values()])
        if not alld:
            continue
        first, last = min(alld), max(alld)
        n = (last - first).days + 1
        dates = [first + dt.timedelta(i) for i in range(n)]
        r1 = lambda m, d: round(m[d], 1) if d in m else None
        y365 = [asof - dt.timedelta(i) for i in range(365)]
        l30 = [asof - dt.timedelta(i) for i in range(30)]
        out.append({
            "code": code, "name": s["station_name"], "region": s["region"],
            "district": s["district"], "state": s["station_state"],
            "status": s["station_status"], "lat": s["latitude"], "lon": s["longitude"],
            "elev": round(z), "first": first.isoformat(), "last": last.isoformat(),
            "lag": (asof - last).days,
            "cov365": round(sum(d in P for d in y365) / 365, 3),
            "qc": {k: [flags[k], totals[k]] for k in flags},
            "l30": {"P": round(sum(P.get(d, 0) for d in l30), 1),
                    "E": round(sum(E[d] for d in l30 if d in E), 1),
                    "nP": sum(d in P for d in l30), "nE": sum(d in E for d in l30)},
            "start": first.isoformat(),
            "P": [r1(P, d) for d in dates], "E": [r1(E, d) for d in dates],
            "T": [r1(T, d) for d in dates],
            "Ef": [1 if d in filled else 0 for d in dates],
            "rsFilled": len(filled),
            "seasons": seasons(P, E, first, asof),
        })
        print(f"{code:14} {first}..{last} z~{z:5.0f}m ETo med "
              f"{st.median(E.values()) if E else float('nan'):.2f}  flags {sum(flags.values())}")

    # A season of exactly 0 mm while the rest of the network had rain points
    # to a blocked or disconnected gauge rather than a true drought.
    pool = defaultdict(list)
    for o in out:
        for r in o["seasons"]:
            if r["cov"] >= 0.8 and not r["prog"]:
                pool[(r["y"], r["s"])].append(r["P"])
    for o in out:
        for r in o["seasons"]:
            vals = pool.get((r["y"], r["s"]), [])
            if len(vals) >= 5:
                r["net"] = round(st.median(vals), 1)
                if r["P"] == 0 and r["cov"] >= 0.8 and r["net"] >= 40:
                    r["zero"] = True

    ne = json.load(open("data/ne50.json"))
    shapes = {}
    for f in ne["features"]:
        a3 = f["properties"]["ADM0_A3"]
        if a3 in ("SOM", "SOL", "ETH", "KEN", "DJI"):
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            shapes[a3] = [[[round(x, 2), round(y, 2)] for x, y in poly[0]] for poly in polys]
    json.dump({"asof": asof.isoformat(), "stations": out, "shapes": shapes},
              open("site.json", "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
