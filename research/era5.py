import json,urllib.request,datetime as dt,statistics as S,math,time
site=json.load(open('/Users/mustafahassan/Projects/swalim-water-balance/site.json'))
def corr(x,y):
    mx,my=S.mean(x),S.mean(y); sx=math.sqrt(sum((a-mx)**2 for a in x)); sy=math.sqrt(sum((b-my)**2 for b in y)); return sum((a-mx)*(b-my) for a,b in zip(x,y))/(sx*sy)
out={};allE=[];allA=[];allP=[];allQ=[]
for s in site['stations']:
    if s['code'] in('AWS_WGABU','AWS_GALKACYO'): continue
    u=f"https://archive-api.open-meteo.com/v1/archive?latitude={s['lat']}&longitude={s['lon']}&start_date={s['first']}&end_date={min(s['last'],'2026-09-15')}&daily=precipitation_sum,et0_fao_evapotranspiration&timezone=Africa%2FNairobi&models=era5"
    for i in range(3):
        try: j=json.load(urllib.request.urlopen(u,timeout=120)); break
        except Exception as e: time.sleep(10); j=None
    if not j: print('fail',s['code']); continue
    f=dt.date.fromisoformat(s['first']); d=j['daily']
    E=[];A=[];P=[];Q=[]
    for t,p,e in zip(d['time'],d['precipitation_sum'],d['et0_fao_evapotranspiration']):
        i=(dt.date.fromisoformat(t)-f).days
        if 0<=i<len(s['E']) and s['E'][i] is not None and e is not None and not s['Ef'][i]: E.append(e);A.append(s['E'][i])
    # monthly rain totals where AWS complete
    mons={}
    for t,p in zip(d['time'],d['precipitation_sum']):
        i=(dt.date.fromisoformat(t)-f).days
        if 0<=i<len(s['P']) and p is not None: mons.setdefault(t[:7],[]).append((s['P'][i],p))
    for m,v in mons.items():
        if len(v)>=28 and all(a is not None for a,_ in v) and s['code']!='AWS_GAROWE': P.append(sum(a for a,_ in v)); Q.append(sum(b for _,b in v))
    allE+=E;allA+=A;allP+=P;allQ+=Q
    out[s['code']]=(S.mean(A),S.mean(E),corr(A,E),len(E))
    print(f"{s['name']:10} ETo AWS {S.mean(A):.2f} ERA5 {S.mean(E):.2f} mm/d r={corr(A,E):.2f} n={len(E)}")
print(f"ALL daily ETo: AWS {S.mean(allA):.2f} ERA5 {S.mean(allE):.2f} bias {100*(S.mean(allE)/S.mean(allA)-1):+.0f}% r={corr(allA,allE):.2f}")
print(f"ALL monthly rain: AWS {S.mean(allP):.1f} ERA5 {S.mean(allQ):.1f} mm/mo r={corr(allP,allQ):.2f} n={len(allP)}")
