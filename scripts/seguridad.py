"""Revisión de seguridad 5.2 para las tres cadenas del desk (solana, bsc, robinhood).

- solana: RugCheck (top10, LP bloqueada, mint/freeze).
- bsc y robinhood: GeckoTerminal token info (holders, top10, honeypot). RugCheck solo cubre Solana.
  Impuestos y renuncia de contrato en BNB siguen saliendo de GMGN token_detail (Firecrawl), paso manual.

Uso como módulo:  from seguridad import revisar; fallos, datos = revisar("robinhood", "0x...")
Uso directo:      python3 seguridad.py <cadena> <direccion>
Devuelve una lista de fallos (vacía = pasa). "seg?" significa que la fuente no dio datos: no se da por bueno.
"""
import json, sys, time, urllib.request

TOP10_MAX = 25.0
HOLDERS_MIN = 300
LP_MIN = 90


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(30 if getattr(e, "code", None) == 429 else 3)
    return None


def _solana(addr):
    rc = get(f"https://api.rugcheck.xyz/v1/tokens/{addr}/report") or {}
    if not rc:
        return ["seg?"], {"fuente": "rugcheck", "error": "sin datos"}
    f = []
    th = rc.get("topHolders") or []
    top10 = sum(h.get("pct", 0) for h in th[:10])
    if top10 > TOP10_MAX: f.append("top10")
    lp = [(m.get("lp") or {}).get("lpLockedPct") or 0 for m in rc.get("markets") or []]
    if lp and max(lp) < LP_MIN: f.append("lp")
    if rc.get("mintAuthority") or rc.get("freezeAuthority"): f.append("mint/freeze")
    holders = rc.get("totalHolders")  # solo informativo en Solana: no cambia las reglas que ya usaba sombra.py
    return f, {"fuente": "rugcheck", "top10": round(top10, 2), "lp_max": max(lp) if lp else None, "holders": holders}


def _evm(chain, addr):
    d = get(f"https://api.geckoterminal.com/api/v2/networks/{chain}/tokens/{addr}/info") or {}
    a = (d.get("data") or {}).get("attributes") or {}
    h = a.get("holders") or {}
    dist = h.get("distribution_percentage") or {}
    top10 = float(dist["top_10"]) if dist.get("top_10") else None
    count = h.get("count")
    hp = a.get("is_honeypot")
    f = []
    if top10 is None: f.append("seg?")
    elif top10 > TOP10_MAX: f.append("top10")
    if count is not None and count < HOLDERS_MIN: f.append("holders")
    if hp is True: f.append("honeypot")
    return f, {"fuente": "geckoterminal", "top10": top10, "holders": count, "honeypot": hp, "gt_score": a.get("gt_score")}


def revisar(chain, addr):
    if chain == "solana":
        return _solana(addr)
    if chain in ("bsc", "robinhood"):
        return _evm(chain, addr)
    return ["seg?"], {"error": f"cadena no soportada: {chain}"}


if __name__ == "__main__":
    f, info = revisar(sys.argv[1], sys.argv[2])
    print(json.dumps({"fallos": f, **info}, ensure_ascii=False))
