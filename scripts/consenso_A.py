"""Consenso A en vivo (16-nov, pedido por Fran tras ver KNIGHT, WIZARD, mihao…). Solo aviso y registro paper; no cambia reglas.

En cada escaneo y reloj vigila las compras nuevas de las 227 billeteras A sin bots (watch_solana.py con su propia lista
y estado). Si 2 o más OPERADORES A distintos (no billeteras) compran el mismo token en 72 h, sin importar edad ni pool:
  - lo agrega a datos/seguimiento.tsv (entrada en sombra a precio de ese momento; fotos de saldos + salida "copiar A"),
  - lo deja en datos/consenso_pendientes.json para que alerta_issue.py abra el aviso (issue) con GH_TOKEN.
Excluye tokens enormes (MC > 100 M USD: SOL, PUMP, acciones tokenizadas grandes, etc.).
"""
import csv, json, os, subprocess, sys, time, urllib.request
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from operadores import mapa

LOG = "datos/consenso_A_compras.tsv"
SEG = "datos/seguimiento.tsv"
PEND = "datos/consenso_pendientes.json"
CAMPOS_SEG = ["ts", "hora_utc", "token", "sym", "precio", "billeteras", "nota"]
VENTANA, MC_MAX, SOL_MIN = 72 * 3600, 100e6, 0.1


def leer(f):
    return list(csv.DictReader(open(f), delimiter="\t")) if os.path.exists(f) else []


def avisar():
    if not os.path.exists(PEND):
        return
    nuevas = json.load(open(PEND))
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not nuevas or not repo:
        return
    cuerpo = "\n".join(f"- **{a['sym']}** `{a['token']}`: {a['n_oper']} operadores A ({a['operadores']}), MC {a['mc']:,} USD, "
                       f"liq {a['liq']:,} USD, edad {a['edad_d']} d, pool contra {a['quote']}. https://dexscreener.com/solana/{a['token']}"
                       for a in nuevas)
    r = subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", f"Consenso A: {', '.join(a['sym'] for a in nuevas)[:80]}",
                        "--body", cuerpo + "\n\nPunto de seguimiento, no es entrada. Queda como entrada en sombra (paper)."], check=False)
    if r.returncode == 0:
        os.remove(PEND)


def main():
    if os.environ.get("GH_TOKEN") and not os.environ.get("HELIUS_API_KEY"):
        avisar(); return
    e = dict(os.environ, ES_H23="1", WL_FILE="datos/watchlist_A_oper.tsv", ST_FILE="datos/consenso_A_estado.json",
             LOG_FILE=LOG, AL_FILE="datos/consenso_A_wl.json", SEMILLA="1")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "watch_solana.py")], env=e, check=False)
    m = mapa()
    ahora = int(time.time())
    por = defaultdict(dict)  # token -> operador -> (billetera, ts)
    for r in leer(LOG):
        if ahora - int(r["ts"]) > VENTANA or float(r.get("sol_gastado") or 0) < SOL_MIN:
            continue
        op, bot = m.get(r["billetera"], (r["billetera"][:6], False))
        if not bot:
            por[r["token"]].setdefault(op, (r["billetera"], int(r["ts"])))
    ya = {r["token"] for r in leer(SEG)}
    cand = [t for t, d in por.items() if len(d) >= 2 and t not in ya]
    if not cand:
        print(f"consenso A: {len(por)} tokens comprados en 72 h, 0 nuevos con 2+ operadores"); return
    info = {}
    for i in range(0, len(cand), 30):
        try:
            req = urllib.request.Request("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(cand[i:i + 30]), headers={"User-Agent": "desk-consenso"})
            for p in json.load(urllib.request.urlopen(req, timeout=25)):
                a = p["baseToken"]["address"]
                if a not in info or ((p.get("liquidity") or {}).get("usd") or 0) > ((info[a].get("liquidity") or {}).get("usd") or 0):
                    info[a] = p
        except Exception as ex:
            print("dexscreener falló:", ex, file=sys.stderr)
    hora = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ahora))
    filas, avisos = [], []
    for t in cand:
        p = info.get(t)
        if not p:
            continue
        mc = p.get("marketCap") or p.get("fdv") or 0
        if mc > MC_MAX:
            continue
        d = por[t]
        filas.append(dict(ts=ahora, hora_utc=hora, token=t, sym=p["baseToken"]["symbol"], precio=p.get("priceUsd") or "",
                          billeteras=",".join(w for w, _ in d.values()), nota=f"consenso A en vivo: {len(d)} operadores"))
        avisos.append(dict(token=t, sym=p["baseToken"]["symbol"], n_oper=len(d), operadores=", ".join(sorted(d)), mc=round(mc),
                           liq=round((p.get("liquidity") or {}).get("usd") or 0), quote=p["quoteToken"]["symbol"],
                           edad_d=round((ahora * 1000 - (p.get("pairCreatedAt") or ahora * 1000)) / 8.64e7, 1)))
        print(f"CONSENSO A: {p['baseToken']['symbol']} {t} {len(d)} operadores ({', '.join(sorted(d))})")
    if filas:
        nuevo = not os.path.exists(SEG)
        with open(SEG, "a", newline="") as f:
            w = csv.DictWriter(f, CAMPOS_SEG, delimiter="\t")
            if nuevo: w.writeheader()
            w.writerows(filas)
        previo = json.load(open(PEND)) if os.path.exists(PEND) else []
        json.dump(previo + avisos, open(PEND, "w"), indent=1)
    if os.environ.get("GITHUB_ACTIONS"):
        subprocess.run(["git", "add", SEG, LOG, "datos/consenso_A_estado.json"], check=False)
    print(f"consenso A: {len(filas)} avisos nuevos")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("consenso A falló (no afecta el escaneo):", ex, file=sys.stderr)
