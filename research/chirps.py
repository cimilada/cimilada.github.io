import rasterio, numpy as np, json, concurrent.futures as cf
from rasterio.windows import from_bounds
B="/vsicurl/https://data.chc.ucsb.edu/products/CHIRPS/v3.0/3-monthly/global/tifs/chirps-v3.0.{y}.{m}.tif"
aws=json.load(open('stations.json')); mrs=json.load(open('mrs_stations.json'))
pts=[(s['station_number'],s['latitude'],s['longitude']) for s in aws+mrs]
def get(arg):
    y,m=arg
    try:
        with rasterio.Env(GDAL_HTTP_MAX_RETRY=3, GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
            with rasterio.open(B.format(y=y,m=m)) as r:
                w=from_bounds(40.5,-2,51.5,12.5,r.transform)
                a=r.read(1,window=w).astype('float32'); a[a<0]=np.nan
                t=r.window_transform(w)
                pv={}
                for c,la,lo in pts:
                    row,col=rasterio.transform.rowcol(t,lo,la)
                    pv[c]=float(a[row,col]) if 0<=row<a.shape[0] and 0<=col<a.shape[1] else None
                return (y,m),a,pv,t
    except Exception as e:
        return (y,m),None,str(e),None
jobs=[(y,m) for y in range(1981,2027) for m in ('040506','101112')]
grids={};points={}
with cf.ThreadPoolExecutor(8) as ex:
    for k,a,pv,t in ex.map(get,jobs):
        if a is None: print('miss',k,pv[:80]); continue
        grids[f"{k[0]}_{k[1]}"]=a; points[f"{k[0]}_{k[1]}"]=pv; T=t
np.savez_compressed('chirps_som.npz',**grids)
json.dump({'points':points,'transform':list(T)[:6]},open('chirps_points.json','w'))
print(len(grids),'grids', next(iter(grids.values())).shape)
