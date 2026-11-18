"""Prueba (18-nov): baja las listas de Jupiter con pausas e imprime una fila compacta por token (para revisar impulso)."""
import json, time, urllib.request
vis = {}
for path in ("toptrending/5m", "toptrending/1h", "toptrending/6h", "toptrending/24h", "toptraded/5m", "toptraded/1h", "toptraded/24h",
             "toporganicscore/5m", "toporganicscore/1h", "toporganicscore/24h", "recent"):
    d = None
    for k in range(3):
        try:
            r = urllib.request.Request("https://lite-api.jup.ag/tokens/v2/" + path + ("?limit=100" if "top" in path else ""), headers={"User-Agent": "desk-prueba"})
            d = json.load(urllib.request.urlopen(r, timeout=20)); break
        except Exception as e:
            print("fallo", path, str(e)[:50]); time.sleep(8)
    print("lista", path, len(d or []))
    for x in d or []:
        vis.setdefault(x["id"], dict(x, lista=path))
    time.sleep(3)
print("TOTAL", len(vis))
for a, x in vis.items():
    s5, s1, s24 = x.get("stats5m") or {}, x.get("stats1h") or {}, x.get("stats24h") or {}
    print("JUP\t" + "\t".join(str(v) for v in (a, x.get("symbol"), x.get("name"), x["lista"], x.get("mcap"), x.get("liquidity"), x.get("holderCount"),
          s5.get("holderChange"), s1.get("holderChange"), s24.get("holderChange"), s5.get("priceChange"), s1.get("priceChange"), s24.get("priceChange"),
          s1.get("numNetBuyers"), s1.get("numOrganicBuyers"), s1.get("numTraders"), s1.get("buyVolume"), s1.get("sellVolume"),
          x.get("organicScore"), (x.get("audit") or {}).get("topHoldersPercentage"), x.get("createdAt") or (x.get("firstPool") or {}).get("createdAt"))))
