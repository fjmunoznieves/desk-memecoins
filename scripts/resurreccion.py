"""H16 paso horario (solo sombra, paper): ¿algún token muerto despertó?

Disparo: volumen de la última hora (todas sus pools en DexScreener) ≥ 5× su base por hora
y precio de la última hora en verde. Se registra TODO disparo en datos/h16_resurrecciones.tsv;
solo se abre un aviso (issue) si la liquidez es ≥ 30k USD y la revisión de seguridad pasa.
Cada hora también sigue los disparos abiertos: máximo y mínimo vistos, precio a +6 h y a +24 h.
"""
import atexit as _atexit, os as _os, subprocess as _sp


def _stage_reloj():
    """17-nov: el reloj (último paso antes de "Guardar") solo hacía git add de 4 archivos; los demás que escriben
    watch_solana, salidas, fotos, etc. quedaban sin preparar y el git pull --rebase fallaba → el push NO se hacía y
    se perdía todo el estado de la corrida (pasó el 17-nov 06:27 UTC). Aquí se prepara todo datos/."""
    if _os.environ.get("GITHUB_ACTIONS") and _os.environ.get("GITHUB_WORKFLOW", "").startswith("Reloj"):
        _sp.run(["git", "add", "-A", "datos"], check=False)


_atexit.register(_stage_reloj)
import csv, json, os, subprocess, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from seguridad import revisar
import statistics
from muertos import cargar, guardar as guardar_estado, UMBRAL, BASE_MIN

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


VOL6 = {}  # volumen de 6 h sumado: el reloj corre cada 2 h 30 min y no debe perder un pico entre corridas


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
            VOL6[(cadena, a)] = VOL6.get((cadena, a), 0) + ((p.get("volume") or {}).get("h6") or 0)
            liq = lambda q: ((q or {}).get("liquidity") or {}).get("usd") or 0
            if mejor is None or liq(p) > liq(mejor):
                mejor = p
            res[a] = (vol, mejor)
        time.sleep(0.4)
    return res


ahora = int(time.time())
hoy = time.strftime("%Y-%m-%d", time.gmtime(ahora))
rows = leer()
prev = cargar()
estado = prev.get("estado", {})
con_historia = [e for e in estado.values() if "ultimo_arriba" in e]
abiertos = [r for r in rows if r["estado"] == "abierto"]
porcadena = {}
for e in con_historia:
    porcadena.setdefault(e["net"], set()).add(e["token"])
for r in abiertos:  # los disparos abiertos se siguen aunque ya no estén muertos
    porcadena.setdefault(r["cadena"], set()).add(r["token"])

datos = {}
for cadena, toks in porcadena.items():
    datos.update({(cadena, a): v for a, v in consultar(cadena, sorted(toks)).items()})

# 0) mantener al día quién está muerto (sin pedir velas otra vez)
muertos = []
for e in con_historia:
    if e.get("muerto"):  # muerto ANTES de esta consulta: candidato a disparo con su base anterior
        muertos.append(dict(e))
    vol, p = datos.get((e["net"], e["token"]), (0, None))
    if p and p.get("priceUsd"):
        precio = float(p["priceUsd"])
        e["pico"] = max(e["pico"], precio)
        if precio > UMBRAL * e["pico"]:
            e["ultimo_arriba"] = ahora
        e.setdefault("vols", {})[hoy] = max(e["vols"].get(hoy, 0), (p.get("volume") or {}).get("h24") or 0)
        e["vols"] = dict(sorted(e["vols"].items())[-7:])
        e["base_h"] = round(max(statistics.median(e["vols"].values()) / 24, BASE_MIN), 2)
    e["muerto"] = ahora - e["ultimo_arriba"] >= 7 * 86400
guardar_estado(prev, estado)

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
    vol1, p = datos[k]
    pc = (p.get("priceChange") or {}) if p else {}
    c1, c6 = pc.get("h1") or 0, pc.get("h6") or 0
    # ritmo por hora: el mayor entre la última hora y el promedio de las últimas 6 h
    vol = max(vol1, VOL6.get(k, 0) / 6)
    if not p or not p.get("priceUsd") or vol < VOL_MIN or vol < RATIO * t["base_h"] or (c1 <= 0 and c6 <= 0):
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
            f"- Volumen por hora (última hora o promedio de 6 h): {vol:,.0f} USD, {vol / t['base_h']:.1f}× su base ({t['base_h']:,.0f} USD/h)",
            f"- Precio 1 h: {c1}% | 6 h: {c6}% | Liquidez: {liq:,.0f} USD | MC: {(p.get('marketCap') or p.get('fdv') or 0):,.0f} USD",
            f"- Revivió antes en el estudio: {t.get('revivio', 0)} veces",
            "", "Del estudio: entrar solo por el disparo es casi una moneda al aire; mirar si hay pool nueva o token hijo, y respetar stop −20 %."])
        r = subprocess.run(["gh", "issue", "create", "--title", f"H16 resurrección: {t['sym']} ({cad}) {vol / t['base_h']:.0f}× volumen", "--body", cuerpo])
        aviso = "si" if r.returncode == 0 else "error"
    rows.append({"ts": ahora, "hora_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), "cadena": t["net"], "token": t["token"],
                 "sym": t["sym"], "revivio": t.get("revivio", 0), "precio": p["priceUsd"], "liq": round(liq), "mc": round(p.get("marketCap") or p.get("fdv") or 0),
                 "vol_h1": round(vol), "base_h": t["base_h"], "ratio": round(vol / t["base_h"], 1), "c1": c1 if vol == vol1 else c6, "pasa_liq": "si" if pasa else "no",
                 "seguridad": "ok" if not fallos else ",".join(fallos), "aviso": aviso, "pmax": p["priceUsd"], "pmin": p["priceUsd"],
                 "p6": "", "p24": "", "estado": "abierto"})
    nuevos += 1

guardar(rows)
print(f"muertos vigilados {len(muertos)} | disparos nuevos {nuevos} | abiertos seguidos {len(abiertos)}")
