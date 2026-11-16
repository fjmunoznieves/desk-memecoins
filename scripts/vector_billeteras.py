#!/usr/bin/env python3
"""Vector de 1 año de nuestras 100 mejores billeteras (solo lectura, Helius).

Para cada billetera de datos/vector_billeteras_100.tsv pide sus transacciones de los últimos 365 días
(getTransactionsForAddress) y, por token, suma lo que gastó y recibió en SOL (nativo + wSOL), la primera compra
y el número de compras y ventas. Una transacción cuenta solo si mueve un único token aparte de SOL.
Entrada: BILLETERAS (tsv). Salida: SALIDA (billetera × token). Necesita HELIUS_API_KEY; la clave nunca se imprime.
"""
import csv, json, os, sys, time, urllib.request, urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

K = os.environ.get("HELIUS_API_KEY", "")
if not K:
    print("Falta HELIUS_API_KEY"); sys.exit(0)
RPC = f"https://mainnet.helius-rpc.com/?api-key={K}"
WSOL = "So11111111111111111111111111111111111111112"
# estables como moneda de pago (USDC, USDT, USD1, PYUSD): se suman en USD aparte de SOL
ESTABLES = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY2yoAFsTJ9Q9Pd2",
            "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB", "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo"}
DIAS = int(os.environ.get("DIAS") or 365)
MAX_PAG = int(os.environ.get("MAX_PAG") or 40)
HILOS = int(os.environ.get("HILOS") or 4)


def rpc(m, p):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for intento in range(6):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            if "error" in d:
                print("  error RPC:", str(d["error"])[:300], flush=True); return None
            return d.get("result")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                print("  HTTP", e.code, flush=True); return None
            time.sleep(1 + 2 * intento)
        except Exception:
            time.sleep(2)
    return None


def claves(tx):
    msg = (tx.get("transaction") or {}).get("message") or {}
    out = []
    for k in msg.get("accountKeys") or []:
        out.append(k["pubkey"] if isinstance(k, dict) else k)
    la = (tx.get("meta") or {}).get("loadedAddresses") or {}
    return out + (la.get("writable") or []) + (la.get("readonly") or [])


LLAMADAS = [0]
TOPE_TOTAL = int(os.environ.get("TOPE_CONSULTAS") or 10 ** 9)  # freno de créditos por corrida (100 c/u)
HASTA = {}  # modo profundo: billetera -> ts más antiguo ya leído (se pide solo lo anterior)


def procesar(fila):
    w, bot = fila
    desde = int(time.time()) - DIAS * 86400
    agg = defaultdict(lambda: {"sol_in": 0.0, "sol_out": 0.0, "usd_in": 0.0, "usd_out": 0.0, "compras": 0, "ventas": 0, "primera": None, "ultima": None})
    token, pags, ntx = None, 0, 0
    tope = 5 if bot else MAX_PAG  # los bots tienen miles de tx al día: solo una muestra
    while pags < tope and LLAMADAS[0] < TOPE_TOTAL:
        opts = {"transactionDetails": "full", "sortOrder": "desc", "limit": 100, "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 1,
                "filters": {"blockTime": {"gte": desde}, "status": "succeeded"}}
        if w in HASTA:
            opts["filters"]["blockTime"]["lt"] = HASTA[w]
        if token:
            opts["paginationToken"] = token
        r = rpc("getTransactionsForAddress", [w, opts])
        LLAMADAS[0] += 1
        if not r:
            break
        for tx in r.get("data") or []:
            ntx += 1
            meta = tx.get("meta") or {}
            ks = claves(tx)
            if w not in ks:
                continue
            i = ks.index(w)
            try:
                sol = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9
            except Exception:
                sol = 0.0
            pre = defaultdict(float); post = defaultdict(float)
            for b in meta.get("preTokenBalances") or []:
                if b.get("owner") == w:
                    pre[b["mint"]] += float(b["uiTokenAmount"].get("uiAmount") or 0)
            for b in meta.get("postTokenBalances") or []:
                if b.get("owner") == w:
                    post[b["mint"]] += float(b["uiTokenAmount"].get("uiAmount") or 0)
            deltas = {m: post[m] - pre[m] for m in set(pre) | set(post) if abs(post[m] - pre[m]) > 0}
            sol += deltas.pop(WSOL, 0.0)
            usd = sum(deltas.pop(e, 0.0) for e in ESTABLES)
            if len(deltas) != 1:
                continue
            (m, d), = deltas.items()
            a = agg[m]; bt = tx.get("blockTime")
            # pago en estables si se movieron ≥1 USD (el SOL restante es comisión); si no, pago en SOL
            if abs(usd) >= 1:
                if d > 0 and usd < 0:
                    a["usd_in"] += -usd; a["compras"] += 1
                    a["primera"] = bt if a["primera"] is None else min(a["primera"], bt)
                elif d < 0 and usd > 0:
                    a["usd_out"] += usd; a["ventas"] += 1
            elif abs(sol) >= 1e-4:
                if d > 0 and sol < 0:
                    a["sol_in"] += -sol; a["compras"] += 1
                    a["primera"] = bt if a["primera"] is None else min(a["primera"], bt)
                elif d < 0 and sol > 0:
                    a["sol_out"] += sol; a["ventas"] += 1
            a["ultima"] = bt if a["ultima"] is None else max(a["ultima"], bt)
        pags += 1
        if pags >= 10 and not agg:
            break  # 1.000 transacciones sin ninguna compra/venta de token: no es trader, no se gastan más créditos
        token = r.get("paginationToken")
        if not token:
            break
    return w, agg, pags, ntx, bool(token)


def main():
    ws = [(r["direccion"], r.get("bot") == "sí") for r in csv.DictReader(open(os.environ["BILLETERAS"]), delimiter="\t")]
    lote = os.environ.get("LOTE", "")  # "0-9" = filas 0 a 9 de la lista
    if lote:
        a, b = (int(x) for x in lote.split("-"))
        ws = ws[a:b + 1]
    if os.environ.get("PROFUNDO"):
        # 16-nov (Fran): historia completa del año, por partes. Solo se piden las transacciones anteriores a lo que
        # ya teníamos en vector_ops_A_289 / B_148 (y a lo ya bajado en lotes previos).
        for f in ("datos/vector_ops_A_289.tsv", "datos/vector_ops_B_148.tsv", os.environ["SALIDA"]):
            if os.path.exists(f):
                for r in csv.DictReader(open(f), delimiter="\t"):
                    for c in ("primera_compra", "ultima"):
                        if r.get(c):
                            HASTA[r["billetera"]] = min(HASTA.get(r["billetera"], 10 ** 12), int(r[c]))
    print(f"billeteras: {len(ws)}, {DIAS} días, máx {MAX_PAG} páginas", flush=True)
    filas = []
    with ThreadPoolExecutor(HILOS) as ex:
        for w, agg, pags, ntx, cortado in ex.map(procesar, ws):
            for m, a in agg.items():
                filas.append(dict(billetera=w, token=m, sol_in=round(a["sol_in"], 4), sol_out=round(a["sol_out"], 4),
                                  pnl_sol=round(a["sol_out"] - a["sol_in"], 4),
                                  usd_in=round(a["usd_in"], 2), usd_out=round(a["usd_out"], 2), pnl_usd=round(a["usd_out"] - a["usd_in"], 2), compras=a["compras"], ventas=a["ventas"],
                                  primera_compra=a["primera"] or "", ultima=a["ultima"] or "",
                                  historial_cortado="sí" if cortado else "no"))
            print(f"{w[:8]}  {ntx:5} tx  {len(agg):4} tokens  {pags} págs{'  (cortado)' if cortado else ''}", flush=True)
    modo_ag = os.environ.get("PROFUNDO") and os.path.exists(os.environ["SALIDA"])
    with open(os.environ["SALIDA"], "a" if modo_ag else "w", newline="") as f:
        campos = ["billetera", "token", "sol_in", "sol_out", "pnl_sol", "usd_in", "usd_out", "pnl_usd", "compras", "ventas",
                  "primera_compra", "ultima", "historial_cortado"]
        wr = csv.DictWriter(f, fieldnames=campos, delimiter="\t")
        if not modo_ag:
            wr.writeheader()
        wr.writerows(filas)
    print(f"consultas Helius aprox: {LLAMADAS[0]} (≈{LLAMADAS[0] * 100} créditos)")
    print(f"filas billetera×token: {len(filas)}; tokens distintos: {len({x['token'] for x in filas})}")


if __name__ == "__main__":
    main()
