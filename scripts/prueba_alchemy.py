"""Prueba de la clave de Alchemy (solo lectura, sin imprimir la clave): Solana, BNB y Robinhood Chain."""
import json, os, urllib.request
K = os.environ.get("ALCHEMY_API_KEY", "").strip()
print("clave presente:", bool(K))
def rpc(host, m, p):
    try:
        req = urllib.request.Request(f"https://{host}.g.alchemy.com/v2/{K}", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        return "OK " + str(d.get("result", d.get("error")))[:100000]
    except Exception as e:
        return "falla " + str(e)[:120]
W = "9dJKzPJQVoSLQ3ujdzUpUw3o2Ef2kTJLTgbLWnCMMD3i"
print("solana getSlot:", rpc("solana-mainnet", "getSlot", []))
r = rpc("solana-mainnet", "getSignaturesForAddress", [W, {"limit": 1000}])
print("solana firmas billetera A:", r[:120])
import re
sig = re.search(r"'signature': '([^']+)'", r)
if sig:
    print("solana tx:", rpc("solana-mainnet", "getTransaction", [sig.group(1), {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])[:100])
print("bnb bloque:", rpc("bnb-mainnet", "eth_blockNumber", []))
print("robinhood bloque:", rpc("robinhood-mainnet", "eth_blockNumber", []))
