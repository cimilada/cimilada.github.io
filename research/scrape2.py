import re,json,urllib.request,time,sys,concurrent.futures as cf
def fetch(url):
    for i in range(3):
        try: return urllib.request.urlopen(url,timeout=180).read().decode('utf-8','ignore')
        except Exception as e:
            if i==2: return ''
            time.sleep(5)
def get(s):
    h=fetch('https://climseries.faoswalim.org'+s['url'])
    out={}
    for v,arr in re.findall(r'var (\w+)\s*=\s*(\[\[.*?\]\])\s*;',h,re.S):
        try: out[v]=json.loads(arr)
        except: pass
    return s['station_number'],out
for g in ['ss','mrs']:
    st=json.load(open(g+'_stations.json')); res={}
    with cf.ThreadPoolExecutor(5) as ex:
        for k,v in ex.map(get,st): res[k]=v
    json.dump(res,open(g+'_raw.json','w'))
    print(g,'done',sum(1 for v in res.values() if v))
