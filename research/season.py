import numpy as np, json
from matplotlib.path import Path
g=np.load('chirps_som.npz'); T=json.load(open('chirps_points.json'))['transform']
ne=json.load(open('/Users/mustafahassan/Projects/swalim-water-balance/ne50.json'))
polys=[f['geometry']['coordinates'][0] for f in ne['features'] if f['properties']['ADM0_A3'] in('SOM','SOL')]
H,W=g['1981_101112'].shape
xs=T[2]+T[0]*(np.arange(W)+.5); ys=T[5]+T[4]*(np.arange(H)+.5)
X,Y=np.meshgrid(xs,ys); pts=np.c_[X.ravel(),Y.ravel()]
mask=np.zeros(H*W,bool)
for p in polys: mask|=Path(p).contains_points(pts)
mask=mask.reshape(H,W)
def idx(fn,months,miss):
    d={}
    for l in open(fn).read().split('\n')[1:]:
        t=l.split()
        if len(t)==13 and t[0].isdigit():
            v=[float(x) for x in t[1:]]
            m=[v[i-1] for i in months]
            if all(x>miss for x in m): d[int(t[0])]=float(np.mean(m))
    return d
nino=lambda ms: idx('nino34.txt',ms,-90); dmi=lambda ms: idx('dmi.txt',ms,-900)
yrs=range(1981,2026)
res={}
for sn,code,ms in [('Deyr','101112',[9,10,11]),('Gu','040506',[3,4,5])]:
    A=np.array([g[f'{y}_{code}'] for y in yrs])
    area=np.array([np.nanmean(a[mask]) for a in A])
    clim=np.nanmean(A,0)
    anom=100*(area/area.mean()-1)
    n=nino(ms); d=dmi(ms)
    ok=[i for i,y in enumerate(yrs) if y in n and y in d]
    N=np.array([n[yrs[i]] for i in ok]); D=np.array([d[yrs[i]] for i in ok]); R=area[ok]
    rn=np.corrcoef(N,R)[0,1]; rd=np.corrcoef(D,R)[0,1]
    # LOO regression on both
    pred=[]
    for i in range(len(ok)):
        m=np.ones(len(ok),bool); m[i]=False
        Xm=np.c_[np.ones(m.sum()),N[m],D[m]]; b=np.linalg.lstsq(Xm,R[m],rcond=None)[0]
        pred.append(b@[1,N[i],D[i]])
    pred=np.array(pred); rl=np.corrcoef(pred,R)[0,1]
    # tercile hit rate
    t1,t2=np.percentile(R,[33.3,66.7]); cat=lambda v:0 if v<t1 else (2 if v>t2 else 1)
    hits=np.mean([cat(p)==cat(r) for p,r in zip(pred,R)])
    # pixel correlation with nino
    Z=A[ok]; Zs=(Z-Z.mean(0))/Z.std(0); Ns=(N-N.mean())/N.std()
    pix=np.nanmean(Zs*Ns[:,None,None],0); pix[~mask]=np.nan
    print(f"== {sn}: area mean {area.mean():.0f} mm, CV {100*area.std()/area.mean():.0f}%  r(Nino3.4)={rn:.2f}  r(DMI)={rd:.2f}  LOO r={rl:.2f}  tercile hit {hits:.0%} (chance 33%)  share of land with r>0.4: {np.nanmean(pix[mask]>0.4):.0%}")
    order=np.argsort(area)
    print('   driest:',[(yrs[i],int(anom[i])) for i in order[:6]])
    print('   wettest:',[(yrs[i],int(anom[i])) for i in order[::-1][:6]])
    # El Nino + positive IOD analogues
    an=[yrs[i] for i in ok if n[yrs[i]]>=1.0 and d[yrs[i]]>=0.3]
    en=[yrs[i] for i in ok if n[yrs[i]]>=1.0]
    print('   El Nino>=1.0 years:',en,'mean anomaly %+.0f%%'%np.mean([anom[yrs.index(y)] for y in en]) if en else '', ' all wetter than median:',sum(area[yrs.index(y)]>np.median(area) for y in en),'/',len(en))
    print('   El Nino + IOD+ years:',an, ['%+d%%'%anom[yrs.index(y)] for y in an])
    res[sn]={'years':list(yrs),'area':area.round(1).tolist(),'anom':anom.round(1).tolist(),'nino':{y:n.get(y) for y in yrs},'dmi':{y:d.get(y) for y in yrs},'rN':rn,'rD':rd,'loo':rl,'hit':hits,'analog':an,'elnino':en}
    if sn=='Deyr':
        comp=np.nanmean(A[[yrs.index(y) for y in en]],0)/clim*100; comp[~mask]=np.nan
        np.save('deyr_elnino_pct.npy',comp); np.save('deyr_clim.npy',np.where(mask,clim,np.nan)); np.save('deyr_pixr.npy',pix)
        print('   El Nino composite: median land pixel %.0f%% of normal; share of land >150%%: %.0f%%'%(np.nanmedian(comp),100*np.nanmean(comp[mask]>150)))
json.dump(res,open('season_res.json','w'),default=float)
