"""Foto de saldos (16-nov, aprobado por Fran): dos veces al día guarda cuánto tiene cada billetera A/B/C en los tokens
abiertos de H21, H22, H23 y H24 (Solana). Sirve para estudiar entrada, sostenimiento y salida. Solo registro, sin avisos.
Salida: datos/fotos_saldos.tsv (se agrega). Helius RPC (solo lectura) + DexScreener. La clave nunca se imprime."""
import csv, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(__file__))
from h24 import billeteras

K = os.environ.get("HELIUS_API_KEY", "").strip()
RPC = "rpc_sol"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc_sol
SALIDA = "datos/fotos_saldos.tsv"
MAX_CONSULTAS = int(os.environ.get("FOTO_MAX") or 900)
CAMPOS = ["ts", "hora_utc", "hip", "token", "sym", "grupo", "billetera", "cantidad", "usd", "precio"]


def rpc(m, p):
    # 20-nov: Shyft primero, Helius de respaldo (rpc_sol)
    try:
        return rpc_sol.post_json({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, intentos=6, timeout=30).get("result")
    except Exception:
        return None


def leer(f):
    return list(csv.DictReader(open(f), delimiter="\t")) if os.path.exists(f) else []


def main():
    if not rpc_sol.hay():
        print("fotos: falta HELIUS_API_KEY"); return
    W = billeteras()  # token -> {A, B, C}
    toks = {}  # token -> (hip, sym, {grupo: set})
    def add(t, hip, sym, extra=None):
        g = {k: set(v) for k, v in W.get(t, {"A": set(), "B": set(), "C": set()}).items()}
        for k, ws in (extra or {}).items():
            g.setdefault(k, set()).update(ws)
        if t in toks:
            hip = toks[t][0] + "+" + hip
        toks[t] = (hip, sym, g)
    # 17-nov: primero seguimiento y sostenidas (antes quedaban fuera por el tope de consultas: KNIGHT nunca se medía)
    # 16-nov: también los tokens que nuestras A sostienen y subieron (alertas_sostenidas, últimos 7 días)
    for r in leer("datos/alertas_sostenidas.tsv"):
        if time.time() - int(r["ts"]) < 7 * 86400:
            add(r["token"], "SOST", r["sym"])
    # 16-nov: puntos de seguimiento (tokens con ≥3 operadores A dentro, saldo real verificado)
    for r in leer("datos/seguimiento.tsv"):
        add(r["token"], "SEG", r["sym"], {"A": r["billeteras"].split(",")})
    for r in leer("datos/h21_consenso.tsv"):
        if r["estado"] == "abierto": add(r["token"], "H21", r["sym"], {"A": r["billeteras"].split(",")})
    for r in leer("datos/h23_consenso.tsv"):
        if r["estado"] == "abierto": add(r["token"], "H23", r["sym"], {"C": r["billeteras"].split(",")})
    for r in leer("datos/h22_cruce.tsv"):
        if r["estado"] == "abierto": add(r["token"], "H22", r["sym"], {"B": r["billeteras_B"].split(",")})
    for r in leer("datos/h24_pool_acciones.tsv"):
        if r["estado"] == "abierto" and r["cadena"] == "solana": add(r["token"], "H24", r["sym"])
    precios = {}
    lista = list(toks)
    for i in range(0, len(lista), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(lista[i:i + 30]), headers={"User-Agent": "desk-fotos"})
            for p in json.load(urllib.request.urlopen(req, timeout=25)):
                a, liq = p["baseToken"]["address"], (p.get("liquidity") or {}).get("usd") or 0
                if a not in precios or liq > precios[a][1]:
                    precios[a] = (float(p.get("priceUsd") or 0), liq)
        except Exception as e:
            print("dexscreener falló:", e, file=sys.stderr)
    ahora = int(time.time()); hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora))
    filas, n = [], 0
    for t, (hip, sym, g) in toks.items():
        for grupo in "ABC":
            for w in sorted(g.get(grupo, ())):
                if not w or n >= MAX_CONSULTAS: continue
                n += 1
                r = rpc("getTokenAccountsByOwner", [w, {"mint": t}, {"encoding": "jsonParsed"}])
                if r is None: continue
                amt = sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0) for a in r.get("value", []))
                pr = precios.get(t, (0, 0))[0]
                filas.append(dict(ts=ahora, hora_utc=hora, hip=hip, token=t, sym=sym, grupo=grupo, billetera=w,
                                  cantidad=round(amt, 2), usd=round(amt * pr, 2), precio=pr))
                time.sleep(0.12)
    nuevo = not os.path.exists(SALIDA)
    with open(SALIDA, "a", newline="") as f:
        wr = csv.DictWriter(f, CAMPOS, delimiter="\t")
        if nuevo: wr.writeheader()
        wr.writerows(filas)
    print(f"fotos: {len(toks)} tokens, {n} consultas, {sum(1 for x in filas if x['usd'] >= 5)} posiciones con ≥5 USD")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("fotos falló (no afecta el escaneo):", e, file=sys.stderr)
