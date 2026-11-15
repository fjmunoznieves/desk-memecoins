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
                     socials=socials, boosts=(p.get("boosts") or {}).get("active", 0), price=p.get("priceUsd"), pair=p.get("pairAddress")))
json.dump(rows, open("rows.json", "w"))
print("rows", len(rows), file=sys.stderr)
