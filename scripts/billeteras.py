"""Revisión de billeteras EVM (BNB y Robinhood) con Etherscan API v2. Solo lectura.
Entrada: datos/billeteras_revisar.tsv (cadena, direccion, etiqueta). Salida: datos/billeteras_etherscan.tsv.
La clave sale del secreto ETHERSCAN_API_KEY y nunca se imprime."""
import csv, json, os, sys, time, urllib.parse, urllib.request

KEY = os.environ.get("ETHERSCAN_API_KEY", "")
API = "https://api.etherscan.io/v2/api"
IN, OUT = "datos/billeteras_revisar.tsv", "datos/billeteras_etherscan.tsv"


def get(params):
    url = API + "?" + urllib.parse.urlencode({**params, "apikey": KEY})
    for _ in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "desk-scan"}), timeout=30) as r:
                d = json.load(r)
            if isinstance(d.get("result"), str) and "rate limit" in d["result"].lower():
                time.sleep(2); continue
            return d
        except Exception:
            time.sleep(3)
    return {}


RPC = {"bsc": ["https://bsc-dataseed.bnbchain.org", "https://bsc-dataseed1.defibit.io"]}


def rpcs_robinhood(cid):
    try:
        with urllib.request.urlopen(urllib.request.Request("https://chainid.network/chains.json", headers={"User-Agent": "desk-scan"}), timeout=30) as r:
            for c in json.load(r):
                if str(c.get("chainId")) == str(cid):
                    return [u for u in c.get("rpc", []) if u.startswith("https") and "${" not in u]
    except Exception:
        pass
    return []


def nonce_rpc(ch, a):
    """Transacciones enviadas por RPC pública (gratis, sin clave)."""
    for u in RPC.get(ch, []):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionCount", "params": [a, "latest"]}).encode()
            req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json", "User-Agent": "desk-scan"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return int(json.load(r)["result"], 16)
        except Exception:
            continue
    return None


def chain_ids():
    ids = {"bsc": "56"}
    try:
        with urllib.request.urlopen("https://api.etherscan.io/v2/chainlist", timeout=30) as r:
            for c in json.load(r).get("result", []):
                if "robinhood" in c.get("chainname", "").lower() and "test" not in c.get("chainname", "").lower():
                    ids["robinhood"] = str(c["chainid"])
    except Exception:
        pass
    return ids


if not KEY:
    sys.exit("Falta el secreto ETHERSCAN_API_KEY")
ids = chain_ids()
if "robinhood" in ids:
    RPC["robinhood"] = rpcs_robinhood(ids["robinhood"])
print("cadenas:", ids, "rpc:", {k: len(v) for k, v in RPC.items()})
rows = list(csv.DictReader(open(IN), delimiter="\t"))
out = []
for r in rows:
    ch, a = r["cadena"], r["direccion"].lower()
    res = dict(cadena=ch, direccion=a, etiqueta=r.get("etiqueta", ""), tx_enviadas="", primera_tx="", fondeo_desde="", nota="")
    cid = ids.get(ch)
    if not cid:
        res["nota"] = "cadena no disponible en Etherscan v2"; out.append(res); continue
    n = get(dict(chainid=cid, module="proxy", action="eth_getTransactionCount", address=a, tag="latest"))
    try: res["tx_enviadas"] = int(n.get("result", "0x0"), 16)
    except Exception:
        v = nonce_rpc(ch, a)
        if v is not None: res["tx_enviadas"] = v
        else: res["nota"] = "sin nonce: " + str(n.get("result", n.get("message", "")))[:60]
    time.sleep(0.3)
    t = get(dict(chainid=cid, module="account", action="txlist", address=a, startblock=0, endblock=99999999, page=1, offset=10, sort="asc"))
    txs = t.get("result") if isinstance(t.get("result"), list) else []
    if txs:
        res["primera_tx"] = time.strftime("%Y-%m-%d", time.gmtime(int(txs[0]["timeStamp"])))
        inc = [x for x in txs if x.get("to", "").lower() == a]
        if inc: res["fondeo_desde"] = inc[0]["from"].lower()
    elif not res["nota"]:
        m = str(t.get("result", t.get("message", "")))
        res["nota"] = "fondeo no disponible (plan gratis de Etherscan no cubre esta cadena)" if "upgrade" in m.lower() else m[:60]
    time.sleep(0.3)
    out.append(res)
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["cadena"], delimiter="\t")
    w.writeheader(); w.writerows(out)
print("revisadas", len(out))
