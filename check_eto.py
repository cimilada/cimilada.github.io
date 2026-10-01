"""Cross-check process.py ETo against pyet's FAO-56 Penman-Monteith."""
import json, datetime as dt, math
import pandas as pd, pyet
import process as P
raw = json.load(open("raw.json")); stations = json.load(open("stations.json"))
out = []
for s in stations:
    code = s["station_number"]
    c = {k: P.qc(P.daily(raw[code].get(src, []), k), k)[0] for src, k in P.KEY.items()}
    idx = sorted(set(c["T"]) & set(c["RH"]) & set(c["Rs"]) & set(c["U"]) & set(c["pres"]))
    if len(idx) < 100: continue
    df = pd.DataFrame({k: [c[k][d] for d in idx] for k in c if k != "P"}, index=pd.DatetimeIndex(idx))
    z = P.elevation_from_pressure(df.pres.median())
    ref = pyet.pm_fao56(df["T"], df.U / 3.6, rs=df.Rs * 0.0864, rh=df.RH, pressure=df.pres / 10,
                        elevation=z, lat=math.radians(s["latitude"]))
    mine = pd.Series([P.eto(d, s["latitude"], z, c["T"][d], c["RH"][d], c["pres"][d], c["Rs"][d], c["U"][d]) for d in idx], index=df.index)
    diff = (mine - ref)
    out.append((code, len(idx), mine.mean(), ref.mean(), diff.abs().mean()))
    print(f"{code:14} n={len(idx):5} mine {mine.mean():.2f} pyet {ref.mean():.2f} MAE {diff.abs().mean():.3f} mm/d")
