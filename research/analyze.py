import json,datetime as dt,statistics as S,math,collections
def num(x): return [p for p in x if isinstance(p,list) and len(p)==2 and isinstance(p[0],(int,float)) and p[0]>1e11]
day=lambda ms:(dt.datetime.fromtimestamp(ms/1000,dt.UTC)+dt.timedelta(hours=3)).date()
mrs_st={s['station_number']:s for s in json.load(open('mrs_stations.json'))}
mrs={c:{day(p[0]):p[1] for p in num(v.get('rainfall_daily',[])) if p[1] is not None and 0<=p[1]<=300} for c,v in json.load(open('mrs_raw.json')).items()}
site=json.load(open('/Users/mustafahassan/Projects/swalim-water-balance/site.json'))
aws={}
for s in site['stations']:
    f=dt.date.fromisoformat(s['first']); aws[s['code']]={f+dt.timedelta(i):v for i,v in enumerate(s['P']) if v is not None}
awsst={s['code']:s for s in site['stations']}
cp=json.load(open('chirps_points.json'))['points']
SEA={'Gu':(4,6,'040506'),'Deyr':(10,12,'101112')}
def stot(series,y,sn):
    a,b,_=SEA[sn]; s=dt.date(y,a,1); e=dt.date(y+(b==12),1 if b==12 else b+1,1)-dt.timedelta(1)
    n=(e-s).days+1; v=[series[s+dt.timedelta(i)] for i in range(n) if s+dt.timedelta(i) in series]
    return (sum(v) if len(v)>=0.95*n else None)
def corr(x,y):
    mx,my=S.mean(x),S.mean(y); sx=math.sqrt(sum((a-mx)**2 for a in x)); sy=math.sqrt(sum((b-my)**2 for b in y))
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/(sx*sy) if sx and sy else float('nan')
# zero-padding check: gauges with zero seasons when CHIRPS says wet
print('== gauge completeness sanity: seasons where gauge=0 but CHIRPS>=100mm')
bad=collections.Counter(); tot=0
for c,ser in mrs.items():
    for y in range(1998,2026):
        for sn in SEA:
            g=stot(ser,y,sn); ch=cp.get(f"{y}_{SEA[sn][2]}",{}).get(c)
            if g is None or ch is None: continue
            tot+=1
            if g==0 and ch>=100: bad[c]+=1
print(' station-seasons',tot,'suspect zero',sum(bad.values()),'stations',len(bad),bad.most_common(6))
# gauge vs CHIRPS
def compare(name,src,getst):
    X=[];Y=[]
    for c,ser in src.items():
        for y in range(1998,2026):
            for sn in SEA:
                g=stot(ser,y,sn); ch=cp.get(f"{y}_{SEA[sn][2]}",{}).get(c)
                if g is None or ch is None or (g==0 and ch>=100): continue
                X.append(g);Y.append(ch)
    lg=[math.log1p(a) for a in X]; lc=[math.log1p(b) for b in Y]
    print(f'== {name} vs CHIRPS v3 seasonal totals: n={len(X)} r={corr(X,Y):.2f} r(log)={corr(lg,lc):.2f} mean gauge {S.mean(X):.0f} mm, CHIRPS {S.mean(Y):.0f} mm, bias {100*(S.mean(Y)/S.mean(X)-1):+.0f}%  MAE {S.mean(abs(a-b) for a,b in zip(X,Y)):.0f} mm')
compare('Manual gauges',mrs,None)
compare('AWS (QC)',{k:v for k,v in aws.items() if k!='AWS_GAROWE'},None)
# co-located AWS vs gauge (<15 km)
print('== co-located AWS vs manual gauge (seasons with >=95% days both)')
def km(a,b): return 111*math.hypot(a['latitude' if 'latitude' in a else 'lat']-b['lat'],(a['longitude']-b['lon'])*math.cos(math.radians(b['lat'])))
for ac,a in awsst.items():
    best=min(mrs_st.values(),key=lambda m:km(m,a))
    d=km(best,a)
    if d>15: continue
    pairs=[(sn,y,stot(aws[ac],y,sn),stot(mrs[best['station_number']],y,sn)) for y in range(2021,2027) for sn in SEA]
    pairs=[p for p in pairs if p[2] is not None and p[3] is not None]
    if pairs: print(f" {a['name']:10} ~{best['station_name']} {d:4.1f} km: "+'  '.join(f"{sn[0]}{y%100}:{p:.0f}/{q:.0f}" for sn,y,p,q in pairs))
json.dump({'mrs_ok':True},open('an.json','w'))
print('== AWS / gauge / CHIRPS at co-located sites')
for ac,gc in [('AWS_BELETWENE','MRS_HIBEL'),('AWS_MOGADISHU',None),('AWS_BOORAMA',None),('AWS_HARGEISA','MRS_WGHAR')]:
    a=awsst[ac]; best=gc or min(mrs_st.values(),key=lambda m:km(m,a))['station_number']
    out=[]
    for y in range(2021,2026):
        for sn in SEA:
            p=stot(aws[ac],y,sn)
            if p is None: continue
            q=stot(mrs.get(best,{}),y,sn); ch=cp.get(f"{y}_{SEA[sn][2]}",{}).get(ac)
            out.append(f"{sn[0]}{y%100} {p:.0f}/{q if q is None else round(q)}/{ch:.0f}")
    print(f" {a['name']:10} AWS/gauge/CHIRPS: "+' | '.join(out))
