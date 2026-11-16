"""Cuenta operadores distintos (no billeteras) para el consenso.

datos/operadores.tsv sale de la retrospectiva del 16-nov: billeteras que entran juntas
(≤2 min en ≥3 tokens y ≥30 % de sus tokens) se agrupan como un solo operador, y las que
operan >200 veces al día se marcan como bot. Un bot no suma consenso.
"""
import csv
import os

_MAPA = None


def mapa():
    global _MAPA
    if _MAPA is None:
        _MAPA = {}
        f = "datos/operadores.tsv"
        if os.path.exists(f):
            for r in csv.DictReader(open(f), delimiter="\t"):
                _MAPA[r["billetera"]] = (r["operador"], r["bot"] == "si")
    return _MAPA


def n_operadores(billeteras):
    """Operadores distintos que no son bots."""
    m = mapa()
    ops = set()
    for b in billeteras:
        op, bot = m.get(b, (b[:6], False))
        if not bot:
            ops.add(op)
    return len(ops)
