"""Salidas en sombra (16-nov, aprobado por Fran tras la retrospectiva). Solo registro paper; no cambia ninguna regla.

Para cada señal de H21, H22, H23 y H24 (Solana y BNB) guarda en datos/salidas_sombra.tsv tres formas de salir:
  1. actual: la medición de hoy (cambio a 24 h y a 7 días, columnas c24 / c7d del estudio).
  2. escalonada: velas de 1 h desde la señal; stop -20 %, vende 1/3 en x2, 1/3 en x3 y el resto con trailing
     de 30 % desde el máximo; cierre forzado a 7 días. Si en una vela tocan stop y objetivo, se asume el stop.
  3. copiar A: sale cuando la mitad o más de los operadores (sin bots) que tenían ≥5 USD del token en la primera
     foto de saldos bajaron su saldo 30 % o más (datos/fotos_saldos.tsv, 3:47 AM y PM). Ese momento queda también
     como aviso en datos/alertas_salida.tsv para el radar.
  4. (17-nov, Fran) comparativo en las mismas velas: escalonada con stop -35 % (esc35) y trailing 30 % puro sin stop
     fijo ni ventas parciales (trail30).
También guarda pasa_oper = "sí" si la señal tiene 2 o más operadores reales sin bots (consenso por operadores).
"""
import csv, os, sys, time
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from sombra import get, pool_de, GNET
from operadores import mapa

SALIDA = "datos/salidas_sombra.tsv"
ALERTAS = "datos/alertas_salida.tsv"
CAMPOS = ["ts", "hora_utc", "hip", "cadena", "token", "sym", "precio", "n_billeteras", "n_oper", "pasa_oper",
          "c24", "c7d", "max7d_pct", "esc_pct", "esc_detalle", "esc35_pct", "esc35_detalle", "trail30_pct", "trail30_detalle", "copiaA_pct", "copiaA_hora", "copiaA_detalle", "hib_pct", "hib_detalle", "pool", "estado"]
CAMPOS_AL = ["ts", "hora_utc", "hip", "token", "sym", "operadores_con_saldo", "operadores_vendieron", "precio", "cambio_desde_senal"]
PRESUPUESTO_S = 120  # 17-nov: bajado de 240 (minutos de GitHub)


def leer(f):
    return list(csv.DictReader(open(f), delimiter="\t")) if os.path.exists(f) else []


def senales():
    out = []
    for f, hip, col_n, col_o in (("datos/h21_consenso.tsv", "H21", "n", "n_oper"), ("datos/h23_consenso.tsv", "H23", "n", "n_oper"),
                                 ("datos/h22_cruce.tsv", "H22", "nB", "nB_oper"), ("datos/h24_pool_acciones.tsv", "H24", None, "operadores")):
        for r in leer(f):
            n = r.get(col_n) if col_n else sum(int(r.get(k) or 0) for k in "ABC")
            out.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], hip=hip, cadena=r.get("cadena") or "solana", token=r["token"],
                            sym=r["sym"], precio=r["precio"], n_billeteras=n, n_oper=r.get(col_o, ""),
                            c24=r.get("c24", ""), c7d=r.get("c7d", ""), pool=r.get("pool", "")))
    vistos = set()
    for r in leer("datos/alertas_sostenidas.tsv"):  # 16-nov: tokens que nuestras A sostienen y suben
        if r["token"] in vistos:
            continue
        vistos.add(r["token"])
        out.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], hip="SOST", cadena="solana", token=r["token"], sym=r["sym"],
                        precio=r["precio"], n_billeteras=len(r["billeteras"].split(",")), n_oper=r["operadores"], c24="", c7d="", pool=""))
    for f, hip in (("datos/h25_sombra.tsv", "H25"), ("datos/h26_sombra.tsv", "H26"), ("datos/h27_sombra.tsv", "H27"),
                   ("datos/imitadores.tsv", "IMIT"), ("datos/h28_sombra.tsv", "H28"), ("datos/h29_sombra.tsv", "H29"), ("datos/h30_sombra.tsv", "H30"), ("datos/h31_sombra.tsv", "H31"), ("datos/h31p_sombra.tsv", "H31p")):  # 17-nov (Fran): estudios en sombra
        for r in leer(f):
            out.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], hip=hip, cadena=r["cadena"], token=r["token"], sym=r["sym"],
                            precio=r["precio"], n_billeteras="", n_oper=r.get("n_oper", r.get("n_elite", "")), c24="", c7d="", pool=r.get("pool", "")))
    for r in leer("datos/seguimiento.tsv"):  # 16-nov: puntos de seguimiento (consenso A con saldo real)
        out.append(dict(ts=r["ts"], hora_utc=r["hora_utc"], hip="SEG", cadena="solana", token=r["token"], sym=r["sym"],
                        precio=r["precio"], n_billeteras=len(r["billeteras"].split(",")), n_oper="", c24="", c7d="", pool=""))
    return out


def escalonada(c, p0, stop_ini=0.8):
    stop, pos, pnl, peak, t2, t3 = p0 * stop_ini, 1.0, 0.0, p0, False, False
    for ts, o, h, l, cl, v in c:
        if l <= stop:
            pnl += pos * (stop / p0 - 1)
            return pnl * 100, "stop" if not t2 else "trailing"
        if not t2 and h >= 2 * p0:
            pnl += (1 / 3) * 1.0; pos -= 1 / 3; t2 = True
        if t2 and not t3 and h >= 3 * p0:
            pnl += (1 / 3) * 2.0; pos -= 1 / 3; t3 = True
        peak = max(peak, h)
        if t2:
            stop = max(stop, peak * 0.7)
    if c:
        pnl += pos * (c[-1][4] / p0 - 1)
    if c and c[-1][0] < c[0][0] + 6.9 * 86400:
        return pnl * 100, "en curso (valor a hoy)" if not t2 else "en curso, ya vendió 1/3 en x2"
    return pnl * 100, "cierre 7 d" if t2 else "cierre 7 d sin x2"


def trailing(c, p0, caida=0.3):
    """17-nov (Fran, comparativo de salidas): sin stop fijo ni ventas parciales; vende todo cuando cae 30 % desde el máximo."""
    peak = p0
    for ts, o, h, l, cl, v in c:
        if l <= peak * (1 - caida):
            return (peak * (1 - caida) / p0 - 1) * 100, "trailing"
        peak = max(peak, h)
    if c and c[-1][0] < c[0][0] + 6.9 * 86400:
        return (c[-1][4] / p0 - 1) * 100, "en curso (valor a hoy)"
    return ((c[-1][4] / p0 - 1) * 100 if c else 0), "cierre 7 d"


def hibrida(c, p0, salida_a=None, freno=0.65):
    """18-nov (Fran aprobó): vende 1/3 en x2 y 1/3 en x3; el resto NO se vende por precio: se aguanta mientras las A sigan
    dentro y se vende cuando sale la mitad de los operadores (copiar A, con el retraso real de las fotos). Freno de
    catástrofe −35 %. Histórico (95 entradas filtro no perseguir + MC ≤2M, sin top 3): +296 USD vs +214 de la escalonada."""
    pos, pnl, t2, t3 = 1.0, 0.0, False, False
    for ts, o, h, l, cl, v in c:
        if l <= p0 * freno:
            return (pnl + pos * (freno - 1)) * 100, "freno −35 %" + (" (tras x2)" if t2 else "")
        if not t2 and h >= 2 * p0:
            pnl += 1 / 3; pos -= 1 / 3; t2 = True
        if t2 and not t3 and h >= 3 * p0:
            pnl += 2 / 3; pos -= 1 / 3; t3 = True
        if salida_a and ts >= salida_a - salida_a % 3600:
            return (pnl + pos * (cl / p0 - 1)) * 100, "salieron las A" + (" (tras x2)" if t2 else "")
    if c:
        pnl += pos * (c[-1][4] / p0 - 1)
    return pnl * 100, "en curso (valor a hoy)" + (", ya vendió 1/3 en x2" if t2 else "")


def copiar_A():
    """token -> (ts, precio, con_saldo, vendieron) del primer momento en que salió la mitad de los operadores."""
    m = mapa()
    fotos = defaultdict(lambda: defaultdict(dict))  # token -> ts -> billetera -> (usd, cantidad, precio)
    for r in leer("datos/fotos_saldos.tsv"):
        fotos[r["token"]][int(r["ts"])][r["billetera"]] = (float(r["usd"] or 0), float(r["cantidad"] or 0), float(r["precio"] or 0))
    res = {}
    for tok, por_ts in fotos.items():
        tss = sorted(por_ts)
        if len(tss) < 2:
            continue
        base = por_ts[tss[0]]
        ops = defaultdict(float)  # operador -> cantidad inicial
        for w, (usd, cant, _) in base.items():
            op, bot = m.get(w, (w[:6], False))
            if usd >= 5 and not bot:
                ops[op] += cant
        if not ops:
            continue
        for t in tss[1:]:
            ahora = defaultdict(float)
            for w, (_, cant, _) in por_ts[t].items():
                op, bot = m.get(w, (w[:6], False))
                if op in ops:
                    ahora[op] += cant
            vend = sum(1 for op, q in ops.items() if ahora.get(op, 0) <= 0.7 * q)
            if vend * 2 >= len(ops):
                precio = next((p for _, _, p in por_ts[t].values() if p), 0)
                res[tok] = (t, precio, len(ops), vend)
                break
    return res


def main():
    t_ini = time.time()
    previas = {(r["hip"], r["token"]): r for r in leer(SALIDA)}
    salida_A = copiar_A()
    alertas = leer(ALERTAS)
    ya_al = {(a["hip"], a["token"]) for a in alertas}
    filas = []
    for s in senales():
        r = previas.get((s["hip"], s["token"]), {})
        r.update({k: v for k, v in s.items() if v not in ("", None) or k not in r})
        try:
            r["pasa_oper"] = "sí" if int(r["n_oper"]) >= 2 else "no"
        except (KeyError, TypeError, ValueError):
            r["pasa_oper"] = ""  # aún sin conteo de operadores (H24 lo llena en el próximo escaneo)
        p0 = float(r["precio"] or 0)
        # copiar A
        a = salida_A.get(r["token"])
        if a and a[0] >= int(r["ts"]) and not r.get("copiaA_hora") and p0:
            r["copiaA_hora"] = time.strftime("%Y-%m-%d %H:%M", time.gmtime(a[0]))
            r["copiaA_pct"] = round((a[1] / p0 - 1) * 100, 1) if a[1] else ""
            r["copiaA_detalle"] = f"{a[3]} de {a[2]} operadores bajaron ≥30 %"
            if (r["hip"], r["token"]) not in ya_al:
                alertas.append(dict(ts=a[0], hora_utc=r["copiaA_hora"], hip=r["hip"], token=r["token"], sym=r["sym"],
                                    operadores_con_saldo=a[2], operadores_vendieron=a[3], precio=a[1], cambio_desde_senal=r["copiaA_pct"]))
                print(f"salida A: {r['sym']} {r['token']} ({r['hip']}) {a[3]}/{a[2]} operadores vendieron, {r['copiaA_pct']} % desde la señal")
        # escalonada (se recalcula hasta cumplir 7 días)
        edad = time.time() - int(r["ts"])
        if (r.get("estado") != "cerrado" or not r.get("esc35_pct") or not r.get("hib_pct")) and p0 and r["cadena"] in GNET and edad >= 3600 and time.time() - t_ini < PRESUPUESTO_S:
            pool = r.get("pool") or pool_de(r["cadena"], r["token"])
            if pool:
                r["pool"] = pool
                t0 = int(r["ts"])
                d = get(f"https://api.geckoterminal.com/api/v2/networks/{GNET[r['cadena']]}/pools/{pool}/ohlcv/hour"
                        f"?aggregate=1&limit=200&currency=usd&token={r['token']}&before_timestamp={t0 + 7 * 86400}")
                time.sleep(2.2)
                try:
                    c = sorted(x for x in d["data"]["attributes"]["ohlcv_list"] if t0 <= x[0] <= t0 + 7 * 86400)
                except Exception:
                    c = []
                if c:
                    r["max7d_pct"] = round((max(x[2] for x in c) / p0 - 1) * 100, 1)
                    pct, det = escalonada(c, p0)
                    r["esc_pct"], r["esc_detalle"] = round(pct, 1), det
                    # 17-nov (Fran): comparativo de salidas en las mismas velas (sin consultas extra)
                    pct35, det35 = escalonada(c, p0, 0.65)
                    r["esc35_pct"], r["esc35_detalle"] = round(pct35, 1), det35
                    pct_t, det_t = trailing(c, p0)
                    r["trail30_pct"], r["trail30_detalle"] = round(pct_t, 1), det_t
                    sa = a[0] if a and a[0] >= t0 else None
                    pct_h, det_h = hibrida(c, p0, sa)
                    r["hib_pct"], r["hib_detalle"] = round(pct_h, 1), det_h
                    r["estado"] = "cerrado" if edad >= 7 * 86400 else "abierto"
        r.setdefault("estado", "abierto")
        filas.append(r)
    with open(SALIDA, "w", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(filas)
    with open(ALERTAS, "w", newline="") as f:
        w = csv.DictWriter(f, CAMPOS_AL, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(alertas)
    print(f"salidas: {len(filas)} señales, {sum(1 for r in filas if r.get('esc_pct') not in ('', None))} con escalonada, "
          f"{len(alertas)} avisos de salida A")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("salidas falló (no afecta el escaneo):", e, file=sys.stderr)
