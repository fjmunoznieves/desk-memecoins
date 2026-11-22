"""H25 y H26: estudios en sombra (17-nov, pedido por Fran). Solo registro paper; NO cambian ninguna regla de entrada.

H25 "maduros con A": token con 7 días o más, 2+ operadores A (sin bots) que SOSTIENEN (última foto de saldos, ≥20 USD c/u),
     liquidez ≥ 75 mil USD y volumen de 24 h ≥ 50 mil USD (el de 5 min no sirve en tokens maduros). Candidatos: seguimiento + sostenidas de los últimos 3 días.
H26 "lanzamientos con liquidez sana": candidatos del escaneo (estudio_reglas_sombra.tsv) con liquidez 100–250 mil USD y
     liquidez/MC entre 5 y 15 %, y que pase la revisión de seguridad (top10, dev, LP, mint/freeze).
Cada token entra una sola vez, al precio del momento. salidas.py mide sus salidas (escalonada y "copiar A")."""
import csv, json, os, sys, time, urllib.error, urllib.request
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


ATH = "datos/ath_cache.json"


def ath_de(toks, info):
    """Máximo histórico por token (velas diarias de GeckoTerminal, en caché 24 h; luego se actualiza con el precio de cada escaneo)."""
    try:
        cache = json.load(open(ATH))
    except Exception:
        cache = {}
    ahora, t0 = time.time(), time.time()
    for t in toks:
        p = info.get(t)
        if not p:
            continue
        precio = float(p.get("priceUsd") or 0)
        c = cache.get(t)
        if (not c or ahora - c["ts"] > 86400) and time.time() - t0 < 150:
            try:
                url = (f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{p['pairAddress']}/ohlcv/day"
                       f"?aggregate=1&limit=180&currency=usd&token={t}")
                req = urllib.request.Request(url, headers={"User-Agent": "desk-h31", "Accept": "application/json"})
                try:
                    v = json.load(urllib.request.urlopen(req, timeout=25))["data"]["attributes"]["ohlcv_list"]
                except urllib.error.HTTPError as e:
                    if e.code != 429:
                        raise
                    time.sleep(8)
                    v = json.load(urllib.request.urlopen(req, timeout=25))["data"]["attributes"]["ohlcv_list"]
                c = {"ts": ahora, "ath": max([x[2] for x in v] + [precio, (c or {}).get("ath", 0)])}
                cache[t] = c
            except Exception as e:
                print("h31: geckoterminal", t[:8], str(e)[:50])
            time.sleep(2.2)
        if c:
            c["ath"] = max(c["ath"], precio)
    json.dump(cache, open(ATH, "w"))
    return {t: c["ath"] for t, c in cache.items()}


def h31(ahora, hora):
    """H31 "pozo + chispa" (18-nov, Fran: A/B/C confirman interés, hay que detectar qué provoca el impulso). Estudio de precursores
    (290 tokens con A dentro, velas 1 h, 4.397 casos): el volumen solo no anticipa; el pozo (≥75 % bajo su máximo, A dentro) hace x2
    en 7 d 1 de cada 3 (base 16 %); pozo + chispa (sube 5–15 % en 1 h con volumen de la hora ≥2× el promedio) es la mejor relación
    x2/caída (2,2). Dos carriles en sombra, 10 USD c/u: H31 = pozo + chispa (h31_sombra.tsv); H31p = pozo quieto, cambio 6 h entre
    −20 y +15 % (h31p_sombra.tsv). Requiere 1+ operador A (sin bots) con ≥20 USD en la última foto, es meme, edad ≥3 d, liq ≥10 mil,
    MC ≤10 M. Holders y compras/ventas (liquidez_seguimiento) van como etiqueta para medir si anticipan. Solo registro."""
    ya1 = {r["token"] for r in leer("datos/h31_sombra.tsv")}
    ya2 = {r["token"] for r in leer("datos/h31p_sombra.tsv")}
    fs = leer("datos/fotos_saldos.tsv")
    if not fs:
        return [], []
    mx = max(int(r["ts"]) for r in fs)
    m = mapa()
    sost = {}
    for r in fs:
        try:
            if int(r["ts"]) > mx - 86400 and ahora - mx < 86400 and r.get("grupo") == "A" and float(r["usd"] or 0) >= 20:
                op, bot = m.get(r["billetera"], (r["billetera"][:6], False))
                if not bot:
                    sost.setdefault(r["token"], set()).add(op)
        except ValueError:
            pass
    info = dex("solana", list(sost))
    cand = [t for t in sost if t in info and not no_meme(t, info[t]["baseToken"].get("symbol", ""))]
    aths = ath_de(cand, info)
    liqs = {}
    for r in leer("datos/liquidez_seguimiento.tsv"):
        liqs.setdefault(r["token"], []).append(r)
    f1, f2 = [], []
    for t in cand:
        p = info[t]
        precio = float(p.get("priceUsd") or 0)
        ath = aths.get(t)
        if not precio or not ath:
            continue
        dd = 100 * (precio / ath - 1)
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        ch, vol = p.get("priceChange") or {}, p.get("volume") or {}
        c1, c6, c24 = ch.get("h1") or 0, ch.get("h6") or 0, ch.get("h24") or 0
        v1, v24 = vol.get("h1") or 0, vol.get("h24") or 0
        vx = v1 / (v24 / 24) if v24 else 0
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        if dd > -75 or edad < 3 or liq < 10000 or not mc or mc > 10e6:
            continue
        hs = sorted(liqs.get(t, []), key=lambda r: int(r["ts"]))
        try:
            dh = round(100 * (float(hs[-1]["holders"]) / float(hs[-2]["holders"]) - 1), 1)
        except (IndexError, ValueError, ZeroDivisionError, KeyError):
            dh = None
        tx = (p.get("txns") or {}).get("h1") or {}
        bs = round(tx.get("buys", 0) / tx["sells"], 2) if tx.get("sells") else None
        ops = sost[t]
        fila = dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"),
                    liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), vol1h=round(v1), edad_d=round(edad, 1),
                    n_oper=len(ops), operadores=",".join(sorted(ops)), pool=p.get("pairAddress"))
        etiq = (f"dd {round(dd)} %, c1 {c1} %, c6 {c6} %, c24 {c24} %, vol 1 h x{round(vx, 1)}, "
                f"holders {'sin dato' if dh is None else str(dh) + ' %'}, compras/ventas 1 h {bs if bs is not None else 'sin dato'}")
        if 5 <= c1 <= 15 and vx >= 2 and t not in ya1:
            f1.append(dict(fila, motivo="pozo + chispa: " + etiq)); ya1.add(t)
            print(f"H31 entrada sombra: {fila['sym']} {t} {etiq}")
        elif -20 <= c6 <= 15 and c1 > -10 and t not in ya2:
            f2.append(dict(fila, motivo="pozo quieto: " + etiq)); ya2.add(t)
            print(f"H31p entrada sombra: {fila['sym']} {t} {etiq}")
    h31.sost = sost
    return f1, f2


def h31s(ahora, hora, extra=None):
    """H31s "pozo + chispa SIN A" (18-nov, Fran, caso hotdog: −95 % en el pozo, chispa a las 8 AM, x9, sin billeteras nuestras).
    Mismo criterio que H31 pero sobre todo el universo de los escaneos de las últimas 24 h (datos/universo_escaneos.tsv, Solana):
    ≥75 % bajo su máximo, cambio 1 h entre +5 y +15 % (dato), volumen de la hora ≥2× el promedio (sin mínimo; volumen y operaciones como etiqueta), meme, edad ≥3 d (dato), liq ≥10 mil y MC ≤10 M (criterio, sin histórico de liquidez/MC).
    Etiqueta holders/compradores netos (Jupiter) y si hay A dentro, para medir si las A suman. Solo registro → datos/h31s_sombra.tsv."""
    ya = {r["token"] for r in leer("datos/h31s_sombra.tsv")}
    uni, jup = {}, {}
    for r in leer("datos/universo_escaneos.tsv"):
        try:
            if r["cadena"] == "solana" and ahora - int(r["ts"]) < 86400 and float(r["liq"] or 0) >= 10000:
                uni[r["token"]] = r["sym"]
                if r.get("hold_chg1h"):
                    jup[r["token"]] = r
        except (ValueError, KeyError):
            pass
    for t in extra or []:
        uni.setdefault(t, "")
    uni = [t for t in uni if t not in ya]
    info = dex("solana", uni)
    pre = []
    for t, p in info.items():
        ch, vol = p.get("priceChange") or {}, p.get("volume") or {}
        c1, v1, v24 = ch.get("h1") or 0, vol.get("h1") or 0, vol.get("h24") or 0
        vx = v1 / (v24 / 24) if v24 else 0
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        # 18-nov: sin mínimo de volumen. En el histórico (569 pozo+chispa con A, 75 d) la chispa con volumen de la hora <2 mil USD
        # rindió mejor (x2 7 d 45 %, cae −35 % 10 %) que ≥2 mil (39 % / 29 %); >10 mil fue lo peor. Volumen y operaciones van como etiqueta.
        # 18-nov auditoría (569 pozo+chispa, 75 d): c1 5-15 % ratio x2/caída 3,1; 15-30 % 1,6; 30-60 % 0,9 → solo 5-15.
        # Edad: 1-3 d ratio 1,2 (n=23), 3-7 d 1,9, 7-14 d 2,2, ≥14 d 3,2 → mínimo 3 d.
        if 5 <= c1 <= 15 and vx >= 2 and liq >= 10000 and mc and mc <= 10e6 and edad >= 3 and not no_meme(t, p["baseToken"].get("symbol", "")):
            pre.append((t, c1, vx, edad, liq, mc))
    if not pre:
        return []
    aths = ath_de([x[0] for x in pre][:30], info)
    sost = getattr(h31, "sost", {})
    out = []
    for t, c1, vx, edad, liq, mc in pre[:30]:
        p = info[t]
        precio = float(p.get("priceUsd") or 0)
        if not aths.get(t) or not precio:
            continue
        dd = 100 * (precio / aths[t] - 1)
        if dd > -75:
            continue
        j = jup.get(t, {})
        tx = (p.get("txns") or {}).get("h1") or {}
        ops = sost.get(t, set())
        out.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd"), liq=round(liq),
                        mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1), vol1h=round((p.get("volume") or {}).get("h1") or 0), edad_d=round(edad, 1),
                        n_oper=len(ops), operadores=",".join(sorted(ops)), pool=p.get("pairAddress"),
                        motivo=f"pozo + chispa sin A: dd {round(dd)} %, c1 {c1} %, vol 1 h {round((p.get('volume') or {}).get('h1') or 0)} USD x{round(vx, 1)}, compras/ventas 1 h {tx.get('buys')}/{tx.get('sells')}, "
                               f"holders 1 h {j.get('hold_chg1h') or 'sin dato'} %, netos 1 h {j.get('netos1h') or 'sin dato'}, A dentro {len(ops)}"))
        print(f"H31s entrada sombra: {p['baseToken']['symbol']} {t} {out[-1]['motivo']}")
    return out


MICRO = {"dacity": r"dacity|audacity", "gta": r"\bgta|grand theft|leonida", "anthropic": r"anthropi|claud|klaud", "nvidia": r"nvidia|jensen",
         "musk": r"musk|tesla|spacex|elon", "trump": r"trump|barron|maga\b", "over_back": r"nigga|its over|so back|there is hope",
         "milker": r"milker|titt|lactator", "pokemon": r"poke", "perro": r"\binu\b|inu$|doge|\bdog\b|dog$", "gato": r"\bcat\b|cat$|miao|meow|猫",
         "china": r"\bhao\b|chinese|china|[一-鿿]", "brainrot": r"tung|sahur", "negocios": r"business|\bbiz", "ia": r"\bai\b|agent|gpt|openai|\bbot\b",
         "pepe": r"pepe|\bapu\b|frog"}
PARADAS = set("""about after again board breaking coin crypto decline down explores fast fund grid hikes into live make market markets meet minutes
name new news official payments plan prediction price production projects rate reports retail sales says seeks services session states
stock threat time tokenized worker with world from that this have will their than they what when your more over band bigger halts outage
says hasn't worked intents energization monopoly""".split())


def h32(ahora, hora, sost):
    """H32 "tema dormido que despierta" (18-nov, Fran). Estudio previo (256 tokens con A, velas 75 d): que un token de una temática estalle
    NO hace rebotar a los caídos de su misma temática (x2 en 48 h 18-19 % igual que el control) → el contagio por temática amplia no
    sirve; falta probar el disparador externo (noticia). Registra en sombra (10 USD) tokens del universo A (tabla_A, memes con liq ≥10 mil)
    cuando (a) una palabra de un tema caliente en noticias/X (narrativas.json, calor ≥70) aparece en su nombre, o (b) otro token de su
    misma micro-narrativa sube ≥+100 % en 24 h. Etiqueta si está en pozo (≤−75 % de su máximo) y cuántas A tiene dentro. Solo registro."""
    import re
    ya = {}
    for r in leer("datos/h32_sombra.tsv"):
        ya[r["token"]] = max(ya.get(r["token"], 0), int(r["ts"]))
    try:
        filas = json.load(open("datos/tabla_A.json"))["filas"]
    except Exception:
        return []
    uni = [r["token"] for r in filas if r.get("tipo") == "meme" and (r.get("liq") or 0) >= 10000 and (r.get("mc") or 0) <= 20e6]
    uni = list(dict.fromkeys(uni + list(sost)))
    info = dex("solana", uni)
    nom = {t: (p["baseToken"].get("symbol", ""), p["baseToken"].get("name", "")) for t, p in info.items()}
    vivos = {}
    for t, p in info.items():
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        edad = (ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7
        if liq >= 10000 and mc and mc <= 10e6 and edad >= 3 and not no_meme(t, nom[t][0]):
            vivos[t] = p
    def micros(t):
        s = (nom[t][0] + " " + nom[t][1]).lower()
        return {k for k, rx in MICRO.items() if re.search(rx, s)}
    disp = {}
    # (a) noticia / tema caliente
    try:
        narr = json.load(open("datos/narrativas.json")).get("narrativas", [])
    except Exception:
        narr = []
    for n in narr:
        if (n.get("calor") or 0) < 70:
            continue
        pal = {w for w in re.findall(r"[a-z0-9]{4,}", n["tema"].lower()) if w not in PARADAS}
        pal |= {w.lower() for w in re.findall(r"\b[A-Z]{3}\b", n["tema"]) if w.lower() not in ("ceo", "ipo", "fed", "cpi", "etf", "usa", "sec")}
        for t in vivos:
            nw = set(re.findall(r"[a-z0-9]{3,}", (nom[t][0] + " " + nom[t][1]).lower()))
            com = pal & nw
            if com:
                disp.setdefault(t, f"noticia: '{n['tema']}' ({'+'.join(n.get('fuentes', []))}, calor {n['calor']}) palabra {','.join(sorted(com))}")
    # (b) contagio de micro-narrativa
    for t, p in vivos.items():
        c24 = (p.get("priceChange") or {}).get("h24") or 0
        if c24 >= 100:
            for k in micros(t):
                for u in vivos:
                    if u != t and k in micros(u):
                        disp.setdefault(u, f"contagio: {nom[t][0]} +{round(c24)} % en 24 h (narrativa {k})")
    disp = {t: m for t, m in disp.items() if ahora - ya.get(t, 0) > 72 * 3600}
    if not disp:
        return []
    aths = ath_de(list(disp)[:40], info)
    out = []
    for t, motivo in list(disp.items())[:40]:
        p = info[t]
        precio = float(p.get("priceUsd") or 0)
        dd = round(100 * (precio / aths[t] - 1)) if aths.get(t) and precio else None
        liq = (p.get("liquidity") or {}).get("usd") or 0
        mc = p.get("marketCap") or p.get("fdv") or 0
        ch = p.get("priceChange") or {}
        ops = sost.get(t, set())
        out.append(dict(ts=ahora, hora_utc=hora, cadena="solana", token=t, sym=nom[t][0], precio=p.get("priceUsd"), liq=round(liq), mc=round(mc),
                        liq_mc_pct=round(100 * liq / mc, 1), vol1h=round((p.get("volume") or {}).get("h1") or 0),
                        edad_d=round((ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7, 1), n_oper=len(ops),
                        operadores=",".join(sorted(ops)), pool=p.get("pairAddress"),
                        motivo=f"{motivo} | {'pozo' if dd is not None and dd <= -75 else 'no pozo'} (dd {dd} %), c1 {ch.get('h1')} %, c24 {ch.get('h24')} %, A dentro {len(ops)}"))
        print(f"H32 entrada sombra: {nom[t][0]} {t} {out[-1]['motivo']}")
    return out


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
    try:
        e1, e2 = h31(ahora, hora)
        guardar("datos/h31_sombra.tsv", e1); guardar("datos/h31p_sombra.tsv", e2)
        print(f"H31: {len(e1)} entradas nuevas (pozo + chispa); H31p: {len(e2)} (pozo quieto)")
    except Exception as e:
        print("h31 falló:", e)
    try:
        g = h31s(ahora, hora)
        guardar("datos/h31s_sombra.tsv", g)
        print(f"H31s: {len(g)} entradas nuevas (pozo + chispa sin A)")
    except Exception as e:
        print("h31s falló:", e)
    try:
        if os.environ.get("OBS_LIVIANO", "1") == "1":
            raise RuntimeError("apagado 22-nov (observatorio liviano)")
        g = h32(ahora, hora, getattr(h31, "sost", {}))
        guardar("datos/h32_sombra.tsv", g)
        print(f"H32: {len(g)} entradas nuevas (tema que despierta)")
    except Exception as e:
        print("h32 falló:", e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("h25/h26 falló (no afecta el escaneo):", e)
