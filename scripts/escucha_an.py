"""Análisis en papel de datos/escucha/ev_*.tsv (21-nov). Solo mide; no cambia reglas.

Señal = primera compra de un operador A en un token (pump.fun o PumpSwap) en 60 min.
Entrada = primer precio visto >= recv + retraso (5/10/30/60 s). 12 USD por entrada, 6 % de costos ida y vuelta.
Tope +3 %: también se reporta el subconjunto que entra a ≤ +3 % del precio de A (24-nov).
Salidas: copiar (cuando ese operador vende, + mismo retraso), stop −35 %, trailing 30 %, 5 min, 30 min, fin (≤90 min).
"""
import csv, glob, statistics, sys
from collections import defaultdict

RETRASOS = [5, 10, 30, 60]
COSTO = 0.06
filas = []
for f in sorted(glob.glob("datos/escucha/ev_*.tsv")):
    filas += list(csv.DictReader(open(f), delimiter="\t"))
for r in filas:
    r["t"] = float(r["recv_ts"]); r["p"] = float(r["precio_sol"] or 0)
filas = [r for r in filas if r["p"] > 0]
serie = defaultdict(list)
for r in filas:
    serie[r["clave"]].append(r)
for k in serie:
    serie[k].sort(key=lambda r: r["t"])

senales, ult = [], {}
for r in sorted((r for r in filas if r["tipo"] == "A_compra"), key=lambda r: r["t"]):
    key = (r["operador"], r["clave"])
    if r["t"] - ult.get(key, -1e12) > 3600:
        senales.append(r)
    ult[key] = r["t"]
ventas = defaultdict(list)
for r in filas:
    if r["tipo"] == "A_venta":
        ventas[(r["operador"], r["clave"])].append(r["t"])


def precio_desde(s, t):
    for r in s:
        if r["t"] >= t:
            return r
    return None


def simular(sen, d):
    s = serie[sen["clave"]]
    e = precio_desde(s, sen["t"] + d)
    if not e or e["t"] - sen["t"] > d + 120:
        return None
    pe, te = e["p"], e["t"]
    tras = [r for r in s if te < r["t"] <= te + 5400]
    if not tras:
        return None
    res = {}
    v = [t for t in ventas[(sen["operador"], sen["clave"])] if t > sen["t"]]
    if v:
        x = precio_desde(tras, v[0] + d)
        res["copiar"] = (x or tras[-1])["p"] / pe
    else:
        res["copiar"] = tras[-1]["p"] / pe
    pk, res["stop35"], res["trail30"] = pe, None, None
    for r in tras:
        if res["stop35"] is None and r["p"] <= pe * 0.65:
            res["stop35"] = r["p"] / pe
        pk = max(pk, r["p"])
        if res["trail30"] is None and r["p"] <= pk * 0.7:
            res["trail30"] = r["p"] / pe
    res["stop35"] = res["stop35"] or tras[-1]["p"] / pe
    res["trail30"] = res["trail30"] or tras[-1]["p"] / pe
    for nom, seg in (("5min", 300), ("30min", 1800)):
        x = [r for r in tras if r["t"] <= te + seg]
        res[nom] = (x[-1] if x else tras[0])["p"] / pe
    res["fin"] = tras[-1]["p"] / pe
    res["max"] = max(r["p"] for r in tras) / pe
    res["sobre_A"] = pe / sen["p"]  # 24-nov: cuánto más caro entramos que la compra de A
    return res


print(f"filas {len(filas)}, señales {len(senales)}, tokens {len(serie)}")
for d in RETRASOS:
    rs = [x for x in (simular(s, d) for s in senales) if x]
    if not rs:
        print(f"+{d}s: sin datos"); continue
    print(f"\n+{d}s  n={len(rs)}  x2 alcanzado {sum(r['max'] >= 2 for r in rs)}")
    for sal in ("copiar", "stop35", "trail30", "5min", "30min", "fin"):
        pnl = sorted(12 * (r[sal] - 1 - COSTO) for r in rs)
        print(f"  {sal:8s} total {sum(pnl):+8.1f} USD  mediana {100*statistics.median(r[sal]-1-COSTO for r in rs):+6.1f} %  ganan {sum(p>0 for p in pnl)}/{len(pnl)}  sin top3 {sum(pnl[:-3]):+8.1f}")
    # 24-nov (Fran, mejora 2): mismo cálculo solo con entradas a no más de +3 % sobre el precio de compra de A
    t3 = [r for r in rs if r["sobre_A"] <= 1.03]
    if t3:
        print(f"  tope +3 % sobre A: n={len(t3)}")
        for sal in ("copiar", "stop35", "trail30", "fin"):
            pnl = sorted(12 * (r[sal] - 1 - COSTO) for r in t3)
            print(f"    {sal:8s} total {sum(pnl):+8.1f} USD  mediana {100*statistics.median(r[sal]-1-COSTO for r in t3):+6.1f} %  ganan {sum(p>0 for p in pnl)}/{len(pnl)}  sin top3 {sum(pnl[:-3]):+8.1f}")
