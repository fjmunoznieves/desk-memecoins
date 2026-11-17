"""Datos para la Mesa interactiva (17-nov, pedido de Fran: conversaciones interactivas). Solo lee lo ya guardado
(sin Helius, sin APIs). Arma datos/mesa.json con: tokens en seguimiento + H25 + H27, su estructura (liquidez, MC,
holders), quién de los nuestros sostiene (últimas fotos de saldo, y la anterior para ver si venden), su jugada en ese
token y su historial completo por OPERADOR (vector_ops_A/B + vector_profundo SUMADOS por billetera×token), más el
resultado de los métodos de salida en sombra. La página de la Mesa lo lee y se lo pasa a Claude al preguntar."""
import csv, json, os, sys, time
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from operadores import mapa

D = "datos/"


def leer(fn):
    p = D + fn
    return list(csv.DictReader(open(p), delimiter="\t")) if os.path.exists(p) else []


def num(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def main():
    m = mapa()
    grupo = {r["billetera"]: r["grupo"] for r in leer("operadores.tsv")}
    elite_ops = {r["operador"] for r in leer("elite.tsv")}

    # historia sumada por billetera×token (los dos tramos)
    agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, None, None])
    for fn in ("vector_ops_A_289.tsv", "vector_ops_B_148.tsv", "vector_profundo.tsv"):
        for r in leer(fn):
            si, so = num(r["sol_in"], 0), num(r["sol_out"], 0)
            a = agg[(r["billetera"], r["token"])]
            a[0] += si; a[1] += so; a[2] += num(r.get("compras"), 0); a[3] += num(r.get("ventas"), 0)
            pc, ul = num(r.get("primera_compra")), num(r.get("ultima"))
            if pc: a[4] = min(a[4] or pc, pc)
            if ul: a[5] = max(a[5] or ul, ul)
    # historial por operador (jugadas ≥0,5 SOL con al menos una venta)
    por_op = defaultdict(list); tmin, tmax = {}, {}
    for (b, t), (si, so, c, v, pc, ul) in agg.items():
        op = m.get(b, (b[:6], False))[0]
        if pc: tmin[op] = min(tmin.get(op, pc), pc)
        if ul: tmax[op] = max(tmax.get(op, ul), ul)
        if si >= 0.5 and v > 0:
            por_op[op].append((si, so))

    def hist(op):
        v = por_op.get(op, [])
        if not v:
            return dict(jugadas=0)
        n = len(v); pnl = sum(so - si for si, so in v); best = max(so - si for si, so in v)
        dias = round(((tmax.get(op) or 0) - (tmin.get(op) or 0)) / 86400) if tmin.get(op) else None
        return dict(jugadas=n, pct_gana=round(100 * sum(so > si for si, so in v) / n), pct_x2=round(100 * sum(so >= 2 * si for si, so in v) / n),
                    pnl_sol=round(pnl, 1), pnl_sin_mejor=round(pnl - best, 1), dias_cubiertos=dias, elite=op in elite_ops)

    # universo de tokens
    toks = {}
    for r in leer("seguimiento.tsv"):
        toks.setdefault(r["token"], dict(token=r["token"], sym=r["sym"], cadena="solana", nota=r.get("nota", ""), desde=r["hora_utc"], senales=[]))
    for fn, h in (("h25_sombra.tsv", "H25"), ("h27_sombra.tsv", "H27")):
        for r in leer(fn):
            t = toks.setdefault(r["token"], dict(token=r["token"], sym=r["sym"], cadena=r.get("cadena", "solana"), nota="", desde=r["hora_utc"], senales=[]))
            t["senales"].append(f'{h} {r["hora_utc"]}: {r.get("motivo", "")}')

    liq = {}
    for r in leer("liquidez_seguimiento.tsv"):
        liq[r["token"]] = r  # el último gana
    # fotos: por token×billetera, lista de (hora, usd)
    fotos = defaultdict(lambda: defaultdict(list))
    for r in leer("fotos_saldos.tsv"):
        if r["token"] in toks:
            fotos[r["token"]][r["billetera"]].append((r["hora_utc"], num(r["usd"], 0), r["grupo"]))
    salidas = defaultdict(list)
    for r in leer("salidas_sombra.tsv"):
        salidas[r["token"]].append({k: r.get(k, "") for k in ("hora_utc", "hip", "precio", "n_oper", "max7d_pct", "esc_pct", "esc35_pct", "trail30_pct", "copiaA_pct", "estado")})

    for tk, t in toks.items():
        l = liq.get(tk)
        if l:
            t["estructura"] = {k: l.get(k) for k in ("hora_utc", "liq", "mc", "liq_mc_pct", "vol5m", "vol1h", "vol24h", "precio", "pool", "holders", "mc_por_holder")}
        hold = []
        for b, fs in fotos.get(tk, {}).items():
            fs.sort()
            op, bot = m.get(b, (b[:6], False))
            ag = agg.get((b, tk))
            hold.append(dict(billetera=b, operador=op, bot=bot, grupo=grupo.get(b, fs[-1][2]),
                             usd_ahora=round(fs[-1][1]), foto=fs[-1][0], usd_antes=round(fs[-2][1]) if len(fs) > 1 else None,
                             usd_max=round(max(x[1] for x in fs)),
                             jugada=dict(sol_in=round(ag[0], 2), sol_out=round(ag[1], 2), compras=int(ag[2]), ventas=int(ag[3]),
                                         desde=time.strftime("%Y-%m-%d %H:%M", time.gmtime(ag[4])) if ag[4] else None) if ag else None))
        hold.sort(key=lambda h: -h["usd_ahora"])
        ops = sorted({h["operador"] for h in hold if not h["bot"]})
        t["sostienen"] = hold
        t["operadores"] = {op: hist(op) for op in ops}
        dentro = [op for op in ops if any(h["operador"] == op and h["usd_ahora"] >= 20 for h in hold)]
        t["resumen"] = dict(operadores_dentro=len(dentro), elite_dentro=sum(t["operadores"][o].get("elite", False) for o in dentro),
                            usd_dentro=round(sum(h["usd_ahora"] for h in hold if h["usd_ahora"] >= 20 and not h["bot"])),
                            salieron=len([op for op in ops if op not in dentro]))
        t["salidas_sombra"] = salidas.get(tk, [])[-5:]
        t["dexscreener"] = f'https://dexscreener.com/{"bsc" if t["cadena"] in ("bnb", "bsc") else t["cadena"]}/{tk}'

    # resumen de métodos de salida (señales cerradas)
    met = defaultdict(list)
    for rs in salidas.values():
        for r in rs:
            for k in ("esc_pct", "esc35_pct", "trail30_pct", "copiaA_pct"):
                x = num(r[k])
                if x is not None:
                    met[k].append(x)
    out = dict(generado=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
               metodos_salida={k: dict(n=len(v), promedio=round(sum(v) / len(v), 1)) for k, v in met.items() if v},
               tokens=sorted(toks.values(), key=lambda t: -t["resumen"]["usd_dentro"]))
    json.dump(out, open(D + "mesa.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(f'mesa: {len(toks)} tokens, {os.path.getsize(D + "mesa.json") // 1024} KB')
    if os.environ.get("GITHUB_ACTIONS"):
        import subprocess
        subprocess.run(["git", "add", D + "mesa.json"], check=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("mesa_datos falló (no afecta el escaneo):", e)
