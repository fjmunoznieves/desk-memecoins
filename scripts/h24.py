"""H24 · Memecoins con pool contra acciones tokenizadas (TTWO, NVDAx, NVDAB…). Solo estudio. Propuesto 15-nov.

El escaneo descarta por "pool" a los tokens cuyo pool no es contra SOL/BNB/USDC/etc. Aquí se registran igual
(los de rows2.json con quote exótico + casos manuales), se cruzan con las billeteras A, B y C y se miden a 24 h y 7 d.
Cruce: A = vector 1 año (289) + watchlist en vivo; B = vector 1 año (148) + vigilancia H22; C = vigilancia H23.
Salida: datos/h24_pool_acciones.tsv. Datos gratis (DexScreener) + archivos de Helius ya bajados. Paper, solo lectura.
"""
import csv, json, os, re, sys, time, urllib.request
from collections import defaultdict

SALIDA = "datos/h24_pool_acciones.tsv"
BASEQ = {"SOL", "WSOL", "USDC", "USDT", "WBNB", "BNB", "USD1", "ETH", "WETH", "BUSD", "FDUSD", "PYUSD"}
ACCIONES = {"TTWO", "NVDAB", "NVDAX", "TSLAX", "AAPLX", "SPYX", "QQQX", "MSTRX", "COINX", "HOODX", "GOOGLX", "METAX", "AMZNX"}
CAMPOS = ["ts", "hora_utc", "cadena", "token", "sym", "quote", "tipo", "origen", "edad_h", "precio", "mc", "liq",
          "A", "B", "C", "billeteras", "p24", "c24", "max_c", "max24_pct", "sim_pct", "sim_usd", "sim_detalle", "pool",
          "p7d", "c7d", "estado"]
POSICION_USD = 12  # tamaño de posición paper del desk
MANUALES = [  # casos vistos el 15-nov (consultas de Fran y radar)
    ("solana", "9HFUEab7sompLDPTAaTGkryMNGbtBaFMhHMVpJEBpump", "Fran"),
    ("solana", "DKYcjobF7HPtL9RyQBRdeRQ2iWvizpfbgWwPWNXdpump", "radar"),
    ("solana", "4xgqefa5WcdHWKXzqvM9MRJqWYGaHVEUnpUL4Vq5pump", "escaneo"),
    ("bsc", "0xb82535e74b03ffe4910efea1c759b6bbbf0a7777", "Fran"),
]


def tipo(q):
    q = (q or "").upper()
    return "acción" if q in ACCIONES or re.fullmatch(r"[A-Z]{2,5}X", q) else "otro"


def dex(chain, addrs):
    out = {}
    for i in range(0, len(addrs), 30):
        try:
            req = urllib.request.Request(f"https://api.dexscreener.com/tokens/v1/{chain}/" + ",".join(addrs[i:i + 30]), headers={"User-Agent": "desk-h24"})
            with urllib.request.urlopen(req, timeout=25) as r:
                for p in json.load(r):
                    a = p["baseToken"]["address"]
                    liq = (p.get("liquidity") or {}).get("usd") or 0
                    if a not in out or liq > out[a]["liq"]:
                        out[a] = {"sym": p["baseToken"]["symbol"], "quote": p["quoteToken"]["symbol"], "precio": float(p.get("priceUsd") or 0),
                                  "liq": liq, "mc": p.get("marketCap") or p.get("fdv") or 0, "creado": p.get("pairCreatedAt"),
                                  "pool": p.get("pairAddress")}
        except Exception as e:
            print("dexscreener falló:", e, file=sys.stderr)
        time.sleep(0.4)
    return out


def billeteras():
    """token -> {'A': set, 'B': set, 'C': set} con todas las fuentes disponibles."""
    m = defaultdict(lambda: {"A": set(), "B": set(), "C": set()})
    for f, g, col in (("datos/vector_ops_A_289.tsv", "A", "billetera"), ("datos/vector_ops_B_148.tsv", "B", "billetera"),
                      ("datos/watchlist_compras.tsv", "A", "billetera"), ("datos/h22_compras.tsv", "B", "billetera"),
                      ("datos/h23_compras.tsv", "C", "billetera")):
        if os.path.exists(f):
            for r in csv.DictReader(open(f), delimiter="\t"):
                if "compras" in r and int(r["compras"] or 0) == 0:
                    continue
                m[r["token"]][g].add(r[col])
    return m


def simular_24h(r, d):
    """Ejercicio pedido por Fran: si el filtro "pool" no la hubiera rechazado, ¿cuánto se ganaba o perdía?
    Velas de 5 min de GeckoTerminal en las 24 h desde la detección y las mismas reglas de salida del estudio en sombra
    (stop -20 %, TP1 +60 %, TP2 +120 %, trailing 20 %, time stop 45 min), con posición paper de 12 USD."""
    try:
        from sombra import get, simular, GNET
        pool, t0, p0 = r.get("pool") or d.get("pool"), int(r["ts"]), float(r["precio"])
        net = GNET.get(r["cadena"])
        if not pool or not net:
            r["sim_detalle"] = "sin pool/cadena"; return
        j = get(f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{pool}/ohlcv/minute"
                f"?aggregate=5&limit=300&currency=usd&token={r['token']}&before_timestamp={t0 + 86400}")
        c = sorted(x for x in j["data"]["attributes"]["ohlcv_list"] if t0 <= x[0] <= t0 + 86400)
        if not c or abs(c[0][1] / p0 - 1) > 0.5:
            r["sim_detalle"] = "sin velas o precio no cuadra"; return
        r["max24_pct"] = round((max(x[2] for x in c) / p0 - 1) * 100, 1)
        pct, det = simular(c, p0)
        if d["liq"] < 1000 and det not in ("stop", "time stop 45 min"):
            pct, det = -100.0, "rug: liquidez retirada"
        r["sim_pct"], r["sim_detalle"], r["sim_usd"] = round(pct, 1), det, round(POSICION_USD * pct / 100, 2)
        time.sleep(2.1)
    except Exception as e:
        r["sim_detalle"] = f"simulación falló: {type(e).__name__}"


def main():
    ahora = time.time()
    previas = list(csv.DictReader(open(SALIDA), delimiter="\t")) if os.path.exists(SALIDA) else []
    ya = {(r["cadena"], r["token"].lower()) for r in previas}
    nuevos = []
    if os.path.exists("rows2.json"):
        for r in json.load(open("rows2.json")):
            q = (r.get("quote") or "").upper()
            if q and q not in BASEQ and r.get("liq", 0) >= 10000 and (r["chain"], r["addr"].lower()) not in ya:
                nuevos.append((r["chain"], r["addr"], "escaneo")); ya.add((r["chain"], r["addr"].lower()))
    for c, t, o in MANUALES:
        if (c, t.lower()) not in ya:
            nuevos.append((c, t, o)); ya.add((c, t.lower()))
    por_cadena = defaultdict(list)
    for c, t, _ in nuevos:
        por_cadena[c].append(t)
    for r in previas:
        if r["estado"] == "abierto":
            por_cadena[r["cadena"]].append(r["token"])
    datos = {}
    for c, ts in por_cadena.items():
        for a, d in dex(c, sorted(set(ts))).items():
            datos[(c, a.lower())] = d
    W = billeteras()
    for c, t, o in nuevos:
        d = datos.get((c, t.lower()))
        if not d or (d["quote"] or "").upper() in BASEQ:
            continue
        previas.append({"ts": int(ahora), "hora_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), "cadena": c, "token": t,
                        "sym": d["sym"], "quote": d["quote"], "tipo": tipo(d["quote"]), "origen": o,
                        "edad_h": round((ahora * 1000 - (d["creado"] or ahora * 1000)) / 3.6e6, 1), "precio": d["precio"],
                        "mc": round(d["mc"]), "liq": round(d["liq"]), "estado": "abierto", "max_c": 0, "pool": d.get("pool") or ""})
        print(f"H24 nuevo: {d['sym']} ({c}) contra {d['quote']}")
    for r in previas:  # cruce con billeteras (se actualiza en cada corrida) y medición
        w = W.get(r["token"], {"A": set(), "B": set(), "C": set()})
        r["A"], r["B"], r["C"] = len(w["A"]), len(w["B"]), len(w["C"])
        r["billeteras"] = " ".join(f"{g}:{x[:6]}" for g in "ABC" for x in sorted(w[g]))[:400]
        d, p0 = datos.get((r["cadena"], r["token"].lower())), float(r["precio"] or 0)
        if r["estado"] != "abierto" or not d or not p0:
            continue
        cambio = -100 if d["liq"] < 1000 else round((d["precio"] / p0 - 1) * 100, 1)
        r["max_c"] = max(float(r.get("max_c") or 0), cambio)
        edad = ahora - int(r["ts"])
        if not r.get("p24") and edad >= 86400:
            r["p24"], r["c24"] = d["precio"], cambio
            simular_24h(r, d)
        if not r.get("p7d") and edad >= 7 * 86400:
            r["p7d"], r["c7d"], r["estado"] = d["precio"], cambio, "cerrado"
    with open(SALIDA, "w", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(previas)
    print(f"H24: {len(previas)} registrados, {sum(1 for r in previas if r['estado'] == 'abierto')} abiertos")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("H24 falló (no afecta el escaneo):", e, file=sys.stderr)
