"""Liquidez de los tokens en seguimiento (17-nov, pedido por Fran). Solo registro, DexScreener gratis, sin Helius.
En cada escaneo y reloj guarda liquidez, MC, volumen y su relación, para estudiar en la revisión del 20:
liquidez al detectar, si la liquidez se drena (señal de salida) y qué rangos de liquidez/MC funcionan."""
import csv, json, os, time, urllib.request
SEG, OUT = "datos/seguimiento.tsv", "datos/liquidez_seguimiento.tsv"
CAMPOS = ["ts", "hora_utc", "token", "sym", "liq", "mc", "liq_mc_pct", "vol5m", "vol1h", "vol24h", "precio", "pool", "holders", "mc_por_holder"]


def main():
    if not os.path.exists(SEG):
        return
    seg = {r["token"]: r["sym"] for r in csv.DictReader(open(SEG), delimiter="\t")}
    for f in ("datos/alertas_sostenidas.tsv",):  # también las sostenidas de los últimos 3 días
        if os.path.exists(f):
            for r in csv.DictReader(open(f), delimiter="\t"):
                if time.time() - int(r["ts"]) < 3 * 86400:
                    seg.setdefault(r["token"], r["sym"])
    toks, filas, ahora = list(seg), [], int(time.time())
    for i in range(0, len(toks), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(toks[i:i + 30]), headers={"User-Agent": "desk-liquidez"})
            mejor = {}
            for p in json.load(urllib.request.urlopen(req, timeout=25)):
                a = p["baseToken"]["address"]
                if a not in mejor or ((p.get("liquidity") or {}).get("usd") or 0) > ((mejor[a].get("liquidity") or {}).get("usd") or 0):
                    mejor[a] = p
        except Exception as e:
            print("liquidez: dexscreener falló", str(e)[:60]); continue
        for a, p in mejor.items():
            liq = (p.get("liquidity") or {}).get("usd") or 0
            mc = p.get("marketCap") or p.get("fdv") or 0
            v = p.get("volume") or {}
            filas.append(dict(ts=ahora, hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora)), token=a, sym=seg.get(a, ""),
                              liq=round(liq), mc=round(mc), liq_mc_pct=round(100 * liq / mc, 1) if mc else "",
                              vol5m=v.get("m5"), vol1h=v.get("h1"), vol24h=v.get("h24"), precio=p.get("priceUsd"), pool=p.get("pairAddress")))
        time.sleep(0.3)
    # 17-nov (Fran): cantidad de holders y MC por holder (¿los holders dan soporte al precio?). RugCheck gratis, solo registro.
    t0 = time.time()
    for r in filas:
        if time.time() - t0 > 120:
            break
        try:
            req = urllib.request.Request(f"https://api.rugcheck.xyz/v1/tokens/{r['token']}/report", headers={"User-Agent": "desk-liquidez"})
            h = json.load(urllib.request.urlopen(req, timeout=20)).get("totalHolders")
            if h:
                r["holders"] = h
                r["mc_por_holder"] = round(r["mc"] / h, 1) if r["mc"] else ""
        except Exception:
            pass
        time.sleep(0.5)
    # si el archivo tiene el encabezado viejo, se reescribe con las columnas nuevas
    if os.path.exists(OUT):
        with open(OUT) as fh:
            cab = fh.readline().rstrip("\n").split("\t")
        if cab != CAMPOS:
            viejas = list(csv.DictReader(open(OUT), delimiter="\t"))
            with open(OUT, "w", newline="") as fh:
                w = csv.DictWriter(fh, CAMPOS, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(viejas)
    nuevo = not os.path.exists(OUT)
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t")
        if nuevo: w.writeheader()
        w.writerows(filas)
    print(f"liquidez: {len(filas)} tokens registrados, {sum(1 for r in filas if r.get('holders'))} con holders")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("liquidez falló (no afecta el escaneo):", e)
