"""Vigila las compras nuevas de la watchlist de Solana con Helius. Solo lectura y paper: no opera.
- RPC getSignaturesForAddress (barato) para ver si hay transacciones nuevas por billetera.
- Solo si hay nuevas, las interpreta con la API de transacciones de Helius (en lotes).
- Registra cada compra en datos/watchlist_compras.tsv y, si 2+ billeteras compran el mismo token en 24 h,
  escribe datos/alertas_pendientes.json para que el workflow abra un aviso (issue) en GitHub.
La clave sale del secreto HELIUS_API_KEY y nunca se imprime."""
import csv, json, os, sys, time, urllib.request

KEY = os.environ.get("HELIUS_API_KEY", "").strip()
RPC = f"https://mainnet.helius-rpc.com/?api-key={KEY}"
PARSE = [f"https://api-mainnet.helius-rpc.com/v0/transactions?api-key={KEY}", f"https://api.helius.xyz/v0/transactions?api-key={KEY}"]
WL = os.environ.get("WL_FILE", "datos/watchlist_solana.tsv")
ST = os.environ.get("ST_FILE", "datos/watchlist_estado.json")
LOG = os.environ.get("LOG_FILE", "datos/watchlist_compras.tsv")
AL = os.environ.get("AL_FILE", "datos/alertas_pendientes.json")
BASE = {"So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY2yoAFsTJ9Q9Pd2", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"}
COLS = ["hora_utc", "ts", "billetera", "token", "cantidad", "sol_gastado", "firma"]


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "desk-scan"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def safe(e):  # nunca mostrar la clave en los errores
    return str(e).replace(KEY, "***") if KEY else str(e)


if not KEY:
    print("Falta el secreto HELIUS_API_KEY: no se revisa nada todavía"); json.dump([], open(AL, "w")); sys.exit(0)
wl = [r["direccion"] for r in csv.DictReader(open(WL), delimiter="\t")]
st = json.load(open(ST)) if os.path.exists(ST) else {"ultima": {}, "alertados": []}
primera = not st["ultima"]
nuevas = {}
for w in wl:
    try:
        d = post(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [w, {"limit": 50}]})
    except Exception as e:
        print("rpc error", w[:6], safe(e)[:80]); continue
    sigs = [s["signature"] for s in d.get("result") or [] if not s.get("err")]
    if not sigs: continue
    last = st["ultima"].get(w)
    if last and last in sigs:
        sigs = sigs[:sigs.index(last)]
    elif not last:
        st["ultima"][w] = sigs[0]; continue  # primera vez: solo marcar el punto de partida
    if sigs:
        nuevas[w] = sigs
        st["ultima"][w] = sigs[0]
    time.sleep(0.2)

compras = []
for w, sigs in nuevas.items():
    for i in range(0, len(sigs), 100):
        txs = None
        for u in PARSE:
            try:
                txs = post(u, {"transactions": sigs[i:i + 100]}); break
            except Exception as e:
                print("parse error", safe(e)[:80])
        for t in txs or []:
            tt = t.get("tokenTransfers") or []
            got = [x for x in tt if x.get("toUserAccount") == w and x.get("mint") not in BASE]
            gave_tok = [x for x in tt if x.get("fromUserAccount") == w and x.get("mint") not in BASE]
            if not got or gave_tok:  # compra = recibe token no base sin entregar otro token no base
                continue
            sol = sum(x.get("amount", 0) for x in t.get("nativeTransfers") or [] if x.get("fromUserAccount") == w) / 1e9
            if sol < 0.05 and t.get("type") != "SWAP":  # descarta airdrops y transferencias gratis
                continue
            ts = t.get("timestamp") or int(time.time())
            for x in got:
                compras.append(dict(hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)), ts=ts, billetera=w, token=x["mint"],
                                    cantidad=x.get("tokenAmount"), sol_gastado=round(sol, 3), firma=t.get("signature")))

if compras:
    nuevo = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLS, delimiter="\t")
        if nuevo: wr.writeheader()
        wr.writerows(compras)

# Consenso: 2+ billeteras distintas compran el mismo token en 24 h
alertas = []
if os.path.exists(LOG):
    now = time.time()
    rows = [r for r in csv.DictReader(open(LOG), delimiter="\t") if now - int(r["ts"]) < 86400]
    por = {}
    for r in rows:
        por.setdefault(r["token"], {}).setdefault(r["billetera"], r)
    for tok, ws in por.items():
        if len(ws) >= 2 and tok not in st["alertados"]:
            alertas.append({"token": tok, "billeteras": [{"b": b, "hora": r["hora_utc"], "sol": r["sol_gastado"]} for b, r in ws.items()]})
            st["alertados"].append(tok)
st["alertados"] = st["alertados"][-500:]
json.dump(st, open(ST, "w"), indent=1)
json.dump(alertas, open(AL, "w"), indent=1)
print(("punto de partida fijado; " if primera else "") + f"billeteras con tx nuevas: {len(nuevas)}, compras: {len(compras)}, alertas: {len(alertas)}")

# H23 (15-nov, aprobado por Fran): vigila las 129 billeteras C solo en los escaneos de 3:47 AM y 3:47 PM Bogotá
# (8:47 y 20:47 UTC; se acepta hasta 2 h de retraso de GitHub). Solo registro, sin avisos.
import subprocess
if not os.environ.get("ES_H23") and os.environ.get("GITHUB_WORKFLOW", "").startswith("Escaneo") and time.gmtime().tm_hour in (8, 9, 10, 20, 21, 22):
    e = dict(os.environ, ES_H23="1", WL_FILE="datos/vector_C_entrenadas.tsv", ST_FILE="datos/h23_estado.json",
             LOG_FILE="datos/h23_compras.tsv", AL_FILE="datos/h23_alertas.json")
    subprocess.run([sys.executable, __file__], env=e, check=False)
    e2 = dict(os.environ, H_NOMBRE="H23", COMPRAS_FILE="datos/h23_compras.tsv", SALIDA_FILE="datos/h23_consenso.tsv",
              EDAD_MIN_H="0", EDAD_MAX_H="72")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "h21.py")], env=e2, check=False)
    # H22 (15-nov, aprobado por Fran): vigila las 148 billeteras B a las mismas horas y cruza con tokens de A.
    e3 = dict(os.environ, ES_H23="1", WL_FILE="datos/vector_B_148.tsv", ST_FILE="datos/h22_estado.json",
              LOG_FILE="datos/h22_compras.tsv", AL_FILE="datos/h22_alertas.json")
    subprocess.run([sys.executable, __file__], env=e3, check=False)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "h22.py")], check=False)

# H24 (15-nov): tokens con pool contra acciones tokenizadas, cruzados con A/B/C. En cada escaneo, solo registro.
if not os.environ.get("ES_H23") and os.environ.get("GITHUB_WORKFLOW", "").startswith("Escaneo"):
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "h24.py")], check=False)

# Foto de saldos (16-nov, aprobado por Fran): a las 3:47 AM y PM, después de H22/H23/H24. Solo registro.
if not os.environ.get("ES_H23") and os.environ.get("GITHUB_WORKFLOW", "").startswith("Escaneo") and time.gmtime().tm_hour in (8, 9, 10, 20, 21, 22):
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "fotos_saldos.py")], check=False)
    # Salidas en sombra (16-nov, aprobado por Fran): escalonada, "copiar A" y consenso por operadores. Solo registro.
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "salidas.py")], check=False)

# Vigilancia de posiciones abiertas de A (16-nov, caso BLOB): en escaneo y reloj; detecta subidas y verifica saldo real
# con Helius. El issue lo crea alerta_issue.py (paso siguiente, con GH_TOKEN).
if not os.environ.get("ES_H23"):
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "vigila_sostenidas.py")], check=False)
    # Consenso A en vivo (16-nov, Fran): 2+ operadores A compran el mismo token en 72 h → seguimiento + aviso.
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "consenso_A.py")], check=False)
