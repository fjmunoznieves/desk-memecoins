"""Prueba del RPC gratis de Shyft (19-nov): una consulta, lote JSON-RPC y ráfaga de 227 billeteras.
No imprime la clave."""
import json, os, re, time, urllib.request, urllib.error
K = os.environ.get("SHYFT_API_KEY", "").strip()
if not K:
    raise SystemExit("falta SHYFT_API_KEY")
URL = f"https://rpc.shyft.to?api_key={K}"
A = re.findall(r'"([1-9A-HJ-NP-Za-km-z]{32,44})"', open("tiempo_real/billeteras.js").read())
print("billeteras:", len(A))

def post(body):
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": "desk"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read()), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, (e.read()[:200].decode("utf8", "replace").replace(K, "***")), time.time() - t
    except Exception as e:
        return 0, str(e).replace(K, "***")[:200], time.time() - t

def sig(w, i=1):
    return {"jsonrpc": "2.0", "id": i, "method": "getSignaturesForAddress", "params": [w, {"limit": 5}]}

# 1) una consulta
st, r, dt = post(sig(A[0]))
print("1) una consulta:", st, f"{dt:.2f}s", (len(r.get("result", [])) if isinstance(r, dict) else r))
# 2) lote de 50 en una sola petición
st, r, dt = post([sig(w, i) for i, w in enumerate(A[:50])])
ok = sum(1 for x in r if isinstance(x, dict) and "result" in x) if isinstance(r, list) else 0
print("2) lote 50:", st, f"{dt:.2f}s", "ok", ok, "" if isinstance(r, list) else str(r)[:200])
# 3) ráfaga 227 individuales a ~8/s
cod = {}
t0 = time.time()
for i, w in enumerate(A):
    st, r, dt = post(sig(w, i))
    k = st if not (isinstance(r, dict) and "error" in r) else f"{st}-err{r['error'].get('code')}"
    cod[k] = cod.get(k, 0) + 1
    time.sleep(max(0, 0.125 - dt))
print("3) ráfaga 227:", cod, f"{time.time()-t0:.0f}s")
# 4) getTransaction de una firma reciente
st, r, dt = post(sig(A[1]))
if isinstance(r, dict) and r.get("result"):
    s = r["result"][0]["signature"]
    st, r, dt = post({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]})
    print("4) getTransaction:", st, f"{dt:.2f}s", "ok" if isinstance(r, dict) and r.get("result") else str(r)[:200])
