"""Revisión de seguridad 5.2 para las tres cadenas del desk (solana, bsc, robinhood).

- solana: RugCheck (top10, LP bloqueada, mint/freeze).
- bsc y robinhood: GeckoTerminal token info (holders, top10, honeypot). RugCheck solo cubre Solana.
  En BNB, además, GoPlus (gratis, sin clave): impuestos <5 %, contrato renunciado, no honeypot, dev ≤5 %, LP bloqueada ≥90 %.

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


GP_CHAIN = {"bsc": "56"}  # GoPlus no cubre Robinhood Chain
TAX_MAX = 0.05
DEV_MAX = 0.05
CERO = ("", "0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dead")


def _goplus(chain, addr):
    """GoPlus Security (API pública, sin clave): impuestos, renuncia, honeypot, dev y LP bloqueada en BNB."""
    if chain not in GP_CHAIN:
        return [], {}
    d = get(f"https://api.gopluslabs.io/api/v1/token_security/{GP_CHAIN[chain]}?contract_addresses={addr}") or {}
    r = (d.get("result") or {}).get(addr.lower())
    if not r:
        return ["impuestos?"], {"goplus": "sin datos"}
    num = lambda k: float(r.get(k) or 0) if str(r.get(k) or "").replace(".", "", 1).isdigit() else None
    bt, st, dev = num("buy_tax"), num("sell_tax"), num("creator_percent")
    f = []
    if bt is None or st is None: f.append("impuestos?")
    elif max(bt, st) >= TAX_MAX: f.append("impuestos")
    if r.get("is_honeypot") == "1" or r.get("cannot_sell_all") == "1": f.append("honeypot")
    if (r.get("owner_address") or "").lower() not in CERO or r.get("can_take_back_ownership") == "1": f.append("no renunciado")
    if dev is not None and dev > DEV_MAX: f.append("dev")
    lp = sum(float(h.get("percent") or 0) for h in r.get("lp_holders") or [] if h.get("is_locked") == 1 or (h.get("address") or "").lower() in CERO)
    if r.get("lp_holders") and lp < 0.9: f.append("lp")
    return f, {"goplus": {"buy_tax": bt, "sell_tax": st, "dev": dev, "lp_bloq": round(lp * 100, 1), "owner": r.get("owner_address"), "open_source": r.get("is_open_source")}}


def revisar(chain, addr):
    if chain == "solana":
        return _solana(addr)
    if chain in ("bsc", "robinhood"):
        f, info = _evm(chain, addr)
        gf, ginfo = _goplus(chain, addr)
        return f + [x for x in gf if x not in f], {**info, **ginfo}
    return ["seg?"], {"error": f"cadena no soportada: {chain}"}


if __name__ == "__main__":
    f, info = revisar(sys.argv[1], sys.argv[2])
    print(json.dumps({"fallos": f, **info}, ensure_ascii=False))
