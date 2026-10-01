import json,datetime as dt,statistics as S
exec(open('analyze.py').read().split("# zero-padding")[0])
rows=[]
for c,ser in mrs.items():
    g26=stot(ser,2026,'Gu')
    if g26 is None: continue
    past=[stot(ser,y,'Gu') for y in range(2007,2026)]
    past=[p for p in past if p is not None and p>0]
    if len(past)<8: continue
    med=S.median(past); rows.append((c,mrs_st[c]['station_name'],mrs_st[c]['region'],g26,med,100*g26/med if med else None,len(past)))
rows.sort(key=lambda r:r[5])
p=[r[5] for r in rows]
print(f"Gu 2026 at {len(rows)} gauges with >=8 prior Gu seasons: median {S.median(p):.0f}% of each gauge's own median; below 75%: {sum(x<75 for x in p)}; 75-125%: {sum(75<=x<=125 for x in p)}; above 125%: {sum(x>125 for x in p)}")
for r in rows[:4]+rows[len(rows)//2-1:len(rows)//2+1]+rows[-4:]: print(f"  {r[1]:18} {r[2]:16} {r[3]:6.0f} mm vs median {r[4]:5.0f} ({r[5]:.0f}%, n={r[6]})")
json.dump([dict(zip(['code','name','region','gu26','med','pct','n'],r)) for r in rows],open('gu26.json','w'))
