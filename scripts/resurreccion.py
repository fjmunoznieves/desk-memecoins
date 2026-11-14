"""H16 paso horario (solo sombra, paper): ¿algún token muerto despertó?

Disparo: volumen de la última hora (todas sus pools en DexScreener) ≥ 5× su base por hora
y precio de la última hora en verde. Se registra TODO disparo en datos/h16_resurrecciones.tsv;
solo se abre un aviso (issue) si la liquidez es ≥ 30k USD y la revisión de seguridad pasa.
Cada hora también sigue los disparos abiertos: máximo y mínimo vistos, precio a +6 h y a +24 h.
"""
import csv, json, os, subprocess, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from seguridad import revisar

M = "datos/muertos.json"
OUT = "datos/h16_resurrecciones.tsv"
RATIO, VOL_MIN, LIQ_MIN = 5.0, 1000.0, 30000.0
COLS = ["ts", "hora_utc", "cadena", "token", "sym", "revivio", "precio", "liq", "mc", "vol_h1", "base_h", "ratio", "c1",
        "pasa_liq", "seguridad", "aviso", "pmax", "pmin", "p6", "p24", "estado"]


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(30 if getattr(e, "code", None) == 429 else 3)
    return None


def leer():
    if not os.path.exists(OUT):
        return []
    with open(OUT) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def guardar(rows):
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def consultar(cadena, tokens):
    """Devuelve {token: (vol_h1 sumado, par con más liquidez)}."""
    res = {}
    for i in range(0, len(tokens), 30):
        lote = tokens[i:i + 30]
        norm = {x.lower() if x.startswith("0x") else x: x for x in lote}  # en EVM DexScreener puede cambiar mayúsculas
        for p in get(f"https://api.dexscreener.com/tokens/v1/{cadena}/" + ",".join(lote)) or []:
            a = p["baseToken"]["address"]
            a = norm.get(a.lower() if a.startswith("0x") else a)
            if a is None:
                continue
            vol, mejor = res.get(a, (0.0, None))
            vol += (p.get("volume") or {}).get("h1") or 0
            liq = lambda q: ((q or {}).get("liquidity") or {}).get("usd") or 0
            if mejor is None or liq(p) > liq(mejor):
                mejor = p
            res[a] = (vol, mejor)
        time.sleep(0.4)
    return res


ahora = int(time.time())
rows = leer()
muertos = json.load(open(M))["muertos"] if os.path.exists(M) else []
porcadena = {}
for t in muertos:
    porcadena.setdefault(t["net"], []).append(t)
abiertos = [r for r in rows if r["estado"] == "abierto"]
for r in abiertos:  # los disparos abiertos se consultan aunque ya no estén en la lista de muertos
    porcadena.setdefault(r["cadena"], [])

datos = {}
for cadena, lista in porcadena.items():
    toks = sorted({t["token"] for t in lista} | {r["token"] for r in abiertos if r["cadena"] == cadena})
    datos.update({(cadena, a): v for a, v in consultar(cadena, toks).items()})

# 1) seguimiento de disparos abiertos
for r in abiertos:
    vol, p = datos.get((r["cadena"], r["token"]), (0, None))
    if not p or not p.get("priceUsd"):
        continue
    precio = float(p["priceUsd"])
    r["pmax"] = f"{max(float(r['pmax'] or precio), precio):.10g}"
    r["pmin"] = f"{min(float(r['pmin'] or precio), precio):.10g}"
    edad = ahora - int(r["ts"])
    if edad >= 6 * 3600 and not r["p6"]:
        r["p6"] = f"{precio:.10g}"
    if edad >= 24 * 3600:
        r["p24"] = f"{precio:.10g}"
        r["estado"] = "medido"

# 2) disparos nuevos
recientes = {(r["cadena"], r["token"]) for r in rows if ahora - int(r["ts"]) < 24 * 3600}
nuevos = 0
for t in muertos:
    k = (t["net"], t["token"])
    if k in recientes or k not in datos:
        continue
    vol, p = datos[k]
    c1 = ((p.get("priceChange") or {}).get("h1") or 0) if p else 0
    if not p or not p.get("priceUsd") or vol < VOL_MIN or vol < RATIO * t["base_h"] or c1 <= 0:
        continue
    liq = (p.get("liquidity") or {}).get("usd") or 0
    pasa = liq >= LIQ_MIN
    fallos = revisar(t["net"], t["token"])[0] if pasa else ["no revisada (liq<30k)"]
    aviso = "no"
    if pasa and not fallos:
        cad = {"solana": "Solana", "bsc": "BNB", "robinhood": "Robinhood"}.get(t["net"], t["net"])
        cuerpo = "\n".join([
            "Paper trading, H16 (sombra): solo aviso, no es orden de compra.", "",
            f"- Token: {t['sym']} en {cad}", f"- Contrato: `{t['token']}`",
            f"- DexScreener: https://dexscreener.com/{t['net']}/{t['token']}",
            f"- Volumen última hora: {vol:,.0f} USD, {vol / t['base_h']:.1f}× su base ({t['base_h']:,.0f} USD/h)",
            f"- Precio 1 h: +{c1}% | Liquidez: {liq:,.0f} USD | MC: {(p.get('marketCap') or p.get('fdv') or 0):,.0f} USD",
            f"- Revivió antes en el estudio: {t.get('revivio', 0)} veces",
            "", "Del estudio: entrar solo por el disparo es casi una moneda al aire; mirar si hay pool nueva o token hijo, y respetar stop −20 %."])
        r = subprocess.run(["gh", "issue", "create", "--title", f"H16 resurrección: {t['sym']} ({cad}) {vol / t['base_h']:.0f}× volumen", "--body", cuerpo])
        aviso = "si" if r.returncode == 0 else "error"
    rows.append({"ts": ahora, "hora_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), "cadena": t["net"], "token": t["token"],
                 "sym": t["sym"], "revivio": t.get("revivio", 0), "precio": p["priceUsd"], "liq": round(liq), "mc": round(p.get("marketCap") or p.get("fdv") or 0),
                 "vol_h1": round(vol), "base_h": t["base_h"], "ratio": round(vol / t["base_h"], 1), "c1": c1, "pasa_liq": "si" if pasa else "no",
                 "seguridad": "ok" if not fallos else ",".join(fallos), "aviso": aviso, "pmax": p["priceUsd"], "pmin": p["priceUsd"],
                 "p6": "", "p24": "", "estado": "abierto"})
    nuevos += 1

guardar(rows)
print(f"muertos vigilados {len(muertos)} | disparos nuevos {nuevos} | abiertos seguidos {len(abiertos)}")
