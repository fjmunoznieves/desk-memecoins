"""Tabla del proceso de nuestras A por token (17-nov, pedido de Fran): tokens donde entraron 2+ operadores A (≥0,5 SOL cada uno)
o donde una A aún tiene saldo, con más de 7 días. Historia = vector_ops_A_289 + vector_profundo SUMADOS por billetera×token
(ojo: la historia de las A cubre ~60 días y hay billeteras cortadas). Estado actual: foto de cartera (consenso_A_estado.json)
y DexScreener. Salida: datos/tabla_A.json. Sin Helius."""
import csv, json, os, sys, time, urllib.request
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from operadores import mapa


def main():
    m = mapa()
    A = {r["billetera"] for r in csv.DictReader(open("datos/operadores.tsv"), delimiter="\t") if r["grupo"] == "A" and r["bot"] != "si"}
    elite = {r["operador"] for r in csv.DictReader(open("datos/elite.tsv"), delimiter="\t")}
    agg = defaultdict(lambda: [0.0, 0.0, 0, 0, None, None])
    for fn in ("datos/vector_ops_A_289.tsv", "datos/vector_profundo.tsv"):
        for r in csv.DictReader(open(fn), delimiter="\t"):
            if r["billetera"] not in A:
                continue
            a = agg[(r["billetera"], r["token"])]
            a[0] += float(r["sol_in"] or 0); a[1] += float(r["sol_out"] or 0)
            a[2] += int(float(r["compras"] or 0)); a[3] += int(float(r["ventas"] or 0))
            pc, ul = float(r["primera_compra"] or 0), float(r["ultima"] or 0)
            if pc: a[4] = min(a[4] or pc, pc)
            if ul: a[5] = max(a[5] or 0, ul)
    cart = json.load(open("datos/consenso_A_estado.json")).get("cartera", {})
    tok = defaultdict(lambda: dict(ops=set(), si=0.0, so=0.0, c=0, v=0, pc=None, ul=None, wal={}))
    for (b, t), a in agg.items():
        op = m.get(b, (b[:6], False))[0]
        T = tok[t]
        if a[0] >= 0.5:
            T["ops"].add(op)
        T["si"] += a[0]; T["so"] += a[1]; T["c"] += a[2]; T["v"] += a[3]
        if a[4]: T["pc"] = min(T["pc"] or a[4], a[4])
        if a[5]: T["ul"] = max(T["ul"] or 0, a[5])
        T["wal"][b] = (op, round(a[0], 2), round(a[1], 2))
    # saldo actual (cantidad) por token desde la foto de cartera
    held = defaultdict(dict)
    for b, mints in cart.items():
        if b in A:
            for k, q in mints.items():
                if q and q > 0:
                    held[k][b] = q
    sel = [t for t, T in tok.items() if len(T["ops"]) >= 2 or (t[:12] in held and T["si"] >= 0.5)]
    print("tokens seleccionados", len(sel))
    ds = {}
    for i in range(0, len(sel), 30):
        for intento in range(3):
            try:
                req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(sel[i:i + 30]), headers={"User-Agent": "desk-tabla"})
                for p in json.load(urllib.request.urlopen(req, timeout=25)):
                    a = p["baseToken"]["address"]
                    if a not in ds or ((p.get("liquidity") or {}).get("usd") or 0) > ((ds[a].get("liquidity") or {}).get("usd") or 0):
                        ds[a] = p
                break
            except Exception as e:
                time.sleep(3 + 3 * intento)
        time.sleep(0.22)
    ahora = time.time(); filas = []
    for t in sel:
        T, p = tok[t], ds.get(t)
        precio = float(p["priceUsd"]) if p and p.get("priceUsd") else 0
        liq = ((p or {}).get("liquidity") or {}).get("usd") or 0
        mc = (p or {}).get("marketCap") or (p or {}).get("fdv") or 0
        creado = (p or {}).get("pairCreatedAt")
        edad = (ahora - creado / 1000) / 86400 if creado else ((ahora - T["pc"]) / 86400 if T["pc"] else None)
        if edad is None or edad < 7:
            continue
        dentro = {}
        for b, q in held.get(t[:12], {}).items():
            usd = q * precio
            if usd >= 20:
                op = m.get(b, (b[:6], False))[0]
                dentro[op] = dentro.get(op, 0) + usd
        ops = sorted(T["ops"])
        filas.append(dict(
            token=t, sym=(p or {}).get("baseToken", {}).get("symbol") or t[:6], edad_d=round(edad, 1),
            primera_A=time.strftime("%Y-%m-%d", time.gmtime(T["pc"])) if T["pc"] else "",
            ultima_A=time.strftime("%Y-%m-%d", time.gmtime(T["ul"])) if T["ul"] else "",
            dias_A=round((T["ul"] - T["pc"]) / 86400, 1) if T["pc"] and T["ul"] else None,
            n_oper=len(ops), n_elite=sum(o in elite for o in ops), operadores=",".join(ops[:12]),
            sol_in=round(T["si"], 2), sol_out=round(T["so"], 2), pnl_sol=round(T["so"] - T["si"], 2),
            mult=round(T["so"] / T["si"], 2) if T["si"] else None, compras=T["c"], ventas=T["v"],
            oper_dentro=len(dentro), elite_dentro=sum(o in elite for o in dentro), usd_dentro=round(sum(dentro.values())),
            precio=precio or None, mc=round(mc) or None, liq=round(liq) or None,
            liq_mc=round(100 * liq / mc, 1) if mc else None, c24=((p or {}).get("priceChange") or {}).get("h24"),
            estado="vivo" if liq >= 10000 else "débil" if liq >= 1000 else "muerto"))
    import re
    MAJ = {"JUP", "JTO", "PYTH", "RAY", "WSOL", "SOL", "PUMP", "JLP", "MSOL", "JITOSOL", "BSOL", "W", "WBTC", "CBBTC", "ETH", "WETH", "ORCA",
           "DRIFT", "KMNO", "HNT", "RENDER", "TRUMP", "MELANIA", "CLOUD", "ZEUS", "TNSR", "INF", "BNSOL", "HYPE", "XRP", "ZEC", "ZBTC"}
    for r in filas:  # tipo: meme / estable / acción tokenizada / grande (no son memecoins)
        S = (r["sym"] or "").upper()
        r["tipo"] = ("estable" if "USD" in S or S in {"EURC", "PYUSD", "USDG", "USD1"} else
                     "acción" if re.fullmatch(r"[A-Z]{1,5}X", S) and r["sym"].endswith("x") else
                     "grande" if S in MAJ or (r["mc"] or 0) > 1e9 else "meme")
    filas.sort(key=lambda r: (-r["usd_dentro"], -r["n_oper"]))
    json.dump(dict(generado=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), filas=filas), open("datos/tabla_A.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print("filas", len(filas), "vivos", sum(r["estado"] == "vivo" for r in filas), "con A dentro", sum(r["oper_dentro"] > 0 for r in filas))


if __name__ == "__main__":
    main()
