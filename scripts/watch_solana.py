"""Vigila las compras nuevas de la watchlist de Solana con Helius. Solo lectura y paper: no opera.
- RPC getSignaturesForAddress (barato) para ver si hay transacciones nuevas por billetera.
- Solo si hay nuevas, las interpreta con getTransaction (1 crédito por tx; Alchemy si hay ALCHEMY_API_KEY).
- Registra cada compra en datos/watchlist_compras.tsv y, si 2+ billeteras compran el mismo token en 24 h,
  escribe datos/alertas_pendientes.json para que el workflow abra un aviso (issue) en GitHub.
La clave sale del secreto HELIUS_API_KEY y nunca se imprime."""
import csv, json, os, sys, time, urllib.request, urllib.error
T0 = time.time()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc_sol  # 20-nov: Shyft primero, Helius de respaldo
import atexit; atexit.register(lambda: print(rpc_sol.resumen()))
KEY = os.environ.get("HELIUS_API_KEY", "").strip()
RPC = "PRINCIPAL"  # marcador: post() lo envía por rpc_sol
ALC = os.environ.get("ALCHEMY_API_KEY", "").strip()
RPC_TX = RPC  # 20-nov: getTransaction por Shyft (gratis); Alchemy queda para métodos de índice
WL = os.environ.get("WL_FILE", "datos/watchlist_solana.tsv")
ST = os.environ.get("ST_FILE", "datos/watchlist_estado.json")
LOG = os.environ.get("LOG_FILE", "datos/watchlist_compras.tsv")
AL = os.environ.get("AL_FILE", "datos/alertas_pendientes.json")
BASE = {"So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY2yoAFsTJ9Q9Pd2", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"}
COLS = ["hora_utc", "ts", "billetera", "token", "cantidad", "sol_gastado", "firma"]


def post(url, body):
    if url == RPC:
        return rpc_sol.post_json(body)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "desk-scan"})
    for i in range(5):  # 16-nov: reintenta ante 429 (límite de Helius cuando corren varias cosas a la vez)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == 4:
                raise
            time.sleep(2 + 3 * i)


def safe(e):  # nunca mostrar las claves en los errores
    m = str(e)
    for k in (KEY, ALC, os.environ.get("SHYFT_API_KEY", "").strip()):
        if k: m = m.replace(k, "***")
    return m


if not rpc_sol.hay():
    print("Falta el secreto HELIUS_API_KEY / SHYFT_API_KEY: no se revisa nada todavía"); json.dump([], open(AL, "w")); sys.exit(0)
wl = [r["direccion"] for r in csv.DictReader(open(WL), delimiter="\t")]
st = json.load(open(ST)) if os.path.exists(ST) else {"ultima": {}, "alertados": []}
primera = not st["ultima"]
CARTERA = bool(os.environ.get("CARTERA"))  # 16-nov (Fran, freno Helius): foto de cartera en vez de leer transacciones
nuevas = {}
for w in ([] if CARTERA else wl):
    try:
        d = post(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [w, {"limit": 50}]})
    except Exception as e:
        print("rpc error", w[:6], safe(e)[:80]); continue
    sigs = [s["signature"] for s in d.get("result") or [] if not s.get("err")]
    if not sigs: continue
    last = st["ultima"].get(w)
    if last and last in sigs:
        sigs = sigs[:sigs.index(last)]
    elif not last and not os.environ.get("SEMILLA"):
        st["ultima"][w] = sigs[0]; continue  # primera vez: solo marcar el punto de partida
    # SEMILLA (consenso A, 16-nov): la primera vez toma las últimas 50 transacciones como nuevas
    if sigs:
        nuevas[w] = sigs
        st["ultima"][w] = sigs[0]
    time.sleep(0.2)

compras = []
# 16-nov (freno Helius 738k): antes se usaba la API "Enhanced Transactions" de Helius (100 créditos por llamada,
# una por billetera con tx nuevas → decenas de miles de créditos por escaneo). Ahora: getTransaction jsonParsed
# por firma (1 crédito en Helius; o Alchemy si está ALCHEMY_API_KEY). Misma regla de compra.
def tx_rpc(sg):
    try:
        return post(RPC_TX, {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                             "params": [sg, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}]}).get("result")
    except Exception as e:
        print("tx error", safe(e)[:80]); return None


def compra_de(t, w):
    meta = t.get("meta") or {}
    if meta.get("err") is not None:
        return []
    ks = [k["pubkey"] if isinstance(k, dict) else k for k in t["transaction"]["message"]["accountKeys"]]
    dif = {}
    for lado, sg in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in meta.get(lado) or []:
            if b.get("owner") != w:
                continue
            dif[b["mint"]] = dif.get(b["mint"], 0) + sg * float(b["uiTokenAmount"]["uiAmount"] or 0)
    got = [(m, v) for m, v in dif.items() if m not in BASE and v > 0]
    gave_tok = [m for m, v in dif.items() if m not in BASE and v < 0]
    if not got or gave_tok:  # compra = recibe token no base sin entregar otro token no base
        return []
    sol = 0.0
    if w in ks:
        i = ks.index(w)
        sol = max(0.0, (meta["preBalances"][i] - meta["postBalances"][i]) / 1e9)
    sol += max(0.0, -dif.get("So11111111111111111111111111111111111111112", 0))
    base_out = any(v < 0 for m, v in dif.items() if m in BASE)
    if sol < 0.05 and not base_out:  # descarta airdrops y transferencias gratis
        return []
    ts = t.get("blockTime") or int(time.time())
    return [dict(hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)), ts=ts, billetera=w, token=m,
                 cantidad=v, sol_gastado=round(sol, 3), firma=t["transaction"]["signatures"][0]) for m, v in got]


TOKEN_PROGS = ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]


def foto(w):
    """Saldos de todos los tokens de la billetera (2 consultas: Token y Token-2022). None si falla."""
    out = {}
    for prog in TOKEN_PROGS:
        try:
            r = post(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                           "params": [w, {"programId": prog}, {"encoding": "jsonParsed"}]})
            if r.get("error"):  # 16-nov: un error de la consulta no puede pasar como "billetera vacía"
                print("foto error", w[:6], str(r["error"])[:80]); return None
            r = r.get("result") or {}
        except Exception as e:
            print("foto error", w[:6], safe(e)[:80]); return None
        for acc in r.get("value") or []:
            d = acc["account"]["data"]
            if not isinstance(d, dict):  # 20-nov: cuenta que el RPC no pudo desglosar (llega en base64): se omite
                continue
            inf = d["parsed"]["info"]
            v = float(inf["tokenAmount"]["uiAmount"] or 0)
            if v > 0 and inf["mint"] not in BASE:
                out[inf["mint"]] = out.get(inf["mint"], 0) + v
    return out


def precios(mints):
    px = {}
    ms = list(mints)
    for i in range(0, len(ms), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(ms[i:i + 30]), headers={"User-Agent": "desk-scan"})
            for p in json.load(urllib.request.urlopen(req, timeout=25)):
                m = p["baseToken"]["address"]
                liq = (p.get("liquidity") or {}).get("usd") or 0
                if m not in px or liq > px[m][1]:
                    px[m] = (float(p.get("priceUsd") or 0), liq)
        except Exception as e:
            print("dexscreener", str(e)[:60])
        time.sleep(0.25)
    return {m: v[0] for m, v in px.items()}


if CARTERA:
    # Compra = un token nuevo o que sube ≥10 % frente a la foto anterior (entre escaneos). Venta = baja (queda en la foto).
    prev = st.setdefault("cartera", {})
    subidas, bajadas, ahora = [], [], int(time.time())
    for w in wl:
        f = foto(w); time.sleep(0.1)
        if f is None:
            continue
        p0 = prev.get(w)
        if p0 is not None:
            for m, v in f.items():
                antes = p0.get(m[:12], 0)
                if v > antes * 1.1 + 1e-9:
                    subidas.append((w, m, v - antes))
            # Salidas (16-nov, Fran): saldo que baja ≥10 % o desaparece → datos/*_ventas.tsv (ciclo entrada-sostén-salida)
            cortos = {m[:12]: m for m in f}
            for k, antes in p0.items():
                v = f.get(cortos.get(k, ""), 0)
                if antes > 0 and v < antes * 0.9:
                    bajadas.append((w, k, antes - v, v))
        prev[w] = {m[:12]: float("%.4g" % v) for m, v in f.items()}  # clave corta y 4 cifras: el estado se guarda en git
    px = precios({m for _, m, _ in subidas}) if subidas else {}
    sol_px = precios(["So11111111111111111111111111111111111111112"]).get("So11111111111111111111111111111111111111112") or 0
    for w, m, dv in subidas:
        usd = dv * px.get(m, 0)
        if usd < 5:  # polvo o tokens sin precio
            continue
        compras.append(dict(hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), ts=ahora, billetera=w, token=m,
                            cantidad=round(dv, 6), sol_gastado=round(usd / sol_px, 3) if sol_px else "", firma="foto"))
    if bajadas:
        VLOG = LOG.replace("compras", "ventas") if "compras" in LOG else LOG + ".ventas"
        nuevo_v = not os.path.exists(VLOG)
        with open(VLOG, "a", newline="") as fv:
            wv = csv.writer(fv, delimiter="\t", lineterminator="\n")
            if nuevo_v:
                wv.writerow(["hora_utc", "ts", "billetera", "token12", "vendido", "queda", "salida_total"])
            for w, k, dv, v in bajadas:
                wv.writerow([time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), ahora, w, k, "%.4g" % dv, "%.4g" % v, "si" if v == 0 else "no"])
    print(f"cartera: {len(wl)} billeteras, {2 * len(wl)} consultas, {len(subidas)} subidas y {len(bajadas)} bajadas de saldo")
    # CONTROL (16-nov, Fran): la foto de cartera debe coincidir con las fotos de saldos directas (fotos_saldos.py, que consulta
    # token por token). Sin consultas extra. Si coincide menos del 90 %, se registra la falla y se abre aviso.
    try:
        fs = list(csv.DictReader(open("datos/fotos_saldos.tsv"), delimiter="\t"))
        ult = max(int(r["ts"]) for r in fs)
        en_wl = set(wl)
        pares = {(r["billetera"], r["token"]) for r in fs if int(r["ts"]) == ult and r["billetera"] in en_wl and float(r["usd"] or 0) >= 20}
        ok = sum(1 for w, t in pares if w in prev and t[:12] in prev[w])
        pct = round(100 * ok / len(pares), 1) if pares else None
        estado_c = "sin datos" if pct is None else ("ok" if pct >= 90 else "FALLA")
        print(f"CONTROL cartera vs fotos de saldos: {ok}/{len(pares)} posiciones coinciden ({pct} %) → {estado_c}")
        nuevo_c = not os.path.exists("datos/control_cartera.tsv")
        with open("datos/control_cartera.tsv", "a", newline="") as fc:
            if nuevo_c:
                fc.write("hora_utc\tlista\tcoinciden\ttotal\tpct\testado\n")
            fc.write(f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(ahora))}\t{os.path.basename(WL)}\t{ok}\t{len(pares)}\t{pct}\t{estado_c}\n")
        if estado_c == "FALLA":
            json.dump([{"control": "cartera", "lista": os.path.basename(WL), "coinciden": ok, "total": len(pares)}],
                      open("datos/control_cartera_falla.json", "w"))
    except Exception as e:
        print("control cartera no se pudo calcular:", str(e)[:80])

else:
    from concurrent.futures import ThreadPoolExecutor
    pares = [(w, sg) for w, sigs in nuevas.items() for sg in sigs]
    NTX = len(pares)

    def una(par):
        time.sleep(0.4)  # 4 hilos ≈ 8 consultas/s: bajo el límite de Helius (10/s)
        return par[0], tx_rpc(par[1])
    with ThreadPoolExecutor(4) as ex:
        for w, t in ex.map(una, pares):
            if t:
                compras += compra_de(t, w)
    print(f"getTransaction: {NTX} ({'Shyft' if rpc_sol.SHYFT else 'Helius RPC, 1 crédito c/u'})")


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

# 20-nov: límites subidos (job 50 min, repo público): con 16-20 min, consenso A, liquidez y H25 se saltaban en los escaneos de 3:47 (B/C/fotos tardan).
# 19-nov: el escaneo de 12:27 se cortó por el límite de 30 min antes de llegar a estudios_17nov (H34 en tiempo real).
# Por eso H27/IMIT/bundles/H34rt corren primero (son baratos, sin Helius) y los pasos opcionales se saltan si no hay tiempo.
import subprocess
def _paso(nombre, opcional=False, limite_min=17):
    if opcional and (time.time() - T0) / 60 > limite_min:
        print(f"sin tiempo ({(time.time() - T0) / 60:.0f} min): se salta {nombre}")
        return
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), nombre)], check=False)
if not os.environ.get("ES_H23"):
    _paso("estudios_17nov.py")  # H27, IMIT, bundles, H34 y H34 en tiempo real
# H23 (15-nov, aprobado por Fran): vigila las 129 billeteras C solo en los escaneos de 3:47 AM y 3:47 PM Bogotá
# (8:47 y 20:47 UTC; se acepta hasta 2 h de retraso de GitHub). Solo registro, sin avisos.
import subprocess
if not os.environ.get("ES_H23") and os.environ.get("GITHUB_WORKFLOW", "").startswith("Escaneo") and time.gmtime().tm_hour in (8, 9, 10, 20, 21, 22):
    e = dict(os.environ, ES_H23="1", WL_FILE="datos/vector_C_entrenadas.tsv", ST_FILE="datos/h23_estado.json",
             LOG_FILE="datos/h23_compras.tsv", AL_FILE="datos/h23_alertas.json", CARTERA="1")
    subprocess.run([sys.executable, __file__], env=e, check=False)
    e2 = dict(os.environ, H_NOMBRE="H23", COMPRAS_FILE="datos/h23_compras.tsv", SALIDA_FILE="datos/h23_consenso.tsv",
              EDAD_MIN_H="0", EDAD_MAX_H="72")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "h21.py")], env=e2, check=False)
    # H22 (15-nov, aprobado por Fran): vigila las 148 billeteras B a las mismas horas y cruza con tokens de A.
    e3 = dict(os.environ, ES_H23="1", WL_FILE="datos/vector_B_148.tsv", ST_FILE="datos/h22_estado.json",
              LOG_FILE="datos/h22_compras.tsv", AL_FILE="datos/h22_alertas.json", CARTERA="1")
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
    # Liquidez de lo que está en seguimiento (17-nov, Fran): solo registro, DexScreener.
    _paso("liquidez.py", opcional=True, limite_min=30)
    # H25 y H26 en sombra (17-nov, Fran): maduros con A sosteniendo / lanzamientos con liquidez 100-250k. Solo registro.
    _paso("h25_h26.py", opcional=True, limite_min=31)
    # Consenso A en vivo (16-nov, Fran): 2+ operadores A compran el mismo token en 72 h → seguimiento + aviso.
    _paso("consenso_A.py", opcional=True, limite_min=32)
    _paso("mesa_datos.py", opcional=True, limite_min=33)  # datos de la Mesa interactiva
    _paso("h28_catalizador.py", opcional=True, limite_min=33)  # H28 catalizador (sombra)
