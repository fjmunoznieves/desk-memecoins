"""H21 · Consenso de la watchlist en tokens maduros (solo estudio, no es señal).

Si 2 o más billeteras de la watchlist compran el mismo token de más de 48 h de vida dentro de 24 h,
se registra en datos/h21_consenso.tsv con precio, MC y liquidez, y se mide su precio a 24 h y a 7 días.
Datos: datos/watchlist_compras.tsv (Helius) + DexScreener (gratis). Paper trading, solo lectura.
"""
import csv, json, os, sys, time, urllib.request
from collections import defaultdict

COMPRAS = os.environ.get("COMPRAS_FILE", "datos/watchlist_compras.tsv")
SALIDA = os.environ.get("SALIDA_FILE", "datos/h21_consenso.tsv")
NOMBRE = os.environ.get("H_NOMBRE", "H21")
CAMPOS = ["ts", "hora_utc", "token", "sym", "billeteras", "n", "edad_d", "precio", "mc", "liq", "p24", "c24", "p7d", "c7d", "estado"]
VENTANA = 24 * 3600
EDAD_MIN_H = float(os.environ.get("EDAD_MIN_H", 48))
EDAD_MAX_H = float(os.environ.get("EDAD_MAX_H", 1e9))  # H23 usa 0–72 h


def dex(addrs):
    out = {}
    for i in range(0, len(addrs), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(addrs[i:i + 30]), headers={"User-Agent": "desk-h21"})
            with urllib.request.urlopen(req, timeout=25) as r:
                for p in json.load(r):
                    a = p["baseToken"]["address"]
                    liq = (p.get("liquidity") or {}).get("usd") or 0
                    if a not in out or liq > out[a]["liq"]:
                        out[a] = {"sym": p["baseToken"]["symbol"], "precio": float(p.get("priceUsd") or 0), "liq": liq,
                                  "mc": p.get("marketCap") or p.get("fdv") or 0, "creado": p.get("pairCreatedAt")}
        except Exception as e:
            print("dexscreener falló:", e, file=sys.stderr)
        time.sleep(0.4)
    return out


def main():
    if not os.path.exists(COMPRAS):
        print(NOMBRE, ": sin compras de la watchlist todavía")
        return
    ahora = time.time()
    filas = list(csv.DictReader(open(COMPRAS), delimiter="\t"))
    previas = list(csv.DictReader(open(SALIDA), delimiter="\t")) if os.path.exists(SALIDA) else []
    ya = {r["token"] for r in previas}

    # grupos: compras del mismo token por billeteras distintas dentro de 24 h
    por_token = defaultdict(list)
    for f in filas:
        por_token[f["token"]].append((int(f["ts"]), f["billetera"]))
    nuevos = {}
    for tok, compras in por_token.items():
        if tok in ya:
            continue
        compras.sort()
        for i, (t0, _) in enumerate(compras):
            bs = {b for t, b in compras[i:] if t - t0 <= VENTANA}
            if len(bs) >= 2:
                nuevos[tok] = sorted(bs)
                break

    abiertos = [r for r in previas if r["estado"] == "abierto"]
    datos = dex(list(nuevos) + [r["token"] for r in abiertos])

    for tok, bs in nuevos.items():
        d = datos.get(tok)
        if not d or not d["creado"]:
            continue
        edad_h = (ahora * 1000 - d["creado"]) / 3.6e6
        if edad_h < EDAD_MIN_H or edad_h > EDAD_MAX_H:
            continue  # los jóvenes van por las reglas normales (señal 3)
        previas.append({"ts": int(ahora), "hora_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), "token": tok, "sym": d["sym"],
                        "billeteras": ",".join(bs), "n": len(bs), "edad_d": round(edad_h / 24, 1), "precio": d["precio"],
                        "mc": round(d["mc"]), "liq": round(d["liq"]), "p24": "", "c24": "", "p7d": "", "c7d": "", "estado": "abierto"})
        print(f"{NOMBRE} nuevo: {d['sym']} {tok} ({len(bs)} billeteras, {edad_h / 24:.1f} días)")

    for r in previas:
        if r["estado"] != "abierto":
            continue
        d, edad = datos.get(r["token"]), ahora - int(r["ts"])
        p0 = float(r["precio"] or 0)
        if not d or not p0:
            continue
        rug = d["liq"] < 1000
        if not r["p24"] and edad >= 24 * 3600:
            r["p24"], r["c24"] = d["precio"], ("-100" if rug else round((d["precio"] / p0 - 1) * 100, 1))
        if not r["p7d"] and edad >= 7 * 86400:
            r["p7d"], r["c7d"] = d["precio"], ("-100" if rug else round((d["precio"] / p0 - 1) * 100, 1))
            r["estado"] = "cerrado"

    with open(SALIDA, "w", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(previas)
    print(f"{NOMBRE}: {len(previas)} registrados, {sum(1 for r in previas if r['estado'] == 'abierto')} abiertos")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("H21 falló (no afecta el escaneo):", e, file=sys.stderr)
