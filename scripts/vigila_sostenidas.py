"""Vigilancia de posiciones abiertas de A (16-nov, tras el caso BLOB que no se avisó). Solo aviso, no cambia reglas.

Tokens donde al menos un operador A sin bots sigue dentro según los vectores (compró ≥0,5 SOL, vendió menos del 70 %
de lo puesto, última operación en los últimos 30 días). En cada escaneo y cada reloj se consulta DexScreener y se avisa
si el token sube ≥50 % en 6 h (o ≥30 % en 1 h) con liquidez ≥30 mil USD.
Salida: datos/alertas_sostenidas.tsv (el radar la lee) y un issue de GitHub (corre desde alerta_issue.py, que tiene GH_TOKEN en escaneo y reloj).
Un mismo token no se vuelve a avisar en 12 h salvo que siga subiendo otro 50 %."""
import csv, json, os, subprocess, sys, time, urllib.request, urllib.error
from collections import defaultdict

ALERTAS = "datos/alertas_sostenidas.tsv"
CAMPOS = ["ts", "hora_utc", "token", "sym", "operadores", "billeteras", "dentro", "mc", "liq", "h1", "h6", "h24", "precio", "dexscreener"]
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


PEND = "datos/sostenidas_pendientes.json"
K = os.environ.get("HELIUS_API_KEY", "").strip()


def saldo_usd(w, t, precio):
    """Saldo real ahora (Helius, solo lectura). None si no se pudo consultar."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                       "params": [w, {"mint": t}, {"encoding": "jsonParsed"}]}).encode()
    for i in range(5):
        try:
            req = urllib.request.Request(f"https://mainnet.helius-rpc.com/?api-key={K}", data=body, headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=20)).get("result") or {}
            return sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0) for a in r.get("value", [])) * precio
        except urllib.error.HTTPError as e:
            if e.code != 429: return None
            time.sleep(2 + 2 * i)
        except Exception:
            time.sleep(1)
    return None


def avisar():
    """Crea el issue con lo pendiente (corre desde alerta_issue.py, que tiene GH_TOKEN)."""
    if not os.path.exists(PEND):
        return
    nuevas = json.load(open(PEND))
    repo = os.environ.get("GITHUB_REPOSITORY")
    if nuevas and repo:
        cuerpo = "\n".join(f"- **{a['sym']}** `{a['token']}`: +{a['h6']} % en 6 h (+{a['h1']} % en 1 h), MC {a['mc']:,}, liq {a['liq']:,}, "
                           f"siguen dentro (saldo real): {a['dentro']}. {a['dexscreener']}" for a in nuevas)
        r = subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", f"[registro] Sube token que nuestras A sostienen ({nuevas[0]['hora_utc']} UTC)",
                            "--body", cuerpo + "\n\nSolo aviso, paper trading."], check=False)
        if r.returncode == 0:
            os.remove(PEND)


def main():
    if os.environ.get("GH_TOKEN") and not K:
        avisar(); return
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
            mc = p.get("marketCap") or p.get("fdv") or 0
            if liq < LIQ_MIN or not (h6 >= SUBE_H6 or h1 >= SUBE_H1) or not mc or mc > 100e6:
                continue  # 17-nov: fuera MC > 100 M o sin MC (caso "HYPE" falso con MC de 246 mil millones)
            if a in ult and ahora - ult[a][0] < 12 * 3600 and precio < 1.5 * ult[a][1]:
                continue
            n, ws = pos[a]
            dentro = "sin verificar"
            if K:
                vivos = []
                for w in ws[:20]:
                    u = saldo_usd(w, a, precio); time.sleep(0.12)
                    if u is not None and u >= 20:
                        vivos.append(f"{w[:6]} {round(u):,} USD")
                if not vivos:
                    continue  # el vector decía que seguían dentro, pero ya vendieron: no se avisa
                dentro = ", ".join(vivos)
            nuevas.append(dict(dentro=dentro, ts=ahora, hora_utc=hora, token=a, sym=p["baseToken"]["symbol"], operadores=n,
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
    if nuevas:
        previo = json.load(open(PEND)) if os.path.exists(PEND) else []
        json.dump(previo + nuevas, open(PEND, "w"), indent=1)
    if os.environ.get("GITHUB_ACTIONS"):  # el reloj solo hace git add de algunos archivos: se deja preparado aquí
        subprocess.run(["git", "add", ALERTAS], check=False)
    print(f"sostenidas: {len(toks)} tokens vigilados, {len(nuevas)} avisos")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("sostenidas falló (no afecta el escaneo):", e, file=sys.stderr)
