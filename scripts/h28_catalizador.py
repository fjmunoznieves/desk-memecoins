"""H28 "catalizador" en sombra (17-nov, aprobado por Fran tras KATIA y GEKKO). Solo registro, no cambia reglas.
Patrón visto: catalizador en X (tweet de cuenta enorme o noticia grande) → token creado a minutos → perfil pagado en
DexScreener que enlaza el tweet → pico en 1–3 h y caída −50 %. Se mide si "cuenta enorme + perfil pagado" predice subida.
Fuentes gratis: DexScreener (token-profiles/latest, orders, tokens) y api.fxtwitter.com para leer el tweet enlazado.
Universo: perfiles recientes de DexScreener + tokens de la sección H2 y candidatos del último escaneo; solo < 48 h.
Salida: datos/h28_sombra.tsv (salidas.py la mide con los mismos métodos de salida)."""
import csv, glob, json, os, re, time, urllib.request

OUT = "datos/h28_sombra.tsv"
CAMPOS = ["ts", "hora_utc", "cadena", "token", "sym", "precio", "liq", "mc", "liq_mc_pct", "edad_h", "vol1h", "c1h", "c6h",
          "perfil_pagado_utc", "min_perfil_a_deteccion", "tweet_autor", "seguidores", "vistas", "tweet_utc", "min_tweet_a_deteccion",
          "cita_autor", "cita_seguidores", "clase", "texto", "origen", "pool"]
UA = {"User-Agent": "desk-h28"}
CADENAS = {"solana": "solana", "bsc": "bsc"}


def get(url, timeout=20):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))


def universo():
    toks = {}
    try:
        for p in get("https://api.dexscreener.com/token-profiles/latest/v1"):
            if p.get("chainId") in CADENAS:
                toks[(p["chainId"], p["tokenAddress"])] = "perfil reciente"
    except Exception as e:
        print("h28: perfiles falló", str(e)[:80])
    esc = sorted(glob.glob("escaneos/escaneo_*.md"))
    if esc and time.time() - os.path.getmtime(esc[-1]) < 3 * 3600:
        txt = open(esc[-1]).read()
        for sec in re.split(r"\n## ", txt):
            if sec.startswith("Candidatos") or sec.startswith("H2"):
                for m in re.finditer(r"\((solana|bsc)\) `([^`]+)`", sec):
                    toks.setdefault((m.group(1), m.group(2)), "escaneo " + sec.split(":")[0][:12])
    return toks


def tweet(url):
    m = re.search(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)", url or "")
    if not m:
        return None
    try:
        t = get(f"https://api.fxtwitter.com/{m.group(1)}/status/{m.group(2)}")["tweet"]
    except Exception as e:
        print("h28: fxtwitter falló", str(e)[:60])
        ts = ((int(m.group(2)) >> 22) + 1288834974657) / 1000  # la hora sale del id aunque no se pueda leer
        return dict(autor=m.group(1), seguidores="", vistas="", ts=ts, texto="", cita_autor="", cita_seg="")
    q = t.get("quote") or {}
    return dict(autor=t["author"]["screen_name"], seguidores=t["author"].get("followers", ""), vistas=t.get("views", ""),
                ts=t.get("created_timestamp"), texto=(t.get("text") or "")[:160].replace("\t", " ").replace("\n", " "),
                cita_autor=(q.get("author") or {}).get("screen_name", ""), cita_seg=(q.get("author") or {}).get("followers", ""))


def main():
    hechos = set()
    if os.path.exists(OUT):
        hechos = {(r["cadena"], r["token"]) for r in csv.DictReader(open(OUT), delimiter="\t")}
    toks = {k: v for k, v in universo().items() if k not in hechos}
    ahora, filas = time.time(), []
    for cad in CADENAS:
        lista = [t for (c, t) in toks if c == cad]
        for i in range(0, len(lista), 30):
            try:
                pares = get(f"https://api.dexscreener.com/tokens/v1/{cad}/" + ",".join(lista[i:i + 30]))
            except Exception as e:
                print("h28: dexscreener falló", str(e)[:60]); continue
            mejor = {}
            for p in pares:
                a = p["baseToken"]["address"]
                if a not in mejor or ((p.get("liquidity") or {}).get("usd") or 0) > ((mejor[a].get("liquidity") or {}).get("usd") or 0):
                    mejor[a] = p
            for a, p in mejor.items():
                edad = (ahora * 1000 - (p.get("pairCreatedAt") or 0)) / 3.6e6
                liq = (p.get("liquidity") or {}).get("usd") or 0
                mc = p.get("marketCap") or p.get("fdv") or 0
                if edad > 48 or liq < 5000:
                    continue
                socials = (p.get("info") or {}).get("socials") or []
                tw = next((s.get("url") for s in socials if "/status/" in (s.get("url") or "")), None)
                pago = None
                try:
                    o = get(f"https://api.dexscreener.com/orders/v1/{cad}/{a}")
                    o = o.get("orders", o) if isinstance(o, dict) else o
                    pt = [x.get("paymentTimestamp") for x in o if x.get("type") == "tokenProfile" and x.get("paymentTimestamp")]
                    pago = min(pt) / 1000 if pt else None
                except Exception:
                    pass
                t = tweet(tw) if tw else None
                seg = (t or {}).get("seguidores") or 0
                vis = (t or {}).get("vistas") or 0
                cseg = (t or {}).get("cita_seg") or 0
                clase = ("cuenta enorme" if max(seg, cseg) >= 1_000_000 or vis >= 1_000_000 else
                         "cuenta media" if max(seg, cseg) >= 50_000 or vis >= 100_000 else
                         "tweet sin leer" if t and t.get("seguidores") == "" else
                         "cuenta pequeña" if t else "sin tweet")
                ch = p.get("priceChange") or {}
                filas.append(dict(ts=int(ahora), hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), cadena=cad, token=a,
                                  sym=p["baseToken"].get("symbol", ""), precio=p.get("priceUsd"), liq=round(liq), mc=round(mc),
                                  liq_mc_pct=round(100 * liq / mc, 1) if mc else "", edad_h=round(edad, 1), vol1h=(p.get("volume") or {}).get("h1"),
                                  c1h=ch.get("h1"), c6h=ch.get("h6"),
                                  perfil_pagado_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(pago)) if pago else "",
                                  min_perfil_a_deteccion=round((ahora - pago) / 60) if pago else "",
                                  tweet_autor=(t or {}).get("autor", ""), seguidores=seg or "", vistas=vis or "",
                                  tweet_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(t["ts"])) if t and t.get("ts") else "",
                                  min_tweet_a_deteccion=round((ahora - t["ts"]) / 60) if t and t.get("ts") else "",
                                  cita_autor=(t or {}).get("cita_autor", ""), cita_seguidores=cseg or "", clase=clase,
                                  texto=(t or {}).get("texto", ""), origen=toks[(cad, a)], pool=p.get("pairAddress", "")))
                time.sleep(0.3)
    nuevo = not os.path.exists(OUT)
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t")
        if nuevo:
            w.writeheader()
        w.writerows(filas)
    print(f"h28: {len(filas)} tokens nuevos registrados ({sum(r['clase'] == 'cuenta enorme' for r in filas)} con cuenta enorme)")
    if os.environ.get("GITHUB_ACTIONS"):
        import subprocess
        subprocess.run(["git", "add", OUT], check=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("h28 falló (no afecta el escaneo):", e)
