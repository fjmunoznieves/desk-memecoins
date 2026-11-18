"""H25 y H26: estudios en sombra (17-nov, pedido por Fran). Solo registro paper; NO cambian ninguna regla de entrada.

H25 "maduros con A": token con 7 días o más, 2+ operadores A (sin bots) que SOSTIENEN (última foto de saldos, ≥20 USD c/u),
     liquidez ≥ 75 mil USD y volumen de 24 h ≥ 50 mil USD (el de 5 min no sirve en tokens maduros). Candidatos: seguimiento + sostenidas de los últimos 3 días.
H26 "lanzamientos con liquidez sana": candidatos del escaneo (estudio_reglas_sombra.tsv) con liquidez 100–250 mil USD y
     liquidez/MC entre 5 y 15 %, y que pase la revisión de seguridad (top10, dev, LP, mint/freeze).
Cada token entra una sola vez, al precio del momento. salidas.py mide sus salidas (escalonada y "copiar A")."""
import csv, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from operadores import mapa

CAMPOS = ["ts", "hora_utc", "cadena", "token", "sym", "precio", "liq", "mc", "liq_mc_pct", "vol1h", "edad_d", "n_oper", "operadores", "pool", "motivo"]


def leer(f):
    return list(csv.DictReader(open(f), delimiter="\t")) if os.path.exists(f) else []


def guardar(f, filas):
    if not filas:
        return
    nuevo = not os.path.exists(f)
    with open(f, "a", newline="") as fh:
        w = csv.DictWriter(fh, CAMPOS, delimiter="\t", extrasaction="ignore")
        if nuevo: w.writeheader()
        w.writerows(filas)


def dex(cadena, toks):
    out = {}
    for i in range(0, len(toks), 30):
        try:
            req = urllib.request.Request(f"https://api.dexscreener.com/tokens/v1/{cadena}/" + ",".join(toks[i:i + 30]), headers={"User-Agent": "desk-h25"})
            for p in json.load(urllib.request.urlopen(req, timeout=25)):
                a = p["baseToken"]["address"]
                if a not in out or ((p.get("liquidity") or {}).get("usd") or 0) > ((out[a].get("liquidity") or {}).get("usd") or 0):
                    out[a] = p
        except Exception as e:
            print("h25: dexscreener", str(e)[:60])
        time.sleep(0.3)
    return out


NO_MEMES = {"EURC", "PYUSD", "USDG", "USD1", "SKR", "BIRB", "JUP", "JTO", "PYTH", "DRIFT", "KMNO", "RENDER", "WIF", "BONK", "PENGU",
            "TRUMP", "MELANIA", "MNDE", "ME", "HUMA", "WINGS", "BMT", "DBR", "VIRTUAL", "CASH", "BP", "PUMP", "ZEC", "HYPE"}


def no_meme(t, sym):
    """18-nov (Fran vio USDG, EURC, TTWO, ANTHROPIC… en H25): fuera estables, acciones tokenizadas y tokens grandes/de proyecto."""
    S = sym.upper()
    if "USD" in S or S in NO_MEMES:
        return True
    if t.startswith("Xs") or (sym.endswith("x") and S[:-1].isalpha() and len(S) <= 6):  # xStocks (NVDAx, SPYx…)
        return True
    # acciones de Backpack/PreStocks y tokens oficiales usan dirección vanidosa con el ticker (TTWofw…, Pren1F… no; SPCXx…)
    if not t.endswith("pump") and len(S) >= 3 and t.upper().startswith(S[:4]):
        return True
    return S in {"ANTHROPIC", "OPENAI", "SPACEX", "KALSHI"}


def h25(ahora, hora):
    ya = {r["token"] for r in leer("datos/h25_sombra.tsv")}
    cand = {r["token"]: r["sym"] for r in leer("datos/seguimiento.tsv")}
    for r in leer("datos/alertas_sostenidas.tsv"):
        if ahora - int(r["ts"]) < 3 * 86400:
            cand.setdefault(r["token"], r["sym"])
    cand = {t: s for t, s in cand.items() if t not in ya}
    if not cand:
        return []
    # quién sostiene: última foto de saldos de cada token
    fs = leer("datos/fotos_saldos.tsv")
    ult = {}
    for r in fs:
        ult[r["token"]] = max(ult.get(r["token"], 0), int(r["ts"]))
    m = mapa()
    sost = {}
    for r in fs:
        if r["token"] in cand and int(r["ts"]) == ult[r["token"]] and r.get("grupo") == "A" and float(r["usd"] or 0) >= 20:
            op, bot = m.get(r["billetera"], (r["billetera"][:6], False))
            if not bot:
                sost.setdefault(r["token"], set()).add(op)
    info = dex("solana", list(cand))
    filas = []
    for t, s in cand.items():
        p = info.get(t)
        ops = sost.get(t, set())
        if not p or len(ops) < 2 or no_meme(t, p["baseToken"].get("symbol", "")):
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        v1 = (p.get("volume") or {}).get("h1") or 0
        v24 = (p.get("volume") or {}).get("h24") or 0
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        if edad >= 7 and liq >= 75000 and v24 >= 50000 and mc and mc <= 100e6:
            filas.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"),
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), vol1h=round(v1), edad_d=round(edad, 1),
                              n_oper=len(ops), operadores=",".join(sorted(ops)), pool=p.get("pairAddress"),
                              motivo="maduro con 2+ operadores A sosteniendo"))
            print(f"H25 entrada sombra: {p['baseToken']['symbol']} {t} {len(ops)} operadores A, liq {round(liq):,}, edad {round(edad)} d")
    return filas


def h29(ahora, hora):
    """H29 "impulso sano" (18-nov, Fran aprobó tras el estudio de impulso: 456 consensos A con velas → "no perseguir + MC ≤2M"
    a 24 h dio +541 USD con 20 USD por entrada, 42 % ganan; perseguir: 93 % cae −35 %). Solo sombra, no cambia reglas.
    Entra si: 2+ operadores A (sin bots) sostienen ≥20 USD c/u en la última foto, token ≥3 días, cambio 24 h ≤ +30 %,
    cambio 1 h ≤ +10 %, MC ≤ 2 M, liquidez ≥ 10 mil, es meme, y los holders no bajaron >3 % entre las dos últimas fotos."""
    ya = {r["token"] for r in leer("datos/h29_sombra.tsv")}
    fs = leer("datos/fotos_saldos.tsv")
    ult = {}
    for r in fs:
        ult[r["token"]] = max(ult.get(r["token"], 0), int(r["ts"]))
    m = mapa()
    sost = {}
    for r in fs:
        if r["token"] not in ya and int(r["ts"]) == ult[r["token"]] and ahora - int(r["ts"]) < 86400 \
                and r.get("grupo") == "A" and float(r["usd"] or 0) >= 20:
            op, bot = m.get(r["billetera"], (r["billetera"][:6], False))
            if not bot:
                sost.setdefault(r["token"], set()).add(op)
    cand = [t for t, o in sost.items() if len(o) >= 2]
    if not cand:
        return []
    hold = {}
    for r in leer("datos/liquidez_seguimiento.tsv"):
        try:
            hold.setdefault(r["token"], []).append((int(r["ts"]), float(r["holders"])))
        except (TypeError, ValueError, KeyError):
            pass
    info = dex("solana", cand)
    filas = []
    for t in cand:
        p = info.get(t)
        if not p or no_meme(t, p["baseToken"].get("symbol", "")):
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        ch = p.get("priceChange") or {}
        c24, c1 = ch.get("h24"), ch.get("h1")
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        v24 = (p.get("volume") or {}).get("h24") or 0
        h = sorted(hold.get(t, []))
        dh = round(100 * (h[-1][1] / h[-2][1] - 1), 1) if len(h) >= 2 and h[-2][1] else None
        if edad >= 3 and c24 is not None and c24 <= 30 and (c1 or 0) <= 10 and mc and mc <= 2e6 and liq >= 10000 \
                and (dh is None or dh >= -3):
            ops = sost[t]
            filas.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"),
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), vol1h=round((p.get("volume") or {}).get("h1") or 0),
                              edad_d=round(edad, 1), n_oper=len(ops), operadores=",".join(sorted(ops)), pool=p.get("pairAddress"),
                              motivo=f"impulso sano: c24 {c24} %, c1 {c1} %, holders {'sin dato' if dh is None else str(dh) + ' %'}"
                                     + "".join(f" | {x}" for x in (
                                         ["rebote"] if c24 <= -30 else []) + (["vol24 20k-500k"] if 20000 <= v24 <= 500000 else []) + (
                                         ["3+ A"] if len(ops) >= 3 else []) + (["MC<100k"] if mc < 100000 else []) + (
                                         ["holders suben"] if dh is not None and dh > 5 else []))))
            print(f"H29 entrada sombra: {p['baseToken']['symbol']} {t} {len(ops)} operadores A, c24 {c24} %, MC {round(mc):,}")
    return filas


SEGURIDAD = ("lp", "top10", "dev", "no renunciado", "seg?", "ballena", "impuestos", "control")


def h30(ahora, hora):
    """H30 "lanzamiento sano" (18-nov, Fran): carril chico en sombra (10 USD). Del estudio de 268 lanzamientos: sobreviven los de
    volumen 5 min ≥150k (73 % terminan arriba) o liquidez 75–150k (mediana +6 %); mueren los de compras/ventas >2 o +10 % en 5 min,
    y los de BNB contra WBNB/USDT (81 %). Entra si: v5 ≥150k, liq 75–150k, b/s ≤2, cambio 5 min ≤ +10 %, sin fallos de seguridad,
    pool no contra WBNB/USDT. Solo registro."""
    ya = {r["token"] for r in leer("datos/h30_sombra.tsv")}
    filas = []
    for r in leer("datos/estudio_reglas_sombra.tsv"):
        t = r["direccion"]
        if t in ya or ahora - int(r["ts"]) > 6 * 3600:
            continue
        try:
            liq, mc, v5, bs5, c5 = (float(r[k]) for k in ("liq", "mc", "v5", "bs5", "c5"))
        except (TypeError, ValueError, KeyError):
            continue
        fallos = (r.get("fallos") or "").lower()
        if any(x in fallos for x in SEGURIDAD) or r.get("quote") in ("WBNB", "USDT"):
            continue
        if v5 >= 150000 and 75000 <= liq <= 150000 and bs5 <= 2 and c5 <= 10:
            ya.add(t)
            filas.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], cadena=r["cadena"], token=t, sym=r["simbolo"], precio=r["precio"],
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1) if mc else "", vol1h="", edad_d="",
                              n_oper="", operadores="", pool=r.get("pool", ""),
                              motivo=f"lanzamiento sano: v5 {round(v5):,}, b/s {bs5}, c5 {c5} %, quote {r.get('quote')}"))
            print(f"H30 entrada sombra: {r['simbolo']} {t} ({r['cadena']}) v5 {round(v5):,} liq {round(liq):,}")
    return filas


def h26(ahora, hora):
    ya = {r["token"] for r in leer("datos/h26_sombra.tsv")}
    filas = []
    for r in leer("datos/estudio_reglas_sombra.tsv"):
        t = r["direccion"]
        if t in ya or ahora - int(r["ts"]) > 6 * 3600:  # solo candidatos recientes (no reconstruye el pasado)
            continue
        try:
            liq, mc = float(r["liq"]), float(r["mc"])
        except (TypeError, ValueError):
            continue
        if r.get("fallos"):  # 17-nov (caso GTA, rug -99 %): además debe pasar la revisión de seguridad
            continue
        if 100000 <= liq <= 250000 and mc and 5 <= 100 * liq / mc <= 15:
            ya.add(t)
            filas.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], cadena=r["cadena"], token=t, sym=r["simbolo"], precio=r["precio"],
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), vol1h="", edad_d="", n_oper="", operadores="",
                              pool=r.get("pool", ""), motivo="lanzamiento con liquidez 100-250k y liq/MC 5-15 %"))
            print(f"H26 entrada sombra: {r['simbolo']} {t} ({r['cadena']}) liq {round(liq):,}")
    return filas


def main():
    ahora = int(time.time()); hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora))
    a, b = h25(ahora, hora), h26(ahora, hora)
    guardar("datos/h25_sombra.tsv", a); guardar("datos/h26_sombra.tsv", b)
    print(f"H25: {len(a)} entradas nuevas; H26: {len(b)} entradas nuevas")
    try:
        c = h29(ahora, hora)
        guardar("datos/h29_sombra.tsv", c)
        print(f"H29: {len(c)} entradas nuevas")
    except Exception as e:
        print("h29 falló:", e)
    try:
        d = h30(ahora, hora)
        guardar("datos/h30_sombra.tsv", d)
        print(f"H30: {len(d)} entradas nuevas")
    except Exception as e:
        print("h30 falló:", e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("h25/h26 falló (no afecta el escaneo):", e)
