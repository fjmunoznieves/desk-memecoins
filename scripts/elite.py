"""Operadores de élite (17-nov, Fran) para H27 en sombra. Se calcula de la historia ya bajada (vector_ops_A/B + vector_profundo, sumados),
sin gastar Helius. Por billetera (sin bots), jugadas con ≥0,5 SOL y al menos una venta:
  élite = 20+ jugadas, ganancia ≥100 SOL aun quitando su mejor jugada (no depende de un solo golpe) y 5 %+ de jugadas en x2
  (descarta scalpers que ganan seguido pero poco).
Ojo: la historia de las A cubre ~60 días y muchas quedaron cortadas en 100 páginas (ver cobertura en la memoria).
Salida: datos/elite.tsv"""
import csv, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from operadores import mapa


def main():
    m = mapa()
    g = {r["billetera"]: r["grupo"] for r in csv.DictReader(open("datos/operadores.tsv"), delimiter="\t")}
    # 17-nov: la historia está partida en dos tramos que se SUMAN por billetera×token: vector_ops_* (reciente) y
    # vector_profundo (anterior). Usar solo uno subestimaba (7entn7 daba -37 SOL; con ambos tramos +501).
    agg, cort = defaultdict(lambda: [0.0, 0.0, 0.0]), {}
    for fn in ("datos/vector_ops_A_289.tsv", "datos/vector_ops_B_148.tsv", "datos/vector_profundo.tsv"):
        if not os.path.exists(fn):
            continue
        for r in csv.DictReader(open(fn), delimiter="\t"):
            try:
                si, so, ve = float(r["sol_in"]), float(r["sol_out"]), float(r["ventas"] or 0)
            except (TypeError, ValueError):
                continue
            a = agg[(r["billetera"], r["token"])]; a[0] += si; a[1] += so; a[2] += ve
            if "profundo" in fn:
                cort[r["billetera"]] = r.get("historial_cortado", "")
    st = defaultdict(list)
    for (b, t), (si, so, ve) in agg.items():
        if si >= 0.5 and ve > 0:
            st[b].append((si, so))
    filas = []
    for w, v in st.items():
        op, bot = m.get(w, (w[:6], False))
        if bot:
            continue
        n = len(v); pnl = sum(so - si for si, so in v); best = max(so - si for si, so in v)
        x2 = sum(so >= 2 * si for si, so in v) / n
        if n >= 20 and pnl - best >= 100 and x2 >= 0.05:
            filas.append(dict(billetera=w, operador=op, grupo=g.get(w, "?"), jugadas=n,
                              pct_gana=round(100 * sum(so > si for si, so in v) / n), pct_x2=round(100 * x2),
                              pnl_sol=round(pnl, 1), pnl_sin_mejor=round(pnl - best, 1), historial_cortado=cort.get(w, "")))
    filas.sort(key=lambda r: -r["pnl_sin_mejor"])
    with open("datos/elite.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, list(filas[0]), delimiter="\t"); w.writeheader(); w.writerows(filas)
    print(f"élite: {len(filas)} billeteras")
    for r in filas:
        print(r["billetera"][:6], r["grupo"], r["jugadas"], f'{r["pct_gana"]}%', f'x2 {r["pct_x2"]}%', r["pnl_sol"], r["pnl_sin_mejor"])


if __name__ == "__main__":
    main()
