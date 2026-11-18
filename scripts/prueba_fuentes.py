"""Prueba (18-nov, Fran: ampliar el escaneo a 500-1000 tokens). Mide cuántos tokens únicos de Solana dan fuentes gratis y cuánto tardan."""
import json, time, urllib.request
def get(u):
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "desk-prueba", "Accept": "application/json"})
        return json.load(urllib.request.urlopen(r, timeout=25))
    except Exception as e:
        print("  fallo", u[:90], str(e)[:60]); return None
t0 = time.time(); gt = set()
for dur in ("5m", "1h", "6h", "24h"):
    for p in range(1, 11):
        d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?duration={dur}&page={p}")
        for x in (d or {}).get("data", []):
            gt.add(x["relationships"]["base_token"]["data"]["id"].split("_", 1)[1])
        time.sleep(2.1)
for p in range(1, 11):
    d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page={p}")
    for x in (d or {}).get("data", []):
        gt.add(x["relationships"]["base_token"]["data"]["id"].split("_", 1)[1])
    time.sleep(2.1)
print(f"GeckoTerminal (trending 5m/1h/6h/24h x10 págs + new 10 págs): {len(gt)} tokens únicos en {round(time.time()-t0)} s")
t1 = time.time(); jup = set(); ejemplo = None
for path in ("toptrending/5m", "toptrending/1h", "toptrending/6h", "toptrending/24h", "toptraded/1h", "toptraded/24h",
             "toporganicscore/1h", "toporganicscore/24h", "recent"):
    d = get(f"https://lite-api.jup.ag/tokens/v2/{path}" + ("?limit=100" if "top" in path else ""))
    if isinstance(d, list):
        print(f"  jupiter {path}: {len(d)}")
        for x in d:
            jup.add(x.get("id")); ejemplo = ejemplo or x
print(f"Jupiter: {len(jup)} únicos en {round(time.time()-t1)} s; nuevos frente a GT: {len(jup - gt)}; total unión {len(gt | jup)}")
if ejemplo:
    print("campos Jupiter:", sorted(ejemplo.keys()))
    print("stats1h:", json.dumps(ejemplo.get("stats1h"))[:400])
    print("audit:", json.dumps(ejemplo.get("audit"))[:300], "holderCount", ejemplo.get("holderCount"), "organicScore", ejemplo.get("organicScore"))
t2 = time.time(); ds = set()
for u in ("https://api.dexscreener.com/token-profiles/latest/v1", "https://api.dexscreener.com/token-boosts/latest/v1", "https://api.dexscreener.com/token-boosts/top/v1"):
    for x in get(u) or []:
        if x.get("chainId") == "solana": ds.add(x.get("tokenAddress"))
print(f"DexScreener perfiles/boosts: {len(ds)}; unión total {len(gt | jup | ds)} en {round(time.time()-t0)} s")
