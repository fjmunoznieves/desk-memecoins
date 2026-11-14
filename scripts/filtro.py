"""Filtros numéricos 5.1 sobre rows.json -> rows2.json (bandas A–E, fallos por token, H2)."""
import json,collections,sys
R=json.load(open('rows.json'))
BASEQ={"SOL","WSOL","USDC","USDT","WBNB","BNB","USD1","ETH","WETH","BUSD","FDUSD"}
def band(h):
    if h is None: return '?'
    if h*60<10: return '<10m'
    if h<1: return 'A'
    if h<6: return 'B'
    if h<24: return 'C'
    if h<48: return 'D'
    if h<168: return 'E'
    return '>7d'
fails=collections.Counter()
for r in R:
    r['band']=band(r['age_h']);f=[]
    if r['liq']<30000:f.append('liq')
    if r['v5']<20000:f.append('vol5m')
    bs=r['b']/r['s'] if r['s'] else (99 if r['b'] else 0);r['bs']=bs
    if bs<1.2:f.append('b/s')
    if r['c5']>=50:f.append('5m>=50')
    if r['quote'].upper() not in BASEQ:f.append('pool')
    r['f']=f
    for x in f: fails[x]+=1
json.dump(R,open('rows2.json','w'))
print('bandas',dict(collections.Counter(r['band'] for r in R)),'fallos',dict(fails))
print('pasan numéricos en ventana A–D:',[(r['chain'],r['sym'],r['addr']) for r in R if not r['f'] and r['band'] in 'ABCD'])
