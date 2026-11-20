import json, time, sys, urllib.request, collections
G = "https://api.geckoterminal.com/api/v2/"
PAUSA = [2.1]  # segundos entre consultas a GeckoTerminal; sube sola si nos frenan (429)


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 429:
                PAUSA[0] = min(PAUSA[0] + 1, 6)
                time.sleep(8 + 4 * k)
            else:
                time.sleep(3)
    return None

# Listas recortadas (nov-14) para gastar menos minutos: las de 6 h repetían casi todo lo de 1 h y 24 h.
lists = []
for net in ("solana", "bsc"):
    for dur in ("5m", "1h", "24h"):
        for p in (1, 2):
            lists.append((net, f"networks/{net}/trending_pools?duration={dur}&page={p}"))
    for p in range(1, 9 if net == "solana" else 5):
        lists.append((net, f"networks/{net}/new_pools?page={p}"))
    for p in range(1, 4 if net == "solana" else 3):
        lists.append((net, f"networks/{net}/pools?sort=h24_volume_usd_desc&page={p}"))

# Plan B (nov-15): si GeckoTerminal falla en una lista, se usa DexPaprika (gratis, sin clave).
# Sin clave solo ve pools creadas hace ≥1 h y una página de 100; se consulta máximo una vez por red y tipo.
DP = "https://api.dexpaprika.com/networks/{net}/pools/search?limit=100&created_after=-48h&order_by={orden}&sort=desc"
QUOTE = {"SOL", "WSOL", "USDC", "USDT", "WBNB", "BNB", "USD1", "ETH", "WETH", "BUSD", "FDUSD"}
dp_hecho = {}


def plan_b(net, path):
    orden = "created_at" if "new_pools" in path else "volume_usd_24h"
    if (net, orden) in dp_hecho:
        return []
    d = get(DP.format(net=net, orden=orden), tries=2) or {}
    dp_hecho[(net, orden)] = True
    out = []
    for pl in d.get("results") or []:
        for t in pl.get("tokens") or []:
            if (t.get("symbol") or "").upper() not in QUOTE and t.get("id"):
                out.append(t["id"])
                break
    print(f"plan B DexPaprika {net} {orden}: {len(out)} tokens", file=sys.stderr)
    return out


toks = collections.OrderedDict()
cov = collections.Counter()
for net, path in lists:
    d = get(G + path)
    time.sleep(PAUSA[0])
    if not d:
        cov["fail"] += 1
        for b in plan_b(net, path):
            cov["dexpaprika"] += 1
            toks.setdefault((net, b), "dexpaprika")
        continue
    for pl in d.get("data", []):
        b = pl["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
        cov[net] += 1
        toks.setdefault((net, b), path)
print("gecko entries", dict(cov), "unique", len(toks), file=sys.stderr)

# 18-nov (Fran: ver 500-1000 tokens por escaneo y medir el impulso). Jupiter Tokens API (gratis, sin clave): listas de tendencia,
# más operados, puntaje orgánico y recientes de Solana, con holders, cambio de holders, compradores netos/orgánicos por ventana.
JUP = {}
JUP_FALLOS = [0]
for path in ("toptrending/5m", "toptrending/1h", "toptrending/6h", "toptrending/24h", "toptraded/5m", "toptraded/1h", "toptraded/24h",
             "toporganicscore/5m", "toporganicscore/1h", "toporganicscore/24h", "recent"):
    d = None
    if JUP_FALLOS[0] >= 3:  # si Jupiter no responde, no se alarga el escaneo
        break
    for k in range(2):
        try:
            req = urllib.request.Request("https://lite-api.jup.ag/tokens/v2/" + path + ("?limit=100" if "top" in path else ""),
                                         headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=15)); break
        except Exception as e:
            time.sleep(6)
    JUP_FALLOS[0] = 0 if d else JUP_FALLOS[0] + 1
    time.sleep(2.5)
    for x in d or []:
        a = x.get("id")
        if a:
            JUP.setdefault(a, x)
            toks.setdefault(("solana", a), "jupiter_" + path)
print("jupiter unique", len(JUP), "universo total", len(toks), file=sys.stderr)

# DexScreener
chainmap = {"solana": "solana", "bsc": "bsc"}
best = {}
now = time.time() * 1000
bych = collections.defaultdict(list)
for (net, a) in toks:
    bych[chainmap[net]].append(a)
# Robinhood via DexScreener boosts/profiles + search
rh = set()
for u in ("https://api.dexscreener.com/token-profiles/latest/v1", "https://api.dexscreener.com/token-boosts/latest/v1", "https://api.dexscreener.com/token-boosts/top/v1"):
    d = get(u) or []
    for x in d:
        if x.get("chainId") == "robinhood":
            rh.add(x["tokenAddress"])
        elif x.get("chainId") == "solana" and ("solana", x.get("tokenAddress")) not in toks:  # 18-nov: también perfiles/boosts de Solana
            toks[("solana", x["tokenAddress"])] = "dexscreener_perfil"
            bych["solana"].append(x["tokenAddress"])
for q in ("robinhood", "HOOD", "WETH robinhood"):
    d = get("https://api.dexscreener.com/latest/dex/search?q=" + q) or {}
    for p in d.get("pairs", []) or []:
        if p.get("chainId") == "robinhood":
            rh.add(p["baseToken"]["address"])
bych["robinhood"] = list(rh)
print("robinhood", len(rh), file=sys.stderr)

for ch, addrs in bych.items():
    for i in range(0, len(addrs), 30):
        d = get(f"https://api.dexscreener.com/tokens/v1/{ch}/" + ",".join(addrs[i:i+30])) or []
        time.sleep(0.4)
        for p in d:
            a = p["baseToken"]["address"]
            key = (ch, a)
            liq = (p.get("liquidity") or {}).get("usd") or 0
            e = best.setdefault(key, {"pairs": [], "minCreated": 1e20})
            e["pairs"].append(p)
            if p.get("pairCreatedAt"):
                e["minCreated"] = min(e["minCreated"], p["pairCreatedAt"])
            if "p" not in e or liq > ((e["p"].get("liquidity") or {}).get("usd") or 0):
                e["p"] = p

def jup_campos(a):
    x = JUP.get(a)
    if not x:
        return {}
    s1, s5 = x.get("stats1h") or {}, x.get("stats5m") or {}
    return dict(holders=x.get("holderCount"), hold_chg1h=s1.get("holderChange"), hold_chg5m=s5.get("holderChange"),
                netos1h=s1.get("numNetBuyers"), organicos1h=s1.get("numOrganicBuyers"), traders1h=s1.get("numTraders"),
                organic_score=x.get("organicScore"), top_holders=(x.get("audit") or {}).get("topHoldersPercentage"))


BASEQ = {"SOL", "WSOL", "USDC", "USDT", "WBNB", "BNB", "USD1", "ETH", "WETH", "BUSD", "FDUSD"}
rows = []
for (ch, a), e in best.items():
    p = e["p"]
    age_h = (now - e["minCreated"]) / 3.6e6 if e["minCreated"] < 1e20 else None
    tx = (p.get("txns") or {}).get("m5") or {}
    b, s = tx.get("buys", 0), tx.get("sells", 0)
    pc = p.get("priceChange") or {}
    info = p.get("info") or {}
    socials = [x.get("type") for x in info.get("socials", [])] + (["web"] if info.get("websites") else [])
    src = toks.get((ch, a), "")
    rows.append(dict(chain=ch, addr=a, sym=p["baseToken"]["symbol"], name=p["baseToken"].get("name", ""),
                     trending=("trending_pools" in src), src_dur=(src.split("duration=")[1].split("&")[0] if "duration=" in src else ""), dex=p.get("dexId"), quote=p["quoteToken"]["symbol"],
                     age_h=age_h, liq=(p.get("liquidity") or {}).get("usd") or 0, mc=p.get("marketCap") or p.get("fdv") or 0,
                     v5=(p.get("volume") or {}).get("m5") or 0, v1h=(p.get("volume") or {}).get("h1") or 0,
                     b=b, s=s, c5=pc.get("m5") or 0, c1=pc.get("h1") or 0, c24=pc.get("h24") or 0,
                     socials=socials, boosts=(p.get("boosts") or {}).get("active", 0), price=p.get("priceUsd"), pair=p.get("pairAddress"),
                     src=src, **jup_campos(a)))
# 20-nov (Fran aprobó, arreglo de medición, caso RIEMANN FMWYmS…): DexScreener a veces devuelve el pool sin precio ni
# liquidez (616 filas del universo, 6 %, quedaban con MC 0 y se rechazaban sin evaluar). Se completan con GeckoTerminal
# (pool de mayor reserva del token) antes de los filtros. No cambia ninguna regla. Tope 80 tokens / 180 s.
GTNET = {"solana": "solana", "bsc": "bsc"}
vacios = [r for r in rows if r["chain"] in GTNET and (not r.get("price") or not r.get("liq") or not r.get("mc"))]
t_ini, rell = time.time(), 0
for r in vacios[:80]:
    if time.time() - t_ini > 180:
        break
    d = get(G + f"networks/{GTNET[r['chain']]}/tokens/{r['addr']}/pools?page=1") or {}
    time.sleep(PAUSA[0])
    pools = d.get("data") or []
    if not pools:
        continue
    a = max(pools, key=lambda x: float((x.get("attributes") or {}).get("reserve_in_usd") or 0))["attributes"]
    if not a.get("base_token_price_usd") or not float(a.get("reserve_in_usd") or 0):
        continue
    vol, tx, pc = a.get("volume_usd") or {}, (a.get("transactions") or {}).get("m5") or {}, a.get("price_change_percentage") or {}
    f = lambda x: float(x) if x not in (None, "") else 0
    r.update(price=a.get("base_token_price_usd"), liq=f(a.get("reserve_in_usd")), mc=f(a.get("market_cap_usd")) or f(a.get("fdv_usd")),
             v5=f(vol.get("m5")), v1h=f(vol.get("h1")), b=tx.get("buys", 0), s=tx.get("sells", 0),
             c5=f(pc.get("m5")), c1=f(pc.get("h1")), c24=f(pc.get("h24")), pair=a.get("address"), src=r["src"] + "|gt_relleno")
    if r.get("age_h") is None and a.get("pool_created_at"):
        import datetime as _dt
        r["age_h"] = (now / 1000 - _dt.datetime.fromisoformat(a["pool_created_at"].replace("Z", "+00:00")).timestamp()) / 3600
    rell += 1
print(f"relleno GeckoTerminal: {rell} de {len(vacios)} tokens sin precio/liquidez en DexScreener", file=sys.stderr)
json.dump(rows, open("rows.json", "w"))
print("rows", len(rows), file=sys.stderr)
