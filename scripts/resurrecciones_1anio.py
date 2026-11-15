import json,time,urllib.request,urllib.error
U=[x for x in json.load(open('datos/resurreccion_universo.json')) if x['net']=='solana']
ev=[]
import datetime as dt
def velas(pool):
    # DexPaprika (gratis, sin clave): GeckoTerminal gratis solo da ~180 días
    for i in range(5):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.dexpaprika.com/networks/solana/pools/{pool}/ohlcv?start=2025-11-01&interval=24h&limit=400",headers={'User-Agent':'desk/1.0'}),timeout=30))
            out=[]
            for c in d:
                t=int(dt.datetime.fromisoformat(c['time_open'].replace('Z','+00:00')).timestamp())
                out.append([t,c['open'],c['high'],c['low'],c['close'],c.get('volume',0)])
            return sorted(out)
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(20); continue
            return None
        except Exception: time.sleep(3)
primero=[]
for n,x in enumerate(U):
    l=velas(x['pool']); time.sleep(0.4)
    if l: primero.append(l[0][0])
    if n==0: print('primera vela del 1.er pool:', time.strftime('%Y-%m-%d',time.gmtime(l[0][0])) if l else None, 'velas', len(l or []), flush=True)
    if not l or len(l)<20: continue
    i=0
    while i<len(l):
        hi=max(c[2] for c in l[:i+1])
        # muerto ≥7 días: cierres ≤35 % del máximo previo, y caída ≥70 %
        if i>=7 and all(c[4]<=0.35*hi for c in l[i-7:i]) and min(c[4] for c in l[i-7:i])<=0.3*hi:
            base=l[i-1][4]
            pico=max(c[2] for c in l[i:i+7])
            if base and pico>=3*base:
                j=i+max(range(min(7,len(l)-i)),key=lambda k:l[i+k][2])
                ev.append(dict(net='solana',sym=x['sym'],token=x['token'],pool=x['pool'],inicio=time.strftime('%Y-%m-%d',time.gmtime(l[i][0])),x=round(pico/base,1),edad_dias=round((l[i][0]-l[0][0])/86400)))
                i=j+7; continue
        i+=1
json.dump(ev,open('datos/resurrecciones_1anio.json','w'))
print('velas desde (mín):', time.strftime('%Y-%m-%d',time.gmtime(min(primero))) if primero else None)
print('eventos',len(ev),'tokens',len({e['token'] for e in ev}))
