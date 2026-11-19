"""Tres estudios en sombra (17-nov, pedidos por Fran). Solo registro paper; NO cambian ninguna regla de entrada. Sin Helius.

H27 "operadores de élite en tokens viejos": una billetera de datos/elite.tsv (scripts/elite.py, de la historia ya bajada)
     compra (logs de compras de A, B y C, últimas 12 h) un token con 7+ días, liquidez ≥30 mil y MC ≤100 M.
     Entra una vez, al precio del momento → datos/h27_sombra.tsv. salidas.py lo mide.
IMIT "nombres que imitan": candidatos del escaneo (estudio_reglas_sombra.tsv) cuyo símbolo imita una moneda estable
     (contiene USD, USDT, USDC, DAI, EUR…) o una moneda/marca conocida sin ser el contrato oficial (casos ZLUSD, "USDC",
     BONK en BNB, Costco…) → datos/imitadores.tsv con el precio del escaneo. salidas.py lo mide (hip IMIT).
BUNDLES: billeteras de distintos operadores que hicieron su primera compra del mismo token en el mismo minuto
     (historia vector_profundo + logs de compras por transacción). Si el mismo par compra junto en 3+ tokens
     (y en ≥30 % de los tokens del menos activo) se propone como un solo operador → datos/bundle_grupos.tsv; eventos en datos/bundles_eventos.tsv.
     No toca operadores.tsv: n_oper_bundle() en operadores.py permite contar con los grupos fusionados (solo estudio).
"""
import csv, json, os, re, sys, time, urllib.request
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from operadores import mapa

C27 = ["ts", "hora_utc", "cadena", "token", "sym", "precio", "liq", "mc", "liq_mc_pct", "edad_d", "n_elite", "elite", "pool", "motivo"]
CIM = ["ts", "hora_utc", "cadena", "token", "sym", "precio", "liq", "mc", "motivo", "estado_escaneo", "fallos"]

OFICIALES = {  # símbolo → contratos oficiales (Solana y BNB)
    "USDC": {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"},
    "USDT": {"Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCeKBsGQnYb", "0x55d398326f99059fF775485246999027B3197955"},
    "USD1": {"USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB", "0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d"},
    "PYUSD": {"2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo"},
    "SOL": {"So11111111111111111111111111111111111111112"}, "WSOL": {"So11111111111111111111111111111111111111112"},
    "BONK": {"DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"}, "WIF": {"EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"},
    "JUP": {"JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"}, "BTC": set(), "WBTC": set(), "ETH": set(), "WETH": set(),
    "BNB": set(), "WBNB": {"0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"}, "TRUMP": {"6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN"},
    "PEPE": set(), "DOGE": set(), "SHIB": set(), "XRP": set(), "CAKE": {"0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"},
}
MARCAS = ["COSTCO", "TESLA", "TSLA", "APPLE", "AAPL", "NVIDIA", "NVDA", "AMAZON", "AMZN", "GOOGLE", "GOOGL", "MICROSOFT", "MSFT",
          "NETFLIX", "NFLX", "NIKE", "PEPSI", "COCACOLA", "MCDONALDS", "STARBUCKS", "WALMART", "DISNEY", "BINANCE", "COINBASE",
          "ROBINHOOD", "BLACKROCK", "PAYPAL", "VISA", "MASTERCARD", "OPENAI", "CHATGPT", "SPACEX", "STARLINK", "TETHER", "CIRCLE"]
ESTABLE = re.compile(r"USD|USDT|USDC|DAI$|^DAI|EURC|EURO?$|PYUSD|FDUSD|TUSD", re.I)


def leer(f):
    return list(csv.DictReader(open(f), delimiter="\t")) if os.path.exists(f) else []


def guardar(f, campos, filas):
    if not filas:
        return
    nuevo = not os.path.exists(f)
    with open(f, "a", newline="") as fh:
        w = csv.DictWriter(fh, campos, delimiter="\t", extrasaction="ignore")
        if nuevo: w.writeheader()
        w.writerows(filas)


def dex(toks):
    out = {}
    for i in range(0, len(toks), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(toks[i:i + 30]), headers={"User-Agent": "desk-h27"})
            for p in json.load(urllib.request.urlopen(req, timeout=25)):
                a = p["baseToken"]["address"]
                if a not in out or ((p.get("liquidity") or {}).get("usd") or 0) > ((out[a].get("liquidity") or {}).get("usd") or 0):
                    out[a] = p
        except Exception as e:
            print("h27: dexscreener", str(e)[:60])
        time.sleep(0.3)
    return out


def imita(sym, token):
    s = re.sub(r"[^A-Z0-9]", "", (sym or "").upper())
    if not s:
        return ""
    if s in OFICIALES and token not in OFICIALES[s] and token.lower() not in {x.lower() for x in OFICIALES[s]}:
        return f"usa el símbolo de {s} sin ser el contrato oficial"
    if ESTABLE.search(s) and token not in OFICIALES.get(s, set()):
        return "imita moneda estable"
    for m in MARCAS:
        if m in s and len(m) >= 4:
            return f"imita marca {m}"
    return ""


def imitadores(ahora, hora):
    ya = {r["token"] for r in leer("datos/imitadores.tsv")}
    filas = []
    for r in leer("datos/estudio_reglas_sombra.tsv"):  # incluye el pasado: el precio es el del escaneo
        t = r["direccion"]
        if t in ya:
            continue
        mot = imita(r["simbolo"], t)
        if mot:
            ya.add(t)
            filas.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], cadena=r["cadena"], token=t, sym=r["simbolo"], precio=r["precio"],
                              liq=r["liq"], mc=r["mc"], motivo=mot, estado_escaneo=r.get("estado", ""), fallos=r.get("fallos", "")))
            print(f"IMIT: {r['simbolo']} {t} ({r['cadena']}): {mot}")
    return filas


def h27(ahora, hora):
    elite = {r["billetera"]: r["operador"] for r in leer("datos/elite.tsv")}
    if not elite:
        return []
    ya = {r["token"] for r in leer("datos/h27_sombra.tsv")}
    quien = defaultdict(set)
    for f in ("datos/consenso_A_compras.tsv", "datos/h22_compras.tsv", "datos/h23_compras.tsv", "datos/watchlist_compras.tsv"):
        for r in leer(f):
            try:
                ts = int(r["ts"])
            except (TypeError, ValueError):
                continue
            if r["billetera"] in elite and ahora - ts <= 12 * 3600 and r["token"] not in ya:
                quien[r["token"]].add(elite[r["billetera"]])
    if not quien:
        return []
    info = dex(list(quien))
    filas = []
    for t, ops in quien.items():
        p = info.get(t)
        if not p:
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        if edad >= 7 and liq >= 30000 and mc and mc <= 100e6:
            filas.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"),
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), edad_d=round(edad, 1),
                              n_elite=len(ops), elite=",".join(sorted(ops)), pool=p.get("pairAddress"),
                              motivo="operador de élite compra token viejo"))
            print(f"H27 entrada sombra: {p['baseToken']['symbol']} {t} élite {','.join(sorted(ops))}, edad {round(edad)} d, liq {round(liq):,}")
    return filas


def h33(ahora, hora, ventana=12 * 3600):
    """H33 "élite sola en lanzamiento" (18-nov, Fran, caso JESTER: ETZpZa, élite de oNuaeU, entró sola a un token de 1 día y va +94 %;
    no avisamos porque consenso A pide 2 operadores y H27 solo mira tokens de 7+ días). Un operador de élite (datos/elite.tsv) compra
    (logs de compras A/B/C, últimas 12 h) un token de menos de 48 h con liquidez ≥10 mil y MC ≤10 M, aunque esté solo.
    Entra una vez al precio del momento → datos/h33_sombra.tsv; salidas.py lo mide (escalonada, híbrida, copiar A). Solo registro."""
    el = {r["billetera"]: r for r in leer("datos/elite.tsv")}
    if not el:
        return []
    ya = {r["token"] for r in leer("datos/h33_sombra.tsv")}
    quien, sol = defaultdict(set), defaultdict(float)
    for f in ("datos/consenso_A_compras.tsv", "datos/h22_compras.tsv", "datos/h23_compras.tsv", "datos/watchlist_compras.tsv"):
        for r in leer(f):
            try:
                ts = int(r["ts"])
            except (TypeError, ValueError):
                continue
            b = r.get("billetera")
            if b in el and ahora - ts <= ventana and r.get("token") not in ya:
                quien[r["token"]].add(el[b]["operador"])
                try:
                    sol[r["token"]] += float(r.get("sol_gastado") or 0)
                except ValueError:
                    pass
    if not quien:
        return []
    info = dex(list(quien))
    hist = {}
    for r in el.values():
        hist.setdefault(r["operador"], r)
    filas = []
    for t, ops in quien.items():
        p = info.get(t)
        if not p:
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        if edad < 2 and liq >= 10000 and mc and mc <= 10e6:
            ch = p.get("priceChange") or {}
            h = "; ".join(f"{o}: {hist[o].get('jugadas')} jugadas, x2 {hist[o].get('pct_x2')} %, pnl {hist[o].get('pnl_sol')} SOL"
                          for o in sorted(ops) if o in hist)
            filas.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"),
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), edad_d=round(edad, 2),
                              n_elite=len(ops), elite=",".join(sorted(ops)), pool=p.get("pairAddress"),
                              motivo=f"élite sola en lanzamiento ({len(ops)} op., {round(sol[t], 1)} SOL), c1 {ch.get('h1')} %, c24 {ch.get('h24')} % | {h}"))
            print(f"H33 entrada sombra: {p['baseToken']['symbol']} {t} élite {','.join(sorted(ops))}, edad {round(edad * 24)} h, liq {round(liq):,}")
    return filas


def h34(ahora, hora, ventana=12 * 3600):
    """H34 "primera A con MC 60-150 mil" (19-nov, Fran aprobó la recomendación del estudio de la primera A: 2.039 casos de 75 días,
    entrar 1 min después de la primera A pierde −6,7 %; la única franja positiva en las dos mitades fue MC 60–150 mil al entrar,
    +11 % y +9 %, 121 casos, 19 ganadoras, sin top 5 +2 %). Una A sin bots compra (logs de compras, últimas 12 h) un token donde
    ninguna otra billetera nuestra (A/B/C) había entrado antes, y el MC al detectar está entre 60 y 150 mil. OJO: el estudio entra
    1 minuto después de la A; aquí detectamos con el retraso del escaneo, así que mide la franja con retraso. Solo registro."""
    import csv as _c
    op = {}
    for r in leer("datos/operadores.tsv"):
        op[r["billetera"]] = r
    ya = {r["token"] for r in leer("datos/h34_sombra.tsv")}
    previas = defaultdict(set)  # token -> billeteras nuestras vistas antes de la ventana
    for r in leer("datos/vector_profundo.tsv"):
        try:
            if int(float(r.get("primera_compra") or 0)) < ahora - ventana:
                previas[r["token"]].add(r["billetera"])
        except ValueError:
            pass
    for r in leer("datos/fotos_saldos.tsv"):
        try:
            if int(float(r["ts"])) < ahora - ventana and float(r.get("usd") or 0) > 0:
                previas[r["token"]].add(r["billetera"])
        except (TypeError, ValueError):
            pass
    compras = defaultdict(list)
    for f in ("datos/consenso_A_compras.tsv", "datos/h22_compras.tsv", "datos/h23_compras.tsv", "datos/watchlist_compras.tsv"):
        for r in leer(f):
            try:
                ts = int(r["ts"])
            except (TypeError, ValueError):
                continue
            compras[r["token"]].append((ts, r.get("billetera"), f))
            if ts < ahora - ventana:
                previas[r["token"]].add(r.get("billetera"))
    cand = {}
    for t, l in compras.items():
        if t in ya or previas.get(t):
            continue
        rec = sorted(x for x in l if ahora - x[0] <= ventana)
        if not rec:
            continue
        b = rec[0][1]
        o = op.get(b, {})
        if o.get("grupo") == "A" and o.get("bot") != "si":
            cand[t] = (b, o.get("operador", b[:6]), len({x[1] for x in rec}))
    if not cand:
        return []
    info = dex(list(cand))
    filas = []
    for t, (b, oper, n) in cand.items():
        p = info.get(t)
        if not p:
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        if 60e3 <= mc <= 150e3:
            edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
            ch = p.get("priceChange") or {}
            filas.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"),
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1) if mc else "", edad_d=round(edad, 2),
                              n_elite=n, elite=oper, pool=p.get("pairAddress"),
                              motivo=f"primera A ({oper}) sin otra nuestra antes, MC {round(mc):,} al detectar, c1 {ch.get('h1')} %, c24 {ch.get('h24')} % (detección con retraso del escaneo)"))
            print(f"H34 entrada sombra: {p['baseToken']['symbol']} {t} primera A {oper}, MC {round(mc):,}, liq {round(liq):,}")
    return filas


def bundles():
    m = mapa()
    compras = defaultdict(dict)  # token -> billetera -> ts primera compra
    for r in leer("datos/vector_profundo.tsv"):
        try:
            ts = int(float(r["primera_compra"]))
        except (TypeError, ValueError):
            continue
        if ts > 0 and float(r.get("compras") or 0) > 0:
            compras[r["token"]][r["billetera"]] = ts
    for f in ("datos/consenso_A_compras.tsv", "datos/h22_compras.tsv", "datos/h23_compras.tsv", "datos/watchlist_compras.tsv"):
        for r in leer(f):
            if r.get("firma") in ("", "foto"):  # la foto de cartera no tiene la hora de la transacción
                continue
            try:
                ts = int(r["ts"])
            except (TypeError, ValueError):
                continue
            d = compras[r["token"]]
            d[r["billetera"]] = min(d.get(r["billetera"], ts), ts)
    eventos, pares = [], defaultdict(set)
    for tok, d in compras.items():
        if len(d) < 3:
            continue
        orden = sorted(d.items(), key=lambda x: x[1])
        i = 0
        while i < len(orden):
            j = i
            while j + 1 < len(orden) and orden[j + 1][1] - orden[i][1] <= 60:
                j += 1
            grupo = [w for w, _ in orden[i:j + 1]]
            ops = {m.get(w, (w[:6], False))[0] for w in grupo if not m.get(w, ("", False))[1]}
            if len(ops) >= 3:
                eventos.append(dict(token=tok, ts=orden[i][1], hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(orden[i][1])),
                                    n_billeteras=len(grupo), n_oper=len(ops), billeteras=",".join(grupo)))
                for a in grupo:
                    for b in grupo:
                        if a < b:
                            pares[(a, b)].add(tok)
            i = j + 1
    # grupos: pares que compran juntos en 3+ tokens y en ≥30 % de los tokens de la billetera menos activa → unión
    # (17-nov: con "2+ tokens" salían 238 billeteras unidas por francotiradores de lanzamiento independientes)
    ntok = defaultdict(int)
    for d in compras.values():
        for w in d:
            ntok[w] += 1
    padre = {}

    def raiz(x):
        while padre.get(x, x) != x:
            x = padre[x]
        return x
    for (a, b), toks in pares.items():
        if len(toks) >= 3 and len(toks) >= 0.3 * min(ntok[a], ntok[b]):
            padre.setdefault(a, a); padre.setdefault(b, b)
            padre[raiz(a)] = raiz(b)
    grupos = defaultdict(list)
    for w in padre:
        grupos[raiz(w)].append(w)
    filas_g = []
    for r, ws in grupos.items():
        if len(ws) < 2:
            continue
        ops = sorted({m.get(w, (w[:6], False))[0] for w in ws})
        if len(ops) < 2:  # ya eran un solo operador
            continue
        n_tok = len({t for (a, b), toks in pares.items() if a in ws and b in ws and len(toks) >= 3 for t in toks})
        nombre = "bundle_" + sorted(ws)[0][:6]
        for w in sorted(ws):
            filas_g.append(dict(billetera=w, grupo_bundle=nombre, operador_actual=m.get(w, (w[:6], False))[0],
                                operadores_en_grupo=len(ops), billeteras_en_grupo=len(ws), tokens_juntos=n_tok))
    with open("datos/bundles_eventos.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, ["token", "ts", "hora_utc", "n_billeteras", "n_oper", "billeteras"], delimiter="\t")
        w.writeheader(); w.writerows(sorted((e for e in eventos if e["ts"] >= time.time() - 30 * 86400), key=lambda e: -e["ts"]))  # solo 30 d (tamaño)
    with open("datos/bundle_grupos.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, ["billetera", "grupo_bundle", "operador_actual", "operadores_en_grupo", "billeteras_en_grupo", "tokens_juntos"], delimiter="\t")
        w.writeheader(); w.writerows(filas_g)
    print(f"bundles: {len(eventos)} compras coordinadas (3+ operadores en el mismo minuto), "
          f"{len({g['grupo_bundle'] for g in filas_g})} grupos que se repiten ({len(filas_g)} billeteras)")


def main():
    ahora = int(time.time()); hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora))
    a = h27(ahora, hora); guardar("datos/h27_sombra.tsv", C27, a)
    b = imitadores(ahora, hora); guardar("datos/imitadores.tsv", CIM, b)
    try:
        c = h33(ahora, hora); guardar("datos/h33_sombra.tsv", C27, c)
        print(f"H33: {len(c)} entradas nuevas (élite sola en lanzamiento)")
    except Exception as e:
        print("h33 falló:", e)
    try:
        d = h34(ahora, hora); guardar("datos/h34_sombra.tsv", C27, d)
        print(f"H34: {len(d)} entradas nuevas (primera A con MC 60-150 mil)")
        # H34j (19-nov, Fran aprobó): misma H34 pero pool con <30 min de vida al detectar. Estudio 121 casos del rango:
        # pool <30 min n=49 +30,7 % (+27/+34 por mitad, sin top5 +12 %, 17 operadores); 30-120 min 0 de 14; >2 h +4,5 %.
        # Control: <30 min pierde en los otros rangos de MC. Ojo: el escaneo detecta con retraso, pocas filas esperadas.
        dj = [dict(f, motivo="H34 joven (pool <30 min): " + f["motivo"]) for f in d if float(f.get("edad_d") or 99) * 1440 < 30]
        guardar("datos/h34j_sombra.tsv", C27, dj)
        print(f"H34j: {len(dj)} entradas nuevas (H34 con pool <30 min)")
    except Exception as e:
        print("h34 falló:", e)
    if "--sin-bundles" not in sys.argv:
        bundles()
    print(f"H27: {len(a)} entradas nuevas; IMIT: {len(b)} nuevos")
    if os.environ.get("GITHUB_ACTIONS"):  # el reloj solo hace git add de algunos archivos
        import subprocess
        subprocess.run(["git", "add"] + [f for f in ("datos/h27_sombra.tsv", "datos/h33_sombra.tsv", "datos/h34_sombra.tsv", "datos/h34j_sombra.tsv", "datos/imitadores.tsv", "datos/bundles_eventos.tsv",
                                                    "datos/bundle_grupos.tsv", "datos/elite.tsv") if os.path.exists(f)], check=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("estudios 17-nov falló (no afecta el escaneo):", e)
