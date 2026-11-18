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
# 18-nov (Fran, caso JESTER): guardar el universo completo de cada escaneo, para saber qué vimos y por qué no pasó. Solo registro.
try:
    import os, time
    U = "datos/universo_escaneos.tsv"
    nuevo = not os.path.exists(U)
    ts = int(os.path.getmtime("rows.json")); hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
    with open(U, "a") as fh:
        if nuevo:
            fh.write("ts\thora_utc\tcadena\ttoken\tsym\tbanda\tedad_h\tmc\tliq\tv5\tc5\tc1\tbs\tfallos\tfuente\tholders\thold_chg1h\thold_chg5m\tnetos1h\torganicos1h\ttraders1h\torganic_score\ttop_holders\n")
        for r in R:
            fh.write("\t".join(str(x) for x in (ts, hora, r["chain"], r["addr"], r["sym"], r["band"], round(r["age_h"], 1) if r.get("age_h") is not None else "",
                     round(r.get("mc") or 0), round(r.get("liq") or 0), round(r.get("v5") or 0), r.get("c5", ""), r.get("c1", ""),
                     round(r["bs"], 2), ",".join(r["f"]), r.get("src", ""), *[r.get(k, "") for k in ("holders", "hold_chg1h", "hold_chg5m", "netos1h", "organicos1h", "traders1h", "organic_score", "top_holders")])) + "\n")
except Exception as e:
    print("universo_escaneos falló:", e)
