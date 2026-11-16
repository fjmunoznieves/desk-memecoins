"""Vigilancia de posiciones abiertas de A (16-nov, tras el caso BLOB que no se avisó). Solo aviso, no cambia reglas.

Tokens donde al menos un operador A sin bots sigue dentro según los vectores (compró ≥0,5 SOL, vendió menos del 70 %
de lo puesto, última operación en los últimos 30 días). En cada escaneo y cada reloj se consulta DexScreener y se avisa
si el token sube ≥50 % en 6 h (o ≥30 % en 1 h) con liquidez ≥30 mil USD.
Salida: datos/alertas_sostenidas.tsv (el radar la lee) y un issue de GitHub (corre desde alerta_issue.py, que tiene GH_TOKEN en escaneo y reloj).
Un mismo token no se vuelve a avisar en 12 h salvo que siga subiendo otro 50 %."""
import csv, json, os, subprocess, sys, time, urllib.request
from collections import defaultdict

ALERTAS = "datos/alertas_sostenidas.tsv"
CAMPOS = ["ts", "hora_utc", "token", "sym", "operadores", "billeteras", "mc", "liq", "h1", "h6", "h24", "precio", "dexscreener"]
SUBE_H6, SUBE_H1, LIQ_MIN = 50, 30, 30000


def leer(f):
    return list(csv.DictReader(open(f), delimiter="\t")) if os.path.exists(f) else []


def posiciones():
    ops = {r["billetera"]: r for r in leer("datos/operadores.tsv")}
    pos = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0, set()]))
    for f in ("datos/vector_ops_A_289.tsv", "datos/vector_profundo.tsv"):
        for r in leer(f):
            o = ops.get(r["billetera"], {})
            if o.get("bot") == "si" or o.get("grupo", "A") != "A":
                continue
            p = pos[r["token"]][o.get("operador") or r["billetera"][:6]]
            p[0] += float(r["sol_in"] or 0); p[1] += float(r["sol_out"] or 0)
            p[2] = max(p[2], int(r["ultima"] or 0)); p[3].add(r["billetera"])
    lim = time.time() - 30 * 86400
    out = {}
    for t, d in pos.items():
        dentro = {op: v for op, v in d.items() if v[0] >= 0.5 and v[1] < 0.7 * v[0] and v[2] >= lim}
        if dentro:
            out[t] = (len(dentro), sorted(set().union(*(v[3] for v in dentro.values()))))
    return out


def main():
    pos = posiciones()
    toks = list(pos)
    previas = leer(ALERTAS)
    ult = {}
    for a in previas:
        ult[a["token"]] = (int(a["ts"]), float(a["precio"] or 0))
    ahora = int(time.time()); hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora))
    nuevas = []
    for i in range(0, len(toks), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(toks[i:i + 30]),
                                         headers={"User-Agent": "desk-sostenidas"})
            pares = json.load(urllib.request.urlopen(req, timeout=25))
        except Exception as e:
            print("dexscreener falló:", e, file=sys.stderr); time.sleep(2); continue
        mejor = {}
        for p in pares:
            a = p["baseToken"]["address"]
            if a in pos and ((p.get("liquidity") or {}).get("usd") or 0) > ((mejor.get(a, {}).get("liquidity") or {}).get("usd") or 0):
                mejor[a] = p
        for a, p in mejor.items():
            ch, liq = p.get("priceChange") or {}, (p.get("liquidity") or {}).get("usd") or 0
            h1, h6 = float(ch.get("h1") or 0), float(ch.get("h6") or 0)
            precio = float(p.get("priceUsd") or 0)
            if liq < LIQ_MIN or not (h6 >= SUBE_H6 or h1 >= SUBE_H1):
                continue
            if a in ult and ahora - ult[a][0] < 12 * 3600 and precio < 1.5 * ult[a][1]:
                continue
            n, ws = pos[a]
            nuevas.append(dict(ts=ahora, hora_utc=hora, token=a, sym=p["baseToken"]["symbol"], operadores=n,
                               billeteras=",".join(w[:6] for w in ws[:15]), mc=round(p.get("marketCap") or p.get("fdv") or 0),
                               liq=round(liq), h1=h1, h6=h6, h24=ch.get("h24"), precio=precio,
                               dexscreener=f"https://dexscreener.com/solana/{a}"))
        time.sleep(0.25)
    nuevo = not os.path.exists(ALERTAS)
    with open(ALERTAS, "a", newline="") as f:
        w = csv.DictWriter(f, CAMPOS, delimiter="\t")
        if nuevo: w.writeheader()
        w.writerows(nuevas)
    for a in nuevas:
        print(f"SOSTENIDA SUBE: {a['sym']} {a['token']} h1 {a['h1']} % h6 {a['h6']} % mc {a['mc']} liq {a['liq']} operadores A dentro {a['operadores']}")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if nuevas and repo and os.environ.get("GH_TOKEN"):
        cuerpo = "\n".join(f"- **{a['sym']}** `{a['token']}`: +{a['h6']} % en 6 h (+{a['h1']} % en 1 h), MC {a['mc']:,}, liq {a['liq']:,}, "
                           f"{a['operadores']} operadores A dentro. {a['dexscreener']}" for a in nuevas)
        subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", f"Sube token que nuestras A sostienen ({hora} UTC)",
                        "--body", cuerpo + "\n\nSolo aviso, paper trading."], check=False)
    print(f"sostenidas: {len(toks)} tokens vigilados, {len(nuevas)} avisos")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("sostenidas falló (no afecta el escaneo):", e, file=sys.stderr)
