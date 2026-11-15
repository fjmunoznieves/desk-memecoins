#!/usr/bin/env python3
"""Mina billeteras con Helius (solo lectura): quién compró en los 3 días ANTES de cada resurrección (180 días).

Para cada resurrección de Solana (datos/h21_resurrecciones.json) pide las transacciones del pool en la ventana
[arranque - 3 d, arranque) con getTransactionsForAddress y marca como comprador a cada dueño cuyo saldo del token
sube. Guarda las billeteras que compraron antes de 2 o más resurrecciones distintas y descarta bots
(≥1000 firmas en menos de 1 día). Necesita HELIUS_API_KEY; la clave nunca se imprime.
"""
import csv, json, os, sys, time, datetime as dt, urllib.request, urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

K = os.environ.get("HELIUS_API_KEY", "")
if not K:
    print("Falta HELIUS_API_KEY"); sys.exit(0)
RPC = f"https://mainnet.helius-rpc.com/?api-key={K}"
DIA = 86400
VENTANA = int(os.environ.get("VENTANA_D") or 3) * DIA
MAX_PAG = int(os.environ.get("MAX_PAG") or 30)


def rpc(m, p):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for intento in range(5):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            if "error" in d:
                print("  error RPC:", str(d["error"])[:160], flush=True); return None
            return d.get("result")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                print("  HTTP", e.code, flush=True); return None
            time.sleep(1 + 2 * intento)
        except Exception:
            time.sleep(2)
    return None


def compradores(pool, mint, t0):
    """Dueños cuyo saldo de `mint` sube en la ventana previa al arranque, con su primera hora de compra."""
    out, token, pags = {}, None, 0
    while pags < MAX_PAG:
        opts = {"transactionDetails": "full", "sortOrder": "asc", "limit": 100, "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "filters": {"blockTime": {"gte": t0 - VENTANA, "lt": t0}, "status": "succeeded"}}
        if token:
            opts["paginationToken"] = token
        r = rpc("getTransactionsForAddress", [pool, opts])
        if not r:
            break
        for tx in r.get("data") or []:
            meta = tx.get("meta") or {}
            pre = {(b.get("owner"), b.get("mint")): float(b["uiTokenAmount"].get("uiAmount") or 0)
                   for b in meta.get("preTokenBalances") or []}
            for b in meta.get("postTokenBalances") or []:
                if b.get("mint") != mint or not b.get("owner"):
                    continue
                k = (b["owner"], mint)
                if float(b["uiTokenAmount"].get("uiAmount") or 0) > pre.get(k, 0):
                    out.setdefault(b["owner"], tx.get("blockTime"))
        pags += 1
        token = r.get("paginationToken")
        if not token:
            break
    return out, pags


def main():
    res = [r for r in json.load(open("datos/h21_resurrecciones.json")) if r["net"] == "solana"]
    print(f"resurrecciones Solana: {len(res)}", flush=True)
    vistos = defaultdict(list)  # billetera -> [(sym, inicio, horas_antes)]
    for r in res:
        t0 = int(dt.datetime.strptime(r["inicio"], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
        c, pags = compradores(r["pool"], r["token"], t0)
        # el pool y sus bóvedas aparecen como "dueños": se descarta el propio pool
        c.pop(r["pool"], None)
        for w, bt in c.items():
            vistos[w].append((r["sym"], r["inicio"], round((t0 - (bt or t0)) / 3600, 1)))
        print(f"{r['sym']:10} {r['inicio']}  compradores previos {len(c):4}  ({pags} páginas)", flush=True)

    # billeteras en 2+ resurrecciones distintas (por token)
    rep = {w: v for w, v in vistos.items() if len({s for s, _, _ in v}) >= 2}
    print(f"\nbilleteras únicas: {len(vistos)}; en 2+ resurrecciones: {len(rep)}", flush=True)

    def es_bot(w):
        s = rpc("getSignaturesForAddress", [w, {"limit": 1000}]) or []
        if len(s) < 1000:
            return False, len(s)
        span = (s[0].get("blockTime") or 0) - (s[-1].get("blockTime") or 0)
        return span < DIA, len(s)

    with ThreadPoolExecutor(6) as ex:
        marcas = dict(zip(rep, ex.map(es_bot, rep)))
    filas = []
    for w, v in sorted(rep.items(), key=lambda kv: -len({s for s, _, _ in kv[1]})):
        bot, nfirmas = marcas[w]
        filas.append(dict(billetera=w, n_tokens=len({s for s, _, _ in v}), bot="sí" if bot else "no",
                          firmas_recientes=nfirmas, tokens=" | ".join(f"{s} {i} ({h} h antes)" for s, i, h in v)))
    with open("datos/h21_billeteras_180d.tsv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["billetera", "n_tokens", "bot", "firmas_recientes", "tokens"], delimiter="\t")
        wr.writeheader(); wr.writerows(filas)
    limpias = [x for x in filas if x["bot"] == "no"]
    print(f"limpias (no bot): {len(limpias)}; top 15:")
    for x in limpias[:15]:
        print(f"  {x['billetera']}  {x['n_tokens']} tokens  {x['tokens'][:150]}")


if __name__ == "__main__":
    main()
