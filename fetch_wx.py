"""Fetch the weather layers for the v2 map and pack them into wx.json.

Ideas taken from God's Eye View (github.com/bilawalsidhu/gods-eye-view, MIT):
animated forecast wind, observed satellite clouds on one timeline with the wind,
cyclone tracks, a satellite basemap and a 3D terrain view. Its sources are
US-centred (GOES, nowCOAST, NHC), so the Horn of Africa equivalents are used:

  grid      NOAA GFS, ECMWF IFS and ECMWF AIFS (AI) via Open-Meteo, 0.5 deg, -24 h to +7 d:
            10 m wind, 3-hour rain and 2 m temperature
  clouds    EUMETSAT Meteosat IODC IR 10.8 um (view.eumetsat.int WMS), past 24 h
  cyclones  IBTrACS v4 North Indian basin since 1980 + GDACS active storms
  terrain   AWS Terrain Tiles (Terrarium; SRTM and other open DEMs), averaged to 0.1 deg
  imagery   Sentinel-2 cloudless 2016 by EOX (CC BY 4.0)

The page cannot fetch anything at view time, so every layer is baked in here.
"""
import base64
import concurrent.futures as cf
import csv
import datetime as dt
import io
import json
import math
import os
import sys
import time
import urllib.parse

import numpy as np
from PIL import Image

from fetch_v2 import get

D = "data/"
W = D + "wx/"
# map extent, must match LON0/LON1/LAT0/LAT1 in template_v2.html
LON0, LON1, LAT0, LAT1 = 40.4, 51.8, -2.0, 12.4
IMG_W = 570                                   # cloud frames: 2 px per map unit (MW=460 is drawn at ~1x)
IMG_H = round(IMG_W * (LAT1 - LAT0) / (LON1 - LON0))
WIND_LON = np.arange(40.0, 52.01, 0.5)        # grid just past the map edge, so particles don't stall at the border
WIND_LAT = np.arange(-2.5, 13.01, 0.5)
WIND_STEP_H = 3


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def img_uri(im, fmt="webp", **kw):
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return f"data:image/{fmt};base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- wind
GRID_MODELS = [("gfs", "gfs_seamless"), ("ecmwf", "ecmwf_ifs025"), ("aifs", "ecmwf_aifs025_single")]


def wind():
    """Forecast grid: 10 m wind, 3-hour rain and 2 m temperature, every 3 h from -24 h to +7 d.

    Stored per model as base64 arrays (time-major, then point, south row first):
      u, v  int8, m/s / scale      p  uint8, 3 h rain mm / 0.25 (255 = missing)
      t     int8, deg C / 0.5 (-128 = missing)
    """
    pts = [(la, lo) for la in WIND_LAT for lo in WIND_LON]
    out = {"lon0": float(WIND_LON[0]), "lat0": float(WIND_LAT[0]), "d": 0.5,
           "nx": len(WIND_LON), "ny": len(WIND_LAT), "step_h": WIND_STEP_H, "scale": 0.25,
           "p_scale": 0.25, "t_scale": 0.5, "models": {}}
    for key, model in GRID_MODELS:
        U, V, PR, TT, times = [], [], [], [], None
        failed = False
        for i in range(0, len(pts), 100):
            chunk = pts[i:i + 100]
            q = urllib.parse.urlencode({
                "latitude": ",".join(f"{p[0]:.2f}" for p in chunk),
                "longitude": ",".join(f"{p[1]:.2f}" for p in chunk),
                "hourly": "wind_speed_10m,wind_direction_10m,precipitation,temperature_2m", "models": model,
                "wind_speed_unit": "ms", "past_days": 1, "forecast_days": 7, "timezone": "GMT"})
            r = get("https://api.open-meteo.com/v1/forecast?" + q)
            if not r:
                failed = True
                break
            js = json.loads(r)
            js = js if isinstance(js, list) else [js]
            for x in js:
                h = x["hourly"]
                arr = lambda k: np.array(h[k], dtype="float64")
                times = times or h["time"][::WIND_STEP_H]
                sp, di = arr("wind_speed_10m")[::WIND_STEP_H], np.radians(arr("wind_direction_10m")[::WIND_STEP_H])
                # meteorological direction is where the wind comes FROM
                U.append(-sp * np.sin(di))
                V.append(-sp * np.cos(di))
                # hourly precipitation is the preceding hour's total, so a step's 3 h rain is that hour and the two before
                pr = arr("precipitation")
                PR.append([np.sum(pr[max(0, k - WIND_STEP_H + 1):k + 1]) for k in range(0, len(pr), WIND_STEP_H)])
                TT.append(arr("temperature_2m")[::WIND_STEP_H])
            time.sleep(1)
        if failed:
            print("grid fail", key, file=sys.stderr)
            if key == "aifs":            # the AI model is optional; the page offers only what was fetched
                continue
            return None
        U, V, PR, TT = (np.array(a).T for a in (U, V, PR, TT))      # (time, point)
        # trailing hours past a model's horizon come back as null -> nan; keep only full wind steps
        ok = ~np.isnan(U).any(1) & ~np.isnan(V).any(1)
        q8 = lambda a, sc: np.clip(np.round(a[ok] / sc), -127, 127).astype("int8")
        p = PR[ok] / out["p_scale"]
        p = np.where(np.isnan(p), 255, np.clip(np.round(p), 0, 254)).astype("uint8")
        t = TT[ok] / out["t_scale"]
        t = np.where(np.isnan(t), -128, np.clip(np.round(t), -127, 127)).astype("int8")
        out["models"][key] = {"t0": [tt for tt, k in zip(times, ok) if k][0], "n": int(ok.sum()),
                              "u": b64(q8(U, out["scale"])), "v": b64(q8(V, out["scale"])), "p": b64(p), "t": b64(t)}
        print("grid", key, int(ok.sum()), "steps, wind max", round(float(np.nanmax(np.hypot(U, V))), 1), "m/s,",
              "rain 3h max", round(float(np.nanmax(PR)), 1), "mm, T", round(float(np.nanmin(TT))), "to",
              round(float(np.nanmax(TT))), "C")
    return out


# ---------------------------------------------------------------- clouds
def clouds(hours=24, every=2):
    caps = get("https://view.eumetsat.int/geoserver/wms?service=WMS&request=GetCapabilities&version=1.3.0")
    import re
    seg = caps.decode()[caps.decode().find("<Name>msg_iodc:ir108</Name>"):]
    latest = re.search(r'<Dimension[^>]*name="time"[^>]*>[^<]*/([0-9T:\-.]+)Z/PT15M<', seg).group(1)
    t1 = dt.datetime.fromisoformat(latest[:19]).replace(minute=0, second=0)
    frames = []
    for k in range(hours // every, -1, -1):
        t = t1 - dt.timedelta(hours=k * every)
        u = ("https://view.eumetsat.int/geoserver/wms?service=WMS&version=1.1.1&request=GetMap"
             f"&layers=msg_iodc:ir108&styles=&srs=EPSG:4326&bbox={LON0},{LAT0},{LON1},{LAT1}"
             f"&width={IMG_W}&height={IMG_H}&format=image/png&time={t:%Y-%m-%dT%H:%M:00Z}")
        r = get(u, tries=3, timeout=90)
        if not r:
            continue
        g = np.asarray(Image.open(io.BytesIO(r)).convert("L"), dtype="float32")
        # IR is bright where cloud tops are cold. Warm ground and sea stay transparent;
        # the ramp starts above the warmest land so the desert does not read as cloud.
        a = np.clip((g - 80) / 130, 0, 1) ** 0.9 * 240
        rgba = np.zeros((*g.shape, 4), "uint8")
        rgba[..., :3] = 255
        rgba[..., 3] = a.astype("uint8")
        frames.append({"t": f"{t:%Y-%m-%dT%H:00}", "src": img_uri(Image.fromarray(rgba, "RGBA"), quality=70)})
        print("cloud", t, f"{len(frames[-1]['src']) / 1e3:.0f} kB")
    return {"w": IMG_W, "h": IMG_H, "frames": frames}


# ---------------------------------------------------------------- cyclones
def inside(pt, poly):
    """Ray-casting point-in-polygon; poly is a list of [lon, lat]."""
    x, y, c = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def cyclones(somalia_polys):
    fn = D + "ibtracs_ni.csv"
    if not os.path.exists(fn) or time.time() - os.path.getmtime(fn) > 7 * 864e2:
        r = get("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-"
                "ibtracs/v04r01/access/csv/ibtracs.NI.list.v04r01.csv", timeout=600)
        if r:
            open(fn, "wb").write(r)
    coast = np.array([pt for p in somalia_polys for pt in p])
    storms = {}
    with open(fn, newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        next(rd)                                                # units row
        ix = {k: head.index(k) for k in ("SID", "SEASON", "NAME", "ISO_TIME", "LAT", "LON", "USA_WIND", "WMO_WIND")}
        for row in rd:
            if int(row[ix["SEASON"]]) < 1980:
                continue
            t = row[ix["ISO_TIME"]]
            if t[11:13] not in ("00", "06", "12", "18"):
                continue
            la, lo = float(row[ix["LAT"]]), float(row[ix["LON"]])
            w = row[ix["USA_WIND"]].strip() or row[ix["WMO_WIND"]].strip()
            s = storms.setdefault(row[ix["SID"]], {"name": row[ix["NAME"]].title(), "y": int(row[ix["SEASON"]]), "p": []})
            s["p"].append([round(lo, 2), round(la, 2), int(float(w)) if w else None, t[:13]])
    keep = []
    for sid, s in storms.items():
        P = np.array([[p[0], p[1]] for p in s["p"]])
        # nearest approach to the Somali coast, flat-earth km (fine at these latitudes)
        dd = np.hypot((P[:, None, 0] - coast[None, :, 0]) * 111 * np.cos(np.radians(P[:, None, 1])),
                      (P[:, None, 1] - coast[None, :, 1]) * 111).min(1)
        if dd.min() > 300:
            continue
        land = any(inside(pt, p) for p in somalia_polys for pt in P)
        ws = [p[2] for p in s["p"] if p[2] is not None]
        keep.append({"sid": sid, "name": "Unnamed" if s["name"] in ("Not_Named", "") else s["name"].split(":")[-1], "y": s["y"],
                     "land": land, "km": int(dd.min()), "vmax": max(ws) if ws else None,
                     "start": s["p"][0][3][:10], "p": [[p[0], p[1], p[2]] for p in s["p"]]})
    keep.sort(key=lambda s: s["start"])
    print("cyclones near Somalia", len(keep), "landfall", sum(s["land"] for s in keep))
    return keep


def active_storms():
    out = []
    today = dt.date.today()
    r = get("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC"
            f"&fromDate={today - dt.timedelta(days=10)}&toDate={today}")
    if not r:
        return out
    for f in json.loads(r).get("features", []):
        pr = f["properties"]
        lo, la = f["geometry"]["coordinates"]
        if not (30 <= lo <= 80 and -15 <= la <= 30) or pr.get("iscurrent") in ("false", False):
            continue
        g = get("https://www.gdacs.org/gdacsapi/api/polygons/getgeometry?eventtype=TC"
                f"&eventid={pr['eventid']}&episodeid={pr['episodeid']}")
        track = []
        if g:
            for gf in json.loads(g).get("features", []):
                if gf["geometry"]["type"] == "Point" and gf["properties"].get("Class", "").startswith("Point_"):
                    track.append([*gf["geometry"]["coordinates"][:2], gf["properties"].get("forecast") in (True, "true")])
        out.append({"name": pr.get("eventname"), "alert": pr.get("alertlevel"), "lon": lo, "lat": la,
                    "from": pr.get("fromdate", "")[:10], "track": track})
    print("active storms", [s["name"] for s in out])
    return out


# ---------------------------------------------------------------- terrain + imagery
def terrain(step=0.1, zoom=8):
    """Elevation from AWS Terrain Tiles (Terrarium PNG: h = R*256 + G + B/256 - 32768), averaged to 0.1 deg."""
    def tile_xy(lon, lat):
        n = 2 ** zoom
        return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    x0, y0 = map(int, tile_xy(LON0, LAT1))
    x1, y1 = map(int, tile_xy(LON1, LAT0))
    tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]

    def one(xy):
        r = get(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{xy[0]}/{xy[1]}.png", timeout=60)
        a = np.asarray(Image.open(io.BytesIO(r)).convert("RGB"), dtype="float64")
        return xy, a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768

    mosaic = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256))
    with cf.ThreadPoolExecutor(6) as ex:
        for (x, y), h in ex.map(one, tiles):
            mosaic[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = h
    lons = np.round(np.arange(LON0, LON1 + 1e-6, step), 2)
    lats = np.round(np.arange(LAT1, LAT0 - 1e-6, -step), 2)    # north row first, like an image
    z = np.zeros((len(lats), len(lons)))
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            # mean over the 0.1 deg cell, so the 3D surface is smooth rather than aliased
            fx0, fy0 = tile_xy(lo - step / 2, la + step / 2)
            fx1, fy1 = tile_xy(lo + step / 2, la - step / 2)
            c0, c1 = int((fx0 - x0) * 256), max(int((fx1 - x0) * 256), int((fx0 - x0) * 256) + 1)
            r0, r1 = int((fy0 - y0) * 256), max(int((fy1 - y0) * 256), int((fy0 - y0) * 256) + 1)
            z[i, j] = mosaic[max(r0, 0):r1, max(c0, 0):c1].mean()
    z = z.clip(0, None)                                         # sea -> 0
    print("terrain", len(tiles), "tiles", z.shape, "max", int(z.max()), "m")
    return {"nx": len(lons), "ny": len(lats), "max": int(z.max()), "z": b64(np.round(z).astype("<u2"))}


def imagery():
    r = get("https://tiles.maps.eox.at/wms?service=WMS&request=GetMap&version=1.1.1&layers=s2cloudless"
            f"&styles=&srs=EPSG:4326&bbox={LON0},{LAT0},{LON1},{LAT1}&width=1140&height=1440&format=image/jpeg")
    im = Image.open(io.BytesIO(r)).convert("RGB")
    src = img_uri(im, quality=72)
    print("imagery", f"{len(src) / 1e6:.2f} MB")
    return src


OPTIONAL = {"clouds": {"w": IMG_W, "h": IMG_H, "frames": []}, "active": []}   # a failure here must not block the deploy


def cached(name, fn, refresh):
    """Each stage is kept in data/wx/<name>.json; rerun with its name on the command line to refresh it."""
    p = f"{W}{name}.json"
    if name not in refresh and os.path.exists(p):
        return json.load(open(p))
    v = fn()
    if v is None or v == {} or (isinstance(v, dict) and v.get("frames") == []):
        if name in OPTIONAL:
            print(f"{name}: fetch failed, page will show it as unavailable", file=sys.stderr)
            return json.load(open(p)) if os.path.exists(p) else OPTIONAL[name]
        sys.exit(f"{name}: fetch failed, nothing written")
    json.dump(v, open(p, "w"), separators=(",", ":"))
    return v


def main():
    os.makedirs(W, exist_ok=True)
    refresh = set(sys.argv[1:]) or {"wind", "clouds", "active"}    # fast-moving layers by default
    shapes = json.load(open("site.json"))["shapes"]
    polys = [p for k in ("SOM", "SOL") for p in shapes.get(k, [])]
    out = {"built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M"),
           "extent": [LON0, LON1, LAT0, LAT1]}
    for name, fn in [("terrain", terrain), ("imagery", imagery), ("cyclones", lambda: cyclones(polys)),
                     ("active", active_storms), ("clouds", clouds), ("wind", wind)]:
        out[name] = cached(name, fn, refresh)
        print(name, "ok", flush=True)
    json.dump(out, open("wx.json", "w"), separators=(",", ":"))
    print("wx.json", f"{os.path.getsize('wx.json') / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
