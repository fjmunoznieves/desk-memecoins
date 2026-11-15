#!/usr/bin/env python3
"""Backtest H21 (solo lectura): ¿nuestras billeteras entraron juntas en tokens maduros ANTES de que revivieran?

Para cada token de datos/h21_backtest_tokens.tsv y cada billetera (watchlist + top), calcula la cuenta de token
asociada (ATA, programa Token y Token-2022) y pide a Helius su historial de firmas. La primera firma = primera
entrada de esa billetera en ese token. Compara entradas en los 7 días antes del arranque con el periodo muerto
(30 a 7 días antes) como control. Necesita HELIUS_API_KEY (GitHub Secret); la clave nunca se imprime.
"""
import csv, json, os, sys, time, datetime as dt, urllib.request
from solders.pubkey import Pubkey

K = os.environ.get("HELIUS_API_KEY", "")
if not K:
    print("Falta HELIUS_API_KEY"); sys.exit(0)
RPC = f"https://mainnet.helius-rpc.com/?api-key={K}"
ATA_PROG = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
PROGS = [Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
         Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")]
DIA = 86400


def rpc_batch(calls):
    """calls: lista de (method, params). Devuelve lista de result (o None)."""
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]).encode()
    for intento in range(5):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.load(r)
            res = [None] * len(calls)
            for o in out:
                res[o["id"]] = o.get("result")
            return res
        except Exception as e:  # 429 u otros: espera y reintenta (sin imprimir la URL)
            time.sleep(3 + 4 * intento)
    return [None] * len(calls)


def ata(owner, mint, prog):
    return str(Pubkey.find_program_address([bytes(owner), bytes(prog), bytes(mint)], ATA_PROG)[0])


def billeteras():
    out = {}
    for f, col_dir, col_nom in (("datos/watchlist_solana.tsv", "direccion", "nota"),
                                ("datos/billeteras_top_lista.tsv", "direccion", "nombre")):
        for r in csv.DictReader(open(f), delimiter="\t"):
            d = (r.get(col_dir) or "").strip()
            if not d or d.startswith("0x"):
                continue
            try:
                Pubkey.from_string(d)
            except Exception:
                continue
            etiqueta = "watchlist" if "watchlist" in f else (r.get("tipo") or "top")
            out.setdefault(d, ((r.get(col_nom) or "")[:20], etiqueta))
    return out


def main():
    ws = billeteras()
    print(f"billeteras: {len(ws)}")
    toks = list(csv.DictReader(open("datos/h21_backtest_tokens.tsv"), delimiter="\t"))
    filas, resumen = [], []
    for t in toks:
        mint = Pubkey.from_string(t["token"])
        t0 = int(dt.datetime.strptime(t["arranque"], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
        pares = [(w, ata(Pubkey.from_string(w), mint, p)) for w in ws for p in PROGS]
        primeras = {}
        for i in range(0, len(pares), 100):
            lote = pares[i:i + 100]
            res = rpc_batch([("getSignaturesForAddress", [a, {"limit": 1000}]) for _, a in lote])
            for (w, a), r in zip(lote, res):
                if not r:
                    continue
                bt = min((s.get("blockTime") or 9e12) for s in r)
                if len(r) == 1000:  # historial largo: la primera real es aún más antigua
                    bt = min(bt, t0 - 400 * DIA)
                primeras[w] = min(primeras.get(w, 9e12), bt)
            time.sleep(0.3)
        antes7 = sorted((bt, w) for w, bt in primeras.items() if t0 - 7 * DIA <= bt < t0)
        muerto = [w for w, bt in primeras.items() if t0 - 30 * DIA <= bt < t0 - 7 * DIA]
        dia0 = [w for w, bt in primeras.items() if t0 <= bt < t0 + DIA]
        # consenso: máximo de billeteras distintas que entran dentro de 24 h, en los 7 días previos
        cons = 0
        for j, (bt, _) in enumerate(antes7):
            cons = max(cons, sum(1 for b, _ in antes7[j:] if b < bt + DIA))
        wl = [w for _, w in antes7 if ws[w][1] == "watchlist"]
        resumen.append(dict(sym=t["sym"], token=t["token"], arranque=t["arranque"], subida_x=t["subida_x"],
                            edad_d=t["edad_d"], alguna_vez=len(primeras), muerto_23d=len(muerto),
                            antes_7d=len(antes7), consenso_24h=cons, dia_arranque=len(dia0), watchlist_antes=len(wl)))
        for bt, w in antes7:
            filas.append(dict(sym=t["sym"], token=t["token"], billetera=w, nombre=ws[w][0], tipo=ws[w][1],
                              entrada_utc=dt.datetime.fromtimestamp(bt, dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                              horas_antes=round((t0 - bt) / 3600, 1)))
        r = resumen[-1]
        print(f"{r['sym']:10} {r['arranque']} x{r['subida_x']:>5}  alguna vez {r['alguna_vez']:3}  "
              f"muerto(-30..-7d) {r['muerto_23d']:3}  antes(-7..0d) {r['antes_7d']:3}  consenso24h {r['consenso_24h']:2}  "
              f"día0 {r['dia_arranque']:3}  watchlist {r['watchlist_antes']}")

    for nombre, datos in (("datos/h21_backtest_resumen.tsv", resumen), ("datos/h21_backtest_entradas.tsv", filas)):
        if datos:
            with open(nombre, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(datos[0]), delimiter="\t")
                w.writeheader(); w.writerows(datos)
    # tasa diaria: 7 días previos vs periodo muerto (23 días)
    a = sum(r["antes_7d"] for r in resumen) / 7
    m = sum(r["muerto_23d"] for r in resumen) / 23
    c2 = sum(1 for r in resumen if r["consenso_24h"] >= 2)
    print(f"\nentradas/día: antes {a:.2f} vs muerto {m:.2f} (lift {a / m if m else float('inf'):.1f}x); "
          f"tokens con consenso ≥2 en 24 h antes del arranque: {c2}/{len(resumen)}")


if __name__ == "__main__":
    main()
