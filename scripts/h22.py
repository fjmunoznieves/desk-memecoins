"""H22 · Cruce A→B en tokens maduros (solo estudio, no es señal). Aprobado por Fran el 15-nov.

Una billetera B (148, compradores previos a resurrecciones) compra un token de más de 48 h que ya compraron
2 o más billeteras A (vector de 1 año de las 289, datos/vector_ops_A_289.tsv, o la watchlist en vivo).
Se registra en datos/h22_cruce.tsv con precio, MC y liquidez, y se mide a 24 h y 7 días.
Datos: datos/h22_compras.tsv (Helius, vigilancia B) + DexScreener (gratis). Paper trading, solo lectura.
"""
import csv, os, sys, time
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from h21 import dex

COMPRAS = "datos/h22_compras.tsv"
SALIDA = "datos/h22_cruce.tsv"
CAMPOS = ["ts", "hora_utc", "token", "sym", "billeteras_B", "nB", "nA", "edad_d", "precio", "mc", "liq", "p24", "c24", "p7d", "c7d", "estado"]
EDAD_MIN_H = 48


def tokens_A():
    n = defaultdict(set)
    for f in ("datos/vector_ops_A_289.tsv",):
        if os.path.exists(f):
            for r in csv.DictReader(open(f), delimiter="\t"):
                if int(r.get("compras") or 0) > 0:
                    n[r["token"]].add(r["billetera"])
    if os.path.exists("datos/watchlist_compras.tsv"):
        for r in csv.DictReader(open("datos/watchlist_compras.tsv"), delimiter="\t"):
            n[r["token"]].add(r["billetera"])
    return n


def main():
    if not os.path.exists(COMPRAS):
        print("H22: sin compras de B todavía"); return
    ahora = time.time()
    previas = list(csv.DictReader(open(SALIDA), delimiter="\t")) if os.path.exists(SALIDA) else []
    ya = {r["token"] for r in previas}
    A = tokens_A()
    por = defaultdict(set)
    for r in csv.DictReader(open(COMPRAS), delimiter="\t"):
        if ahora - int(r["ts"]) < 86400 and r["token"] not in ya and len(A.get(r["token"], ())) >= 2:
            por[r["token"]].add(r["billetera"])
    abiertos = [r for r in previas if r["estado"] == "abierto"]
    datos = dex(list(por) + [r["token"] for r in abiertos])
    for tok, bs in por.items():
        d = datos.get(tok)
        if not d or not d["creado"]:
            continue
        edad_h = (ahora * 1000 - d["creado"]) / 3.6e6
        if edad_h < EDAD_MIN_H:
            continue
        previas.append({"ts": int(ahora), "hora_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), "token": tok, "sym": d["sym"],
                        "billeteras_B": ",".join(sorted(bs)), "nB": len(bs), "nA": len(A[tok]), "edad_d": round(edad_h / 24, 1),
                        "precio": d["precio"], "mc": round(d["mc"]), "liq": round(d["liq"]), "p24": "", "c24": "", "p7d": "", "c7d": "", "estado": "abierto"})
        print(f"H22 nuevo: {d['sym']} {tok} (B {len(bs)}, A {len(A[tok])}, {edad_h / 24:.1f} días)")
    for r in previas:
        d, edad, p0 = datos.get(r["token"]), ahora - int(r["ts"]), float(r["precio"] or 0)
        if r["estado"] != "abierto" or not d or not p0:
            continue
        rug = d["liq"] < 1000
        if not r["p24"] and edad >= 86400:
            r["p24"], r["c24"] = d["precio"], ("-100" if rug else round((d["precio"] / p0 - 1) * 100, 1))
        if not r["p7d"] and edad >= 7 * 86400:
            r["p7d"], r["c7d"] = d["precio"], ("-100" if rug else round((d["precio"] / p0 - 1) * 100, 1))
            r["estado"] = "cerrado"
    with open(SALIDA, "w", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(previas)
    print(f"H22: {len(previas)} registrados, {sum(1 for r in previas if r['estado'] == 'abierto')} abiertos")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("H22 falló (no afecta el escaneo):", e, file=sys.stderr)
