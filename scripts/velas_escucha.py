"""Respaldo de la escucha con velas de 1 minuto (25-nov, Fran OK "1 y 2 gratis"). SOLO LECTURA, paper.

El websocket público a veces corta y la escucha pierde el precio de los tokens que sigue. Al terminar cada corrida,
este script baja de GeckoTerminal (gratis, sin clave) las velas de 1 minuto de los tokens que alguna A compró en las
últimas VENTANA_H horas, para no perder el recorrido aunque el websocket haya estado caído.
Salida: datos/escucha/velas_AAAAMMDD.tsv (clave, dex, pool, ts, o, h, l, c, vol_usd), sin duplicados.
"""
import csv, glob, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from sombra import get

VENTANA_H = float(os.environ.get("VELAS_VENTANA_H", "6.5"))
MAX_TOKENS = int(os.environ.get("VELAS_MAX_TOKENS", "250"))
PRESUPUESTO_S = int(os.environ.get("VELAS_PRESUPUESTO_S", "1500"))
GT = "https://api.geckoterminal.com/api/v2/networks/solana"
CAMPOS = ["clave", "dex", "pool", "ts", "o", "h", "l", "c", "vol_usd"]
# 26-nov (Fran): datos para estudio creador / curva / reparto. Una fila por token pump.fun (RugCheck + pools de GT).
META = "datos/escucha/meta_tokens.tsv"
CAMPOS_META = ["clave", "consulta_ts", "creador", "n_tokens_creador", "tokens_creador", "insiders_grafo", "redes_insiders",
               "top10_pct", "holders", "rugged", "detectado", "score", "pools"]


def meta_token(mint, pools_gt):
    rc = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report") or {}
    top = rc.get("topHolders") or []
    ct = rc.get("creatorTokens") or []
    redes = rc.get("insiderNetworks") or []
    return [mint, int(time.time()), rc.get("creator") or "", len(ct),
            ",".join(f"{t.get('mint','')}:{t.get('marketCap', '')}:{t.get('createdAt', '')}" for t in ct[:20]),
            rc.get("graphInsidersDetected", ""), ";".join(f"{n.get('type','')}:{n.get('size','')}:{n.get('tokenAmount','')}" for n in redes[:5]),
            round(sum(float(h.get("pct") or 0) for h in top[:10]), 2), rc.get("totalHolders", ""), rc.get("rugged", ""),
            rc.get("detectedAt", ""), rc.get("score_normalised", ""),
            ";".join(f"{(x.get('relationships') or {}).get('dex', {}).get('data', {}).get('id', '')}|{x['attributes'].get('address')}|{x['attributes'].get('pool_created_at')}" for x in pools_gt[:5])]


def tokens_recientes(desde):
    vistos = {}
    for f in sorted(glob.glob("datos/escucha/ev_*.tsv"))[-4:]:  # 26-nov: incluye turno b (ev_*_b.tsv)
        for r in csv.DictReader(open(f), delimiter="\t"):
            if r.get("tipo") not in ("A_compra", "O_compra"):
                continue
            try:
                t = float(r["recv_ts"])
            except (TypeError, ValueError):
                continue
            if t >= desde:
                k = r["clave"]
                if k not in vistos or t < vistos[k][0]:
                    vistos[k] = (t, r.get("dex", ""))
    return sorted(vistos.items(), key=lambda x: x[1][0])


def main():
    t_ini = time.time()
    ahora = int(t_ini)
    lista = tokens_recientes(ahora - VENTANA_H * 3600)[:MAX_TOKENS]
    dia = time.strftime("%Y%m%d", time.gmtime())
    ruta = f"datos/escucha/velas_{dia}.tsv"
    ya = set()
    if os.path.exists(ruta):
        for r in csv.DictReader(open(ruta), delimiter="\t"):
            ya.add((r["clave"], r["ts"]))
    nuevo = not os.path.exists(ruta)
    n_ok = n_sin = n_filas = n_meta = 0
    hechos = set()
    if os.path.exists(META):
        hechos = {r["clave"] for r in csv.DictReader(open(META), delimiter="\t")}
    fm = open(META, "a", newline=""); wm = csv.writer(fm, delimiter="\t")
    if not hechos and os.path.getsize(META) == 0:
        wm.writerow(CAMPOS_META)
    with open(ruta, "a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        if nuevo:
            w.writerow(CAMPOS)
        for clave, (t0, dex) in lista:
            if time.time() - t_ini > PRESUPUESTO_S:
                print(f"velas: presupuesto de {PRESUPUESTO_S} s agotado"); break
            pool = clave
            if dex == "pf":   # pump.fun: la clave es el mint; buscar su pool en GeckoTerminal
                d = get(f"{GT}/tokens/{clave}/pools?page=1") or {}
                time.sleep(2.1)
                pools = d.get("data") or []
                if not pools:
                    n_sin += 1; continue
                pool = pools[0]["attributes"]["address"]
                if clave not in hechos:
                    try:
                        wm.writerow(meta_token(clave, pools)); hechos.add(clave); n_meta += 1
                    except Exception as ex:
                        print("meta falló", clave[:8], str(ex)[:80])
                    time.sleep(1.1)
            d = get(f"{GT}/pools/{pool}/ohlcv/minute?aggregate=1&limit=1000&currency=usd&before_timestamp={ahora}") or {}
            time.sleep(2.1)
            try:
                velas = d["data"]["attributes"]["ohlcv_list"]
            except (KeyError, TypeError):
                n_sin += 1; continue
            n_ok += 1
            for ts, o, h, l, c, v in sorted(velas):
                if ts < t0 - 600 or (clave, str(ts)) in ya:
                    continue
                ya.add((clave, str(ts)))
                w.writerow([clave, dex, pool, ts, o, h, l, c, round(v, 2)]); n_filas += 1
    fm.close()
    print(f"velas: meta (creador/insiders/pools) de {n_meta} tokens nuevos → {META}")
    print(f"velas: {len(lista)} tokens con compra A en {VENTANA_H} h, {n_ok} con velas, {n_sin} sin pool/velas, {n_filas} filas nuevas → {ruta}")


if __name__ == "__main__":
    main()
