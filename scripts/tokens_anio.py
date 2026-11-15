#!/usr/bin/env python3
"""Análisis por token, 1 año (solo lectura): ¿aparecen nuestras billeteras A (289) y B (148) entre los primeros
compradores de cada token, y cómo le fue al token?

1. GeckoTerminal (gratis): velas diarias del pool → múltiplo máximo (máximo / apertura del 1.er día) y caída actual.
2. Helius: compradores en las primeras 72 h del pool (hasta MAX_PAG páginas de 100 tx, en orden cronológico).
3. Cruce con datos/vector_A_289.tsv y datos/vector_B_148.tsv.
Salida: datos/tokens_anio_resultado.tsv. Necesita HELIUS_API_KEY; la clave nunca se imprime.
"""
import csv, json, os, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

K = os.environ.get("HELIUS_API_KEY", "")
if not K:
    print("Falta HELIUS_API_KEY"); sys.exit(0)
RPC = f"https://mainnet.helius-rpc.com/?api-key={K}"
MAX_PAG = int(os.environ.get("MAX_PAG") or 10)
HORAS = 72


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-anio/1.0 (solo lectura)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15 + 10 * i); continue
            return None
        except Exception:
            time.sleep(3)
    return None


def rpc(m, p):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for i in range(6):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            if "error" in d:
                print("  error RPC:", str(d["error"])[:200], flush=True); return None
            return d.get("result")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return None
            time.sleep(1 + 2 * i)
        except Exception:
            time.sleep(2)
    return None


def velas(pool):
    d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/day?limit=400&currency=usd")
    try:
        lista = sorted(d["data"]["attributes"]["ohlcv_list"])  # [ts, o, h, l, c, v]
    except Exception:
        return None
    if not lista:
        return None
    o = lista[0][1] or lista[0][4]
    hi = max(x[2] for x in lista)
    ts_hi = max(lista, key=lambda x: x[2])[0]
    ult = lista[-1][4]
    return dict(multiplo=round(hi / o, 2) if o else "", dias_al_max=round((ts_hi - lista[0][0]) / 86400),
                hoy_vs_max=round(ult / hi, 3) if hi else "")


def compradores(pool, mint, t0):
    out, token, pags = {}, None, 0
    while pags < MAX_PAG:
        opts = {"transactionDetails": "full", "sortOrder": "asc", "limit": 100, "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 1,
                "filters": {"blockTime": {"gte": t0, "lt": t0 + HORAS * 3600}, "status": "succeeded"}}
        if token:
            opts["paginationToken"] = token
        r = rpc("getTransactionsForAddress", [pool, opts])
        if not r:
            break
        for tx in r.get("data") or []:
            meta = tx.get("meta") or {}
            pre = {b.get("owner"): float(b["uiTokenAmount"].get("uiAmount") or 0)
                   for b in meta.get("preTokenBalances") or [] if b.get("mint") == mint}
            for b in meta.get("postTokenBalances") or []:
                if b.get("mint") == mint and b.get("owner") and float(b["uiTokenAmount"].get("uiAmount") or 0) > pre.get(b["owner"], 0):
                    out.setdefault(b["owner"], tx.get("blockTime"))
        pags += 1
        token = r.get("paginationToken")
        if not token:
            break
    out.pop(pool, None)
    return out, pags, bool(token)


def main():
    A = {r["direccion"] for r in csv.DictReader(open("datos/vector_A_289.tsv"), delimiter="\t")}
    B = {r["direccion"] for r in csv.DictReader(open("datos/vector_B_148.tsv"), delimiter="\t")}
    toks = list(csv.DictReader(open("datos/tokens_anio.tsv"), delimiter="\t"))
    print(f"tokens: {len(toks)}  A: {len(A)}  B: {len(B)}", flush=True)

    # 1) velas (GeckoTerminal ~30/min): en un hilo aparte mientras Helius trabaja
    def todas_velas():
        res = {}
        if os.environ.get("SIN_VELAS"):
            return res  # GeckoTerminal limita mucho desde GitHub: las velas se calculan aparte
        for t in toks:
            res[t["token"]] = velas(t["pool"]) or {}
            time.sleep(2.1)
        return res

    with ThreadPoolExecutor(1) as gex:
        fut = gex.submit(todas_velas)

        def uno(t):
            c, pags, cortado = compradores(t["pool"], t["token"], int(t["creado"]))
            return t, c, pags, cortado

        filas, todos = [], {}
        with ThreadPoolExecutor(3) as ex:
            for t, c, pags, cortado in ex.map(uno, toks):
                a = sorted(w for w in c if w in A); b = sorted(w for w in c if w in B)
                for w, bt in c.items():
                    if w not in A and w not in B:
                        todos.setdefault(w, []).append((t["token"], t["sym"], bt))
                filas.append(dict(sym=t["sym"], token=t["token"], creado=time.strftime("%Y-%m-%d", time.gmtime(int(t["creado"]))),
                                  semestre="S1" if int(t["creado"]) < 1779062400 else "S2",  # 2026-05-18
                                  compradores_72h=len(c), billeteras_A=len(a), billeteras_B=len(b),
                                  cortado="sí" if cortado else "no", mc_hoy=t["mc"], liq_hoy=t["liq"],
                                  lista_A=" ".join(x[:6] for x in a), lista_B=" ".join(x[:6] for x in b)))
                print(f"{t['sym'][:10]:10} {filas[-1]['creado']}  compradores {len(c):5}  A {len(a):3}  B {len(b):3}  ({pags} págs)", flush=True)
        v = fut.result()
    for f in filas:
        f.update({k: v.get(f["token"], {}).get(k, "") for k in ("multiplo", "dias_al_max", "hoy_vs_max")})
    with open("datos/tokens_anio_resultado.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]), delimiter="\t"); w.writeheader(); w.writerows(filas)
    # billeteras nuevas (ni A ni B) que aparecen entre los primeros compradores de 3 o más tokens
    nuevas = {w: v for w, v in todos.items() if len({x[0] for x in v}) >= 3}
    with open("datos/vector_C_nuevas.tsv", "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t"); w.writerow(["billetera", "n_tokens", "tokens"])
        for k, v in sorted(nuevas.items(), key=lambda kv: -len(kv[1])):
            w.writerow([k, len({x[0] for x in v}), " | ".join(f"{s} {time.strftime('%Y-%m-%d', time.gmtime(bt or 0))}" for _, s, bt in v)])
    print("listo:", len(filas), "| billeteras nuevas en 3+ tokens:", len(nuevas))


if __name__ == "__main__":
    main()
