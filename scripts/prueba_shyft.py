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

# 5) actividad por billetera en la última hora (para ver quién genera el volumen)
if os.environ.get("ACTIVIDAD"):
    ahora = time.time(); filas = []
    for i in range(0, len(A), 50):
        parte = A[i:i+50]
        st, r, dt = post([{"jsonrpc": "2.0", "id": j, "method": "getSignaturesForAddress", "params": [w, {"limit": 1000}]} for j, w in enumerate(parte)])
        for x in (r if isinstance(r, list) else []):
            l = x.get("result") or []
            h1 = sum(1 for s in l if (s.get("blockTime") or 0) > ahora - 3600)
            ok1 = sum(1 for s in l if (s.get("blockTime") or 0) > ahora - 3600 and s.get("err") is None)
            filas.append((h1, ok1, parte[x["id"]]))
        time.sleep(0.5)
    filas.sort(reverse=True)
    tot = sum(f[0] for f in filas)
    print("ACT total 1h:", tot, "con err=None:", sum(f[1] for f in filas), "billeteras activas:", sum(1 for f in filas if f[0]))
    acum = 0
    for h1, ok1, w in filas[:40]:
        acum += h1; print(f"ACT {h1:5d} {ok1:5d} {acum*100//max(tot,1):3d}% {w}")
    open("/tmp/act.tsv", "w").write("\n".join(f"{w}\t{h}\t{o}" for h, o, w in filas))

# 6) depuración: orden de firmas, efecto de "until" y lote de getTransaction
if os.environ.get("ACTIVIDAD") == "debug":
    w = "is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV"
    st, r, dt = post(sig(w)); l = r.get("result") or []
    print("DBG orden blockTime:", [s.get("blockTime") for s in l], "slots:", [s.get("slot") for s in l])
    if len(l) > 2:
        st, r2, dt = post({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [w, {"limit": 15, "until": l[2]["signature"]}]})
        l2 = r2.get("result") if isinstance(r2, dict) else r2
        print("DBG until=3ª firma -> devuelve", len(l2 or []), "(debería ser 2)")
        lote = [{"jsonrpc": "2.0", "id": j, "method": "getTransaction", "params": [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]} for j, s in enumerate(l[:15])]
        st, r3, dt = post(lote)
        print("DBG lote getTransaction:", st, f"{dt:.2f}s", (sum(1 for x in r3 if x.get('result')) if isinstance(r3, list) else str(r3)[:300]))
        if isinstance(r3, list):
            print("DBG errores:", [str(x.get("error"))[:120] for x in r3 if x.get("error")][:3])
        st, r4, dt = post(lote[:3]); print("DBG lote 3:", st, (sum(1 for x in r4 if x.get('result')) if isinstance(r4, list) else str(r4)[:300]))
