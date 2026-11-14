"""Suma al universo H16 los tokens del escaneo que ya tienen más de 7 días (rows.json de scan.py)."""
import json, sys
U = "datos/resurreccion_universo.json"
u = json.load(open(U))
ya = {(t["net"], t["token"]) for t in u}
n = 0
for r in json.load(open(sys.argv[1] if len(sys.argv) > 1 else "rows.json")):
    if (r.get("age_h") or 0) >= 168 and (r.get("mc") or 0) >= 30000 and r.get("pair") and (r["chain"], r["addr"]) not in ya:
        u.append({"net": r["chain"], "token": r["addr"], "sym": r["sym"], "pool": r["pair"], "revivio": 0})
        ya.add((r["chain"], r["addr"]))
        n += 1
json.dump(u, open(U, "w"), indent=0)
print(f"universo H16: +{n} nuevos, total {len(u)}")
