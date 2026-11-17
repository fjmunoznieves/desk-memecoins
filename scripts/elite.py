"""Operadores de élite (17-nov, Fran) para H27 en sombra. Se calcula de la historia ya bajada (datos/vector_profundo.tsv),
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
    st, cort = defaultdict(list), {}
    for r in csv.DictReader(open("datos/vector_profundo.tsv"), delimiter="\t"):
        try:
            si, so = float(r["sol_in"]), float(r["sol_out"])
        except (TypeError, ValueError):
            continue
        cort[r["billetera"]] = r.get("historial_cortado", "")
        if si >= 0.5 and float(r["ventas"] or 0) > 0:
            st[r["billetera"]].append((si, so))
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
