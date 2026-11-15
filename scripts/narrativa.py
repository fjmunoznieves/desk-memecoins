"""Radar de narrativas (v15): H17, H18 y H19. Paper trading, solo lectura.

H17 · temas calientes de fuentes gratis y sin clave:
      Wikipedia pageviews (lo más visto ayer vs anteayer), GDELT DOC (titulares de las últimas 6 h)
      y Google Trends (RSS público, solo intento: si falla se salta).
      Reddit solo si existen los secretos REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET.
      Para cada tema, búsqueda en DexScreener: ¿ya tiene token en Solana, BNB o Robinhood?
H18 · cruce con el trending 5m/1h/24h del escaneo (rows.json). Solo avisa si coinciden 2 fuentes
      (una narrativa + el trending, o dos narrativas) y el token pasa liquidez ≥ 30k y seguridad.
H19 · temas calientes sin token evidente → "idea paper". Nunca se crea nada.

Nunca debe tumbar el escaneo: todo error se registra y el script sale con 0.
"""
import collections, csv, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "desk-narrativas/1.0 (paper trading, solo lectura)", "Accept": "application/json"}
CADENAS = {"solana": "Solana", "bsc": "BNB", "robinhood": "Robinhood"}
LIQ_TOKEN = 1000      # mínimo para decir "ya tiene token"
LIQ_AVISO = 30000     # mínimo para abrir aviso en H18
MAX_TEMAS = 25        # búsquedas en DexScreener por corrida
SALIDA = "datos"
log = lambda *a: print(*a, file=sys.stderr)


def get(url, tipo="json", intentos=2):
    """Un 404 no se reintenta."""
    for k in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                data = r.read()
            return json.loads(data) if tipo == "json" else data
        except Exception as e:
            log("fallo", url[:90], getattr(e, "code", e))
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(3 + 3 * k)
    return None


# Palabras que no sirven como tema (muy comunes o de relleno)
STOP = set("""the a an of and or in on at to for with from by is are was were be as it its this that these those
new news live update updates video photos watch says said after over into about vs v amid more most how why what who when
de la el los las y en del por con para un una es al se que lo su sus como más
2025 2026 2027 list deaths people film season episode game games series""".split())
EVERGREEN = {"main page", "google", "youtube", "facebook", "wikipedia", "chatgpt", "instagram", "xxx", "pornhub",
             "cleopatra", "deaths in 2026", "bible", "donald trump", "united states", "india", "elon musk", "taylor swift"}
NO_WIKI = re.compile(r"^(Special|Wikipedia|File|Portal|Help|Category|Template|Talk|User)[:]|_\(disambiguation\)$|^Main_Page$|^-$")


def wikipedia():
    """Artículos que suben fuerte en en.wikipedia: top de ayer comparado con anteayer."""
    def top(dias):
        t = time.gmtime(time.time() - dias * 86400)
        d = get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{t.tm_year}/{t.tm_mon:02d}/{t.tm_mday:02d}")
        try:
            return {a["article"]: a["views"] for a in d["items"][0]["articles"] if not NO_WIKI.search(a["article"])}
        except Exception:
            return {}
    ayer, antes = top(1), top(2)
    if not ayer:  # Wikimedia publica el día anterior unas horas después de medianoche UTC
        ayer, antes = antes, top(3)
    out = []
    for i, (art, v) in enumerate(list(ayer.items())[:200]):
        nombre = art.replace("_", " ")
        if nombre.lower() in EVERGREEN:
            continue
        prev = antes.get(art, 0)
        salto = v / prev if prev else 10.0
        if salto >= 2 and v >= 100000:
            out.append({"tema": nombre, "fuente": "wikipedia", "calor": round(min(100, 40 + 10 * min(salto, 6))),
                        "porque": f"{v:,} visitas ayer en Wikipedia" + (f", {salto:.1f}× anteayer" if prev else ", nuevo en el top")})
    log("wikipedia", len(ayer), "artículos,", len(out), "que suben")
    return out[:15]


def _ngrams(titulo):
    pal = re.findall(r"[A-Za-zÀ-ÿ0-9$']+", titulo)
    caps = []
    for w in pal:
        if w[:1].isupper() and w.lower() not in STOP and len(w) > 2:
            caps.append(w)
        else:
            if caps:
                yield " ".join(caps[:3])
            caps = []
    if caps:
        yield " ".join(caps[:3])


def gdelt():
    """Titulares en inglés de las últimas 6 h; temas = nombres propios que más se repiten entre medios distintos."""
    q = urllib.parse.quote("sourcelang:english")
    d = get(f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist&maxrecords=250&timespan=6h&format=json&sort=hybridrel")
    arts = (d or {}).get("articles") or []
    cuenta, medios = collections.Counter(), collections.defaultdict(set)
    for a in arts:
        vistos = set()
        for g in _ngrams(a.get("title", "")):
            if g.lower() in vistos or g.lower() in EVERGREEN:
                continue
            vistos.add(g.lower())
            cuenta[g] += 1
            medios[g].add(a.get("domain", ""))
    out = []
    for g, n in cuenta.most_common(40):
        m = len(medios[g])
        if (" " in g and m >= 4) or m >= 8:
            out.append({"tema": g, "fuente": "gdelt", "calor": min(100, 30 + 8 * m),
                        "porque": f"en {n} titulares de {m} medios distintos en 6 h (GDELT)"})
    log("gdelt", len(arts), "artículos,", len(out), "temas")
    return out[:15]


def trends():
    """Google Trends, solo intento: RSS público de búsquedas en tendencia (EE. UU.). Si falla, lista vacía."""
    try:
        raw = get("https://trends.google.com/trending/rss?geo=US", tipo="raw", intentos=1)
        if not raw:
            return []
        ns = {"ht": "https://trends.google.com/trending/rss"}
        out = []
        for it in ET.fromstring(raw).iter("item"):
            t = (it.findtext("title") or "").strip()
            trafico = it.findtext("ht:approx_traffic", default="", namespaces=ns)
            if t and t.lower() not in EVERGREEN:
                out.append({"tema": t, "fuente": "trends", "calor": 60, "porque": f"búsqueda en tendencia en Google ({trafico or 's/d'})"})
        log("trends", len(out), "temas")
        return out[:15]
    except Exception as e:
        log("trends saltado:", e)
        return []


def reddit():
    """Reddit (solo si existen REDDIT_CLIENT_ID y REDDIT_CLIENT_SECRET en los secretos de GitHub; si no, se salta).
    Lectura de los posts más votados de las últimas horas en comunidades de memes, cripto y noticias."""
    cid, sec = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not sec:
        log("reddit saltado: sin secretos")
        return []
    import base64
    try:
        req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=b"grant_type=client_credentials",
                                     headers={"User-Agent": UA["User-Agent"],
                                              "Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()})
        with urllib.request.urlopen(req, timeout=25) as r:
            tok = json.load(r)["access_token"]
    except Exception as e:
        log("reddit sin token:", getattr(e, "code", e))
        return []
    hdr = {"User-Agent": UA["User-Agent"], "Authorization": "bearer " + tok}
    cuenta, subs = collections.Counter(), collections.defaultdict(set)
    for sub in ("memes", "CryptoCurrency", "SatoshiStreetBets", "solana", "worldnews", "news", "popular"):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"https://oauth.reddit.com/r/{sub}/top?t=day&limit=50", headers=hdr), timeout=25) as r:
                posts = json.load(r)["data"]["children"]
        except Exception as e:
            log("reddit", sub, getattr(e, "code", e))
            continue
        for p in posts:
            for g in set(_ngrams(p["data"].get("title", ""))):
                if g.lower() not in EVERGREEN:
                    cuenta[g] += 1
                    subs[g].add(sub)
        time.sleep(1)
    out = []
    for g, n in cuenta.most_common(40):
        if (" " in g and n >= 2) or len(subs[g]) >= 3:
            out.append({"tema": g, "fuente": "reddit", "calor": min(100, 35 + 10 * len(subs[g]) + 3 * n),
                        "porque": f"en {n} posts top de Reddit ({', '.join(sorted(subs[g]))})"})
    log("reddit", len(out), "temas")
    return out[:15]


def clave(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def palabras(t):
    return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 2]


def coincide(tema, sym, name):
    """Coincidencia estricta (evita falsos positivos): el símbolo es igual a una palabra distintiva del tema,
    o el nombre del token contiene el tema completo."""
    s, n, k = clave(sym), clave(name), clave(tema)
    if not s or len(s) > 15:
        return False
    if len(k) >= 4 and (s == k or n == k or (len(k) >= 6 and k in n)):
        return True
    ws = [w for w in palabras(tema) if len(w) >= 5]
    return len(palabras(tema)) <= 2 and any(w == s for w in ws)


def buscar_token(tema):
    d = get("https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(tema), intentos=1) or {}
    mejor = None
    for p in d.get("pairs") or []:
        if p.get("chainId") not in CADENAS:
            continue
        bt = p.get("baseToken") or {}
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if liq < LIQ_TOKEN or not coincide(tema, bt.get("symbol", ""), bt.get("name", "")):
            continue
        if not mejor or liq > mejor["liq"]:
            mejor = {"cadena": p["chainId"], "token": bt.get("address"), "sym": bt.get("symbol"), "liq": round(liq),
                     "vol24": round((p.get("volume") or {}).get("h24") or 0), "c24": (p.get("priceChange") or {}).get("h24") or 0,
                     "edad_h": round((time.time() * 1000 - p["pairCreatedAt"]) / 3.6e6, 1) if p.get("pairCreatedAt") else None}
    return mejor


def agrupar(temas):
    """Une el mismo tema visto en varias fuentes."""
    g = collections.OrderedDict()
    for t in temas:
        k = clave(t["tema"])
        if not k:
            continue
        hit = next((x for x in g if k == x or (len(k) >= 5 and (k in x or x in k))), None)
        if hit is None:
            g[k] = {"tema": t["tema"], "fuentes": [t["fuente"]], "calor": t["calor"], "porque": [t["porque"]]}
        else:
            e = g[hit]
            if t["fuente"] not in e["fuentes"]:
                e["fuentes"].append(t["fuente"])
                e["porque"].append(t["porque"])
            e["calor"] = min(100, max(e["calor"], t["calor"]) + 10)
    return sorted(g.values(), key=lambda e: (len(e["fuentes"]), e["calor"]), reverse=True)


def anexar(nombre, filas, campos):
    ruta = os.path.join(SALIDA, nombre)
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", newline="") as f:
        w = csv.DictWriter(f, campos, delimiter="\t", extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerows(filas)


def recientes_h18(horas=24):
    ruta = os.path.join(SALIDA, "h18_cruces.tsv")
    if not os.path.exists(ruta):
        return set()
    lim = time.time() - horas * 3600
    with open(ruta) as f:
        return {(r["cadena"], r["token"]) for r in csv.DictReader(f, delimiter="\t") if r.get("aviso") == "si" and float(r["ts"]) > lim}


def main():
    ahora = int(time.time())
    hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora))
    temas = []
    for f in (wikipedia, gdelt, trends, reddit):
        try:
            temas += f()
        except Exception as e:
            log(f.__name__, "falló:", e)
        time.sleep(1)
    grupos = agrupar(temas)[:MAX_TEMAS]

    # H17: ¿el tema ya tiene token?
    for e in grupos:
        e["token"] = buscar_token(e["tema"])
        time.sleep(0.4)

    # H18: cruce con el trending del escaneo
    try:
        filas = json.load(open("rows.json"))
    except Exception:
        filas = []
    trending = [r for r in filas if r.get("trending")]
    ya = recientes_h18()
    cruces = []
    for e in grupos:
        for r in trending:
            if not coincide(e["tema"], r.get("sym", ""), r.get("name", "")):
                continue
            fuentes = e["fuentes"] + ["trending " + (r.get("src_dur") or "")]
            c = {"ts": ahora, "hora_utc": hora, "tema": e["tema"], "fuentes": ",".join(fuentes), "cadena": r["chain"], "token": r["addr"],
                 "sym": r["sym"], "liq": round(r.get("liq") or 0), "mc": round(r.get("mc") or 0), "c1": r.get("c1"), "seguridad": "", "aviso": "no"}
            if len(fuentes) >= 2 and c["liq"] >= LIQ_AVISO and (r["chain"], r["addr"]) not in ya:
                try:
                    sys.path.insert(0, os.path.dirname(__file__))
                    from seguridad import revisar
                    fallos = revisar(r["chain"], r["addr"])[0]
                except Exception as ex:
                    fallos = [f"seg? {ex}"]
                c["seguridad"] = "ok" if not fallos else ",".join(fallos)
                if not fallos and os.environ.get("GH_TOKEN"):
                    cad = CADENAS.get(r["chain"], r["chain"])
                    cuerpo = "\n".join([
                        "Paper trading, H18 (radar de narrativas): solo aviso, no es orden de compra.", "",
                        f"- Tema: {e['tema']} ({'; '.join(e['porque'])})",
                        f"- Token: {r['sym']} en {cad}", f"- Contrato: `{r['addr']}`",
                        f"- DexScreener: https://dexscreener.com/{r['chain']}/{r['addr']}",
                        f"- Fuentes que coinciden: {', '.join(fuentes)}",
                        f"- Liquidez: {c['liq']:,} USD | MC: {c['mc']:,} USD | Precio 1 h: {r.get('c1')}%",
                        "", "Una narrativa caliente no es señal de entrada: aplica filtros 5.x y 2 de 3 señales."])
                    res = subprocess.run(["gh", "issue", "create", "--title", f"H18 narrativa: {e['tema']} → {r['sym']} ({cad})", "--body", cuerpo])
                    c["aviso"] = "si" if res.returncode == 0 else "error"
            cruces.append(c)

    # H19: huecos narrativa → token (temas calientes sin token evidente)
    huecos = [{"ts": ahora, "hora_utc": hora, "tema": e["tema"], "fuentes": ",".join(e["fuentes"]), "calor": e["calor"],
               "porque": " | ".join(e["porque"]), "idea": "idea paper (no se crea nada)"}
              for e in grupos if not e["token"] and (len(e["fuentes"]) >= 2 or e["calor"] >= 70)]

    os.makedirs(SALIDA, exist_ok=True)
    json.dump({"hora_utc": hora, "fuentes_ok": sorted({t["fuente"] for t in temas}),
               "narrativas": grupos, "cruces_h18": cruces, "huecos_h19": huecos},
              open(os.path.join(SALIDA, "narrativas.json"), "w"), ensure_ascii=False, indent=1)
    anexar("h17_narrativas.tsv", [{"ts": ahora, "hora_utc": hora, "tema": e["tema"], "fuentes": ",".join(e["fuentes"]), "calor": e["calor"],
                                    "porque": " | ".join(e["porque"]), "tiene_token": "si" if e["token"] else "no",
                                    **({k: e["token"][k] for k in ("cadena", "token", "sym", "liq")} if e["token"] else {})} for e in grupos],
           ["ts", "hora_utc", "tema", "fuentes", "calor", "porque", "tiene_token", "cadena", "token", "sym", "liq"])
    anexar("h18_cruces.tsv", cruces, ["ts", "hora_utc", "tema", "fuentes", "cadena", "token", "sym", "liq", "mc", "c1", "seguridad", "aviso"])
    anexar("h19_huecos.tsv", huecos, ["ts", "hora_utc", "tema", "fuentes", "calor", "porque", "idea"])
    print(f"H17 temas {len(grupos)} (fuentes: {', '.join(sorted({t['fuente'] for t in temas})) or 'ninguna'}) | "
          f"con token {sum(1 for e in grupos if e['token'])} | H18 cruces {len(cruces)} avisos {sum(1 for c in cruces if c['aviso'] == 'si')} | H19 huecos {len(huecos)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("radar de narrativas falló, el escaneo sigue:", e)
    sys.exit(0)
