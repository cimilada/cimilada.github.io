"""Build site2.json for the v2 dashboard.

Rain comes first from SWALIM's manual gauges, then the AWS network (cross-checked
against nearby gauges). Seasons are expressed as % of the CHIRPS v3 1991-2020
normal at each station. ETo uses AWS sensors where valid and NASA POWER,
calibrated against the AWS, everywhere else. Forecast layers: a statistical
Deyr model on ENSO/IOD, ECMWF SEAS5, and CHIRPS3-GEFS 16-day. Flood watch
uses SWALIM FRRIMS river levels.
"""
import datetime as dt
import json
import math
import statistics as st
from collections import defaultdict

import numpy as np
from matplotlib.path import Path

import process as P1

D = "data/"
SINCE = dt.date(2016, 1, 1)          # start of the daily arrays shipped to the page
NORMAL = range(1991, 2021)           # WMO standard normal period
SEA_CODE = {"Gu": "040506", "Deyr": "101112"}
BOM = {"date": "2026-09-13", "nino": 2.51, "iod": 0.65, "iod_son": 0.9}  # BoM weekly update
REGION_FIX = {"W.Galbeed": "Woqooyi Galbeed", "Waqooyi Galbeed": "Woqooyi Galbeed",
              "Maroodijeh": "Woqooyi Galbeed", "Lower Shabbelle": "Lower Shabelle",
              "Middle Shebelle": "Middle Shabelle", "Mogadishu": "Banadir"}
AWS_REGION = {"AWS_BELETWENE": "Hiraan", "AWS_BOSASO": "Bari", "AWS_DOLOOW": "Gedo", "AWS_BADHAN": "Sanaag",
              "AWS_BURAO": "Togdheer", "AWS_EREGAVO": "Sanaag", "AWS_HOBYO": "Mudug", "AWS_MOGADISHU": "Banadir",
              "AWS_BOORAMA": "Awdal", "AWS_HUDUR": "Bakool", "AWS_ABUDWAQ": "Galgaduud",
              "AWS_GURICEEL": "Galgaduud", "AWS_DHOBLEY": "Lower Juba", "AWS_QARDHO": "Bari",
              "AWS_GAROWE": "Nugaal", "AWS_DUSMEREB": "Galgaduud", "AWS_GALKACYO": "Mudug",
              "AWS_HARGEISA": "Woqooyi Galbeed", "AWS_KISMAYO": "Lower Juba", "AWS_WGABU": "Woqooyi Galbeed"}
PAN_PAIRS = {"SS_WGHAR": "AWS_HARGEISA", "SS_TGBUR": "AWS_BURAO", "SS_NUGAR": "AWS_GAROWE", "SS_BAQAR": "AWS_QARDHO"}


def fix_coords(s):
    la, lo = s.get("latitude"), s.get("longitude")
    if not isinstance(la, (int, float)) or not isinstance(lo, (int, float)):
        return None
    if lo > 1000:
        lo = lo / 1e5
    return (la, lo) if -3 < la < 13 and 40 < lo < 52 else None


def num(x):
    return [p for p in x if isinstance(p, list) and len(p) == 2 and isinstance(p[0], (int, float)) and p[0] > 1e11]


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else None


def season_total(series, y, name, need=0.95):
    a, b = {"Gu": (4, 6), "Deyr": (10, 12)}[name]
    s = dt.date(y, a, 1)
    e = dt.date(y + (b == 12), 1 if b == 12 else b + 1, 1) - dt.timedelta(1)
    days = [s + dt.timedelta(i) for i in range((e - s).days + 1)]
    v = [series[d] for d in days if d in series]
    return sum(v) if len(v) >= need * len(days) else None


# ---------------------------------------------------------------- grids / CHIRPS
class Grid:
    def __init__(self):
        self.g = np.load(D + "chirps_som.npz")
        t = json.load(open(D + "chirps_points.json"))["transform"]
        self.t = t
        a = self.g["1981_101112"]
        self.H, self.W = a.shape
        ne = json.load(open(D + "ne50.json"))
        polys = [f["geometry"]["coordinates"][0] for f in ne["features"] if f["properties"]["ADM0_A3"] in ("SOM", "SOL")]
        xs = t[2] + t[0] * (np.arange(self.W) + .5)
        ys = t[5] + t[4] * (np.arange(self.H) + .5)
        X, Y = np.meshgrid(xs, ys)
        pts = np.c_[X.ravel(), Y.ravel()]
        m = np.zeros(self.H * self.W, bool)
        for p in polys:
            m |= Path(p).contains_points(pts)
        self.mask = m.reshape(self.H, self.W)

    def rc(self, la, lo):
        return int((la - self.t[5]) / self.t[4]), int((lo - self.t[2]) / self.t[0])

    def at(self, key, la, lo):
        r, c = self.rc(la, lo)
        a = self.g[key]
        if not (0 <= r < self.H and 0 <= c < self.W):
            return None
        v = a[r, c]
        if np.isnan(v):  # coastal gauge: take the nearest land cell mean in a 3x3 block
            blk = a[max(0, r - 1):r + 2, max(0, c - 1):c + 2]
            v = np.nanmean(blk) if np.isfinite(blk).any() else np.nan
        return None if np.isnan(v) else float(v)

    def pack(self, a, step=2, scale=1):
        """Downsample to 0.1 deg, mask to Somalia, encode as ints (-1 = none)."""
        H, W = a.shape[0] // step, a.shape[1] // step
        b = a[:H * step, :W * step].reshape(H, step, W, step)
        m = self.mask[:H * step, :W * step].reshape(H, step, W, step).any(axis=(1, 3))
        with np.errstate(all="ignore"):
            v = np.nanmean(b, axis=(1, 3))
        v[~m | ~np.isfinite(v)] = -1
        return {"w": W, "h": H, "x0": self.t[2], "y0": self.t[5], "dx": self.t[0] * step, "dy": self.t[4] * step,
                "v": [int(round(x * scale)) if x >= 0 else -1 for x in v.ravel()]}


def read_index(fn, miss):
    out = {}
    for line in open(D + fn).read().split("\n")[1:]:
        t = line.split()
        if len(t) == 13 and t[0].isdigit():
            for m, x in enumerate(t[1:], 1):
                x = float(x)
                if x > miss:
                    out[(int(t[0]), m)] = x
    return out


def deyr_model(G, nino, dmi):
    yrs = list(range(1981, 2026))
    area = [float(np.nanmean(G.g[f"{y}_101112"][G.mask])) for y in yrs]
    son = lambda idx, y: np.mean([idx[(y, m)] for m in (9, 10, 11)]) if all((y, m) in idx for m in (9, 10, 11)) else None
    rows = [(y, a, son(nino, y), son(dmi, y)) for y, a in zip(yrs, area)]
    rows = [r for r in rows if r[2] is not None and r[3] is not None]
    N = np.array([r[2] for r in rows]); Dm = np.array([r[3] for r in rows]); R = np.array([r[1] for r in rows])
    X = np.c_[np.ones(len(R)), N, Dm]
    b = np.linalg.lstsq(X, R, rcond=None)[0]
    loo = []
    for i in range(len(R)):
        k = np.ones(len(R), bool); k[i] = False
        bi = np.linalg.lstsq(X[k], R[k], rcond=None)[0]
        loo.append(float(bi @ X[i]))
    t1, t2 = np.percentile(R, [100 / 3, 200 / 3])
    cat = lambda v: 0 if v < t1 else (2 if v > t2 else 1)
    hit = float(np.mean([cat(p) == cat(r) for p, r in zip(loo, R)]))
    resid = R - X @ b
    mean = float(R.mean())
    scen = [(1.9, 0.6), (2.3, 0.9), (2.7, 1.1)]
    proj = [float(b @ [1, n, d]) for n, d in scen]
    elnino = [r[0] for r in rows if r[2] >= 1.0]
    return {
        "rows": [{"y": y, "rain": round(a, 1), "nino": round(n, 2), "dmi": round(d, 2), "loo": round(p, 1)}
                 for (y, a, n, d), p in zip(rows, loo)],
        "coef": [round(float(x), 2) for x in b], "rN": corr(N, R), "rD": corr(Dm, R), "loo_r": corr(loo, R),
        "hit": hit, "t1": float(t1), "t2": float(t2), "mean": mean, "median": float(np.median(R)),
        "sd": float(resid.std(ddof=3)), "scen": [{"nino": n, "dmi": d, "rain": round(p, 1)} for (n, d), p in zip(scen, proj)],
        "elnino": elnino, "elnino_above_median": sum(R[[r[0] for r in rows].index(y)] > np.median(R) for y in elnino),
        "max_nino": float(N.max()), "max_dmi": float(Dm.max()),
    }


# ---------------------------------------------------------------- ETo from POWER
def power_eto():
    pw = json.load(open(D + "power.json"))
    out = {}
    for key, par in pw.items():
        if not isinstance(par, dict):
            continue
        la, lo = map(float, key.split(","))
        T, RH, U, Rs, PS = (par[k] for k in ("T2M", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN", "PS"))
        ps = [v for v in PS.values() if v > 0]
        z = P1.elevation_from_pressure(st.median(ps) * 10) if ps else 0
        e = {}
        for k in T:
            vals = (T[k], RH[k], U[k], Rs[k], PS[k])
            if min(vals) <= -900 or vals[3] <= 0:
                continue
            d = dt.date(int(k[:4]), int(k[4:6]), int(k[6:]))
            e[d] = P1.eto(d, la, z, T[k], RH[k], PS[k] * 10, Rs[k] / 0.0864, U[k] * 3.6)
        out[key] = e
    return {code: out.get(key) for code, key in pw.items() if not isinstance(key, dict)}


# ---------------------------------------------------------------- main
def main():
    G = Grid()
    nino, dmi = read_index("nino34.txt", -90), read_index("dmi.txt", -900)
    v1 = json.load(open("site.json"))            # v1 pipeline output: QC'd AWS daily + seasons
    aws_meta = {s["station_number"]: s for s in json.load(open(D + "stations.json"))}
    mrs_meta = {s["station_number"]: s for s in json.load(open(D + "mrs_stations.json"))}
    mrs_raw = json.load(open(D + "mrs_raw.json"))
    seas5 = json.load(open(D + "seas5.json"))
    PE = power_eto()
    gefs = np.load(D + "gefs.npz")
    gt = gefs["transform"]

    day = lambda ms: (dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) + P1.EAT).date()

    # --- rain series
    rain, meta = {}, {}
    for s in v1["stations"]:
        f = dt.date.fromisoformat(s["first"])
        rain[s["code"]] = {f + dt.timedelta(i): v for i, v in enumerate(s["P"]) if v is not None}
        m = aws_meta[s["code"]]
        meta[s["code"]] = {"net": "AWS", "name": s["name"], "status": s["status"],
                           "region": AWS_REGION.get(s["code"]), "state": m.get("station_state"),
                           "district": m.get("district"), "coords": fix_coords(m), "v1": s}
    rejected = defaultdict(int)
    for code, v in mrs_raw.items():
        ser = {}
        for ms, x in num(v.get("rainfall_daily", [])):
            if x is None:
                continue
            if 0 <= x <= 300:
                ser[day(ms)] = x
            else:
                rejected[code] += 1
        if not ser:
            continue
        m = mrs_meta[code]
        rain[code] = ser
        meta[code] = {"net": "Gauge", "name": m["station_name"], "status": m["station_status"],
                      "region": REGION_FIX.get(m.get("region"), m.get("region")), "state": m.get("station_state"),
                      "district": m.get("district"), "coords": fix_coords(m)}
    asof = max(max(s) for s in rain.values())

    # --- ETo series: AWS measured (not radiation-filled) where valid, else POWER x calibration
    aws_E = {}
    for s in v1["stations"]:
        f = dt.date.fromisoformat(s["first"])
        aws_E[s["code"]] = {f + dt.timedelta(i): v for i, (v, fl) in enumerate(zip(s["E"], s["Ef"])) if v is not None and not fl}
    ratios_m = defaultdict(list); pairs_all = []
    for code, E in aws_E.items():
        pe = PE.get(code) or {}
        for d, v in E.items():
            if d in pe and pe[d] > 0:
                ratios_m[d.month].append(v / pe[d]); pairs_all.append((v, pe[d]))
    cal = {m: st.median(v) for m, v in ratios_m.items()}
    power_check = {"r": corr([a for a, _ in pairs_all], [b for _, b in pairs_all]),
                   "aws": st.mean(a for a, _ in pairs_all), "power": st.mean(b for _, b in pairs_all),
                   "n": len(pairs_all), "cal": {m: round(v, 3) for m, v in sorted(cal.items())}}
    # skill after calibration
    cal_pairs = [(a, b * cal[d.month]) for code, E in aws_E.items() for d, a in E.items()
                 for b in [(PE.get(code) or {}).get(d)] if b]
    power_check["r_cal"] = corr([a for a, _ in cal_pairs], [b for _, b in cal_pairs])
    power_check["mae_cal"] = float(np.mean([abs(a - b) for a, b in cal_pairs]))
    power_check["bias_cal"] = float(np.mean([b for _, b in cal_pairs]) / np.mean([a for a, _ in cal_pairs]) - 1)

    etos, esrc = {}, {}
    for code in rain:
        pe = PE.get(code) or {}
        E = dict((d, v * cal.get(d.month, 1)) for d, v in pe.items())
        src = {d: "p" for d in E}
        for d, v in aws_E.get(code, {}).items():
            E[d] = v; src[d] = "m"
        etos[code], esrc[code] = E, src

    # --- pan evaporation check at synoptic stations
    ss_raw = json.load(open(D + "ss_raw.json"))
    pan = []
    for sc, ac in PAN_PAIRS.items():
        ep = {day(ms): x for ms, x in num(ss_raw.get(sc, {}).get("evaporation_daily", [])) if x is not None and 0 < x < 25}
        common = [d for d in aws_E.get(ac, {}) if d in ep]
        # pan readings are noisy day to day; compare monthly means (>= 20 shared days)
        mon = defaultdict(list)
        for d in common:
            mon[(d.year, d.month)].append((aws_E[ac][d], ep[d]))
        mm = [(st.mean(a for a, _ in v), st.mean(b for _, b in v)) for v in mon.values() if len(v) >= 20]
        if len(mm) >= 6:
            pan.append({"site": meta[ac]["name"], "n": len(common), "months": len(mm),
                        "kp": round(st.mean(aws_E[ac][d] for d in common) / st.mean(ep[d] for d in common), 2),
                        "r_day": round(corr([aws_E[ac][d] for d in common], [ep[d] for d in common]), 2),
                        "r": round(corr([a for a, _ in mm], [b for _, b in mm]), 2)})

    # --- station records
    stations = []
    netmed = defaultdict(list)
    per = {}
    for code, P in rain.items():
        m = meta[code]
        first, last = min(P), max(P)
        seas = P1.seasons(P, etos[code], first, asof)
        for r in seas:
            if r["s"] in SEA_CODE and r["cov"] >= 0.8 and not r["prog"]:
                netmed[(r["y"], r["s"])].append(r["P"])
        per[code] = seas
    for code, P in rain.items():
        m = meta[code]
        c = m["coords"]
        seas = per[code]
        first, last = min(P), max(P)
        chirps = {}
        normals = {}
        if c:
            for sn, k in SEA_CODE.items():
                vals = [G.at(f"{y}_{k}", *c) for y in range(1981, 2026)]
                chirps[sn] = [None if v is None else round(v) for v in vals]
                nv = [v for y, v in zip(range(1981, 2026), vals) if y in NORMAL and v is not None]
                normals[sn] = st.mean(nv) if len(nv) >= 25 else None
        for r in seas:
            vals = netmed.get((r["y"], r["s"]), [])
            if len(vals) >= 5:
                r["net"] = round(st.median(vals), 1)
            ch = chirps.get(r["s"], [None] * 45)[r["y"] - 1981] if 1981 <= r["y"] <= 2025 and r["s"] in chirps else None
            if ch is not None:
                r["chirps"] = ch
            if r["P"] == 0 and r["cov"] >= 0.8 and ((ch or 0) >= 100 or r.get("net", 0) >= 40):
                r["zero"] = True
            nrm = normals.get(r["s"])
            if nrm and r["cov"] >= 0.8 and not r.get("zero"):
                r["norm"] = round(nrm)
                r["pct"] = round(100 * r["P"] / nrm) if not r["prog"] else None
        # SEAS5 Deyr 2026
        f5 = None
        s5 = seas5.get(code)
        if s5 and c:
            idx = [i for i, t in enumerate(s5["time"]) if t[:7] in ("2026-10", "2026-11", "2026-12")]
            if len(idx) == 3 and all(s5["mean"][i] is not None for i in idx):
                tot = sum(s5["mean"][i] for i in idx) * 1.0
                an = sum(s5["anom"][i] for i in idx)
                mclim = tot - an
                f5 = {"mm": round(tot), "anom": round(an), "pct": round(100 * tot / mclim) if mclim > 5 else None,
                      "months": [round(s5["mean"][i]) for i in idx]}
        g16 = None
        if c:
            r_, c_ = int((c[0] - gt[5]) / gt[4]), int((c[1] - gt[2]) / gt[0])
            a = gefs["grid"]
            if 0 <= r_ < a.shape[0] and 0 <= c_ < a.shape[1]:
                blk = a[max(0, r_ - 1):r_ + 2, max(0, c_ - 1):c_ + 2]
                g16 = round(float(np.nanmean(blk)), 1) if np.isfinite(blk).any() else None
        # daily arrays from SINCE
        d0 = max(first, SINCE)
        n = (asof - d0).days + 1
        dates = [d0 + dt.timedelta(i) for i in range(n)]
        E, S = etos[code], esrc[code]
        y365 = [asof - dt.timedelta(i) for i in range(365)]
        rec = {
            "code": code, "net": m["net"], "name": m["name"], "status": m["status"], "region": m["region"],
            "state": m["state"], "district": m["district"],
            "lat": c[0] if c else None, "lon": c[1] if c else None,
            "first": first.isoformat(), "last": last.isoformat(), "lag": (asof - last).days,
            "cov365": round(sum(d in P for d in y365) / 365, 3), "rejected": rejected.get(code, 0),
            "d0": d0.isoformat(),
            "P": [None if d not in P else round(P[d] * 10) for d in dates],
            "E": [None if d not in E else round(E[d] * 10) for d in dates],
            "Es": "".join(S.get(d, "-") for d in dates),
            "seasons": seas, "chirps": chirps, "normal": {k: (round(v) if v else None) for k, v in normals.items()},
            "seas5": f5, "gefs16": g16,
        }
        if m["net"] == "AWS":
            v = m["v1"]
            rec.update({"qc": v["qc"], "rsFilled": v["rsFilled"], "elev": v["elev"]})
        stations.append(rec)

    # --- AWS vs nearest gauge rain cross-check
    def km(a, b):
        return 111 * math.hypot(a["lat"] - b["lat"], (a["lon"] - b["lon"]) * math.cos(math.radians(a["lat"])))
    gauges = [s for s in stations if s["net"] == "Gauge" and s["lat"] is not None]
    for s in stations:
        if s["net"] != "AWS" or s["lat"] is None:
            continue
        g = min(gauges, key=lambda x: km(s, x))
        d = km(s, g)
        if d > 15:
            continue
        pa = []
        for sn in SEA_CODE:
            for y in range(2021, 2027):
                a, b = season_total(rain[s["code"]], y, sn), season_total(rain[g["code"]], y, sn)
                if a is not None and b is not None and (a + b) > 20:
                    pa.append([f"{sn} {y}", round(a), round(b)])
        if pa:
            ta, tb = sum(p[1] for p in pa), sum(p[2] for p in pa)
            s["xcheck"] = {"gauge": g["code"], "gname": g["name"], "km": round(d, 1), "pairs": pa,
                           "ratio": round(ta / tb, 2) if tb else None}

    # --- region x season % of normal (gauges only)
    cols = [(y, sn) for y in range(2005, asof.year + 1) for sn in ("Gu", "Deyr")
            if dt.date(y, 4 if sn == "Gu" else 10, 1) <= asof]
    byreg = defaultdict(lambda: defaultdict(list))
    reglat = defaultdict(list)
    for s in stations:
        if s["net"] != "Gauge" or not s["region"]:
            continue
        if s["lat"] is not None:
            reglat[s["region"]].append(s["lat"])
        for r in s["seasons"]:
            if r.get("pct") is not None:
                byreg[s["region"]][(r["y"], r["s"])].append(r["pct"])
    regions = sorted([r for r in byreg if reglat[r]], key=lambda r: -st.mean(reglat[r]))
    heat = {"cols": [f"{sn} {y}" for y, sn in cols], "rows": []}
    for rg in regions:
        heat["rows"].append({"region": rg, "v": [
            [round(st.median(byreg[rg][c])), len(byreg[rg][c])] if byreg[rg].get(c) else None for c in cols]})

    # --- network summaries
    gu26 = [r["pct"] for s in stations if s["net"] == "Gauge" for r in s["seasons"]
            if r["y"] == 2026 and r["s"] == "Gu" and r.get("pct") is not None]
    f5p = [s["seas5"]["pct"] for s in stations if s["seas5"] and s["seas5"]["pct"]]
    rivers = json.load(open(D + "rivers.json"))
    rivers = [r for r in rivers if r["cur"]]

    # --- validation of gauges / AWS against CHIRPS
    def vs_chirps(net):
        X, Y = [], []
        for s in stations:
            if s["net"] != net or s["code"] == "AWS_GAROWE":
                continue
            for r in s["seasons"]:
                if "chirps" in r and r["cov"] >= 0.95 and not r.get("zero") and r["s"] in SEA_CODE and not r["prog"]:
                    X.append(r["P"]); Y.append(r["chirps"])
        return {"n": len(X), "r": corr(X, Y), "bias": float(np.mean(Y) / np.mean(X) - 1) if X else None}

    model = deyr_model(G, nino, dmi)
    idx_series = {
        "nino": [[f"{y}-{m:02d}", v] for (y, m), v in sorted(nino.items()) if y >= 2023],
        "dmi": [[f"{y}-{m:02d}", v] for (y, m), v in sorted(dmi.items()) if y >= 2023],
    }
    comp = np.load(D + "deyr_elnino_pct.npy")
    shapes = json.load(open("site.json"))["shapes"]
    out = {
        "asof": asof.isoformat(), "built": dt.date.today().isoformat(),
        "stations": stations, "heat": heat, "model": model, "indices": idx_series, "bom": BOM,
        "grids": {"elnino": G.pack(comp), "gefs": G.pack(gefs["grid"], scale=1), "gefs_start": str(gefs["start"])},
        "rivers": rivers, "pan": pan, "power": power_check,
        "valid": {"gauge": vs_chirps("Gauge"), "aws": vs_chirps("AWS")},
        "summary": {"gu26_median_pct": st.median(gu26) if gu26 else None, "gu26_n": len(gu26),
                    "gu26_below75": sum(p < 75 for p in gu26),
                    "seas5_median_pct": st.median(f5p) if f5p else None, "seas5_n": len(f5p),
                    "seas5_wet": sum(p >= 125 for p in f5p)},
        "shapes": shapes,
    }
    json.dump(out, open("site2.json", "w"), separators=(",", ":"), default=float)
    print("asof", asof, "stations", len(stations), "gauges", sum(s["net"] == "Gauge" for s in stations))
    print("power", {k: v for k, v in power_check.items() if k != "cal"})
    print("pan", pan)
    print("valid", out["valid"])
    print("summary", out["summary"])
    print("model", {k: model[k] for k in ("coef", "rN", "rD", "loo_r", "hit", "mean", "median", "sd", "scen", "elnino", "elnino_above_median")})
    print("heat rows", [r["region"] for r in heat["rows"]])
    print("xcheck", [(s["name"], s["xcheck"]["gname"], s["xcheck"]["ratio"]) for s in stations if "xcheck" in s])


if __name__ == "__main__":
    main()
