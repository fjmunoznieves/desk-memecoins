"""Liquidez de los tokens en seguimiento (17-nov, pedido por Fran). Solo registro, DexScreener gratis, sin Helius.
En cada escaneo y reloj guarda liquidez, MC, volumen y su relación, para estudiar en la revisión del 20:
liquidez al detectar, si la liquidez se drena (señal de salida) y qué rangos de liquidez/MC funcionan."""
import csv, json, os, time, urllib.request
SEG, OUT = "datos/seguimiento.tsv", "datos/liquidez_seguimiento.tsv"
CAMPOS = ["ts", "hora_utc", "token", "sym", "liq", "mc", "liq_mc_pct", "vol5m", "vol1h", "vol24h", "precio", "pool"]


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
    nuevo = not os.path.exists(OUT)
    with open(OUT, "a", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t")
        if nuevo: w.writeheader()
        w.writerows(filas)
    print(f"liquidez: {len(filas)} tokens registrados")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("liquidez falló (no afecta el escaneo):", e)
