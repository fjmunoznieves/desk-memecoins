"""Prueba de la clave de Alchemy (solo lectura, sin imprimir la clave): Solana, BNB y Robinhood Chain."""
import json, os, urllib.request
K = os.environ.get("ALCHEMY_API_KEY", "").strip()
print("clave presente:", bool(K))
def rpc(host, m, p):
    try:
        req = urllib.request.Request(f"https://{host}.g.alchemy.com/v2/{K}", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        return "OK " + str(d.get("result", d.get("error")))[:160]
    except Exception as e:
        return "falla " + str(e)[:120]
W = "8s2MNRBtFBLAUWZJsk1YqeQxbsVAjbAA7xSUmLaN3bUu"
print("solana getSlot:", rpc("solana-mainnet", "getSlot", []))
print("solana firmas:", rpc("solana-mainnet", "getSignaturesForAddress", ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", {"limit": 2}]))
print("bnb bloque:", rpc("bnb-mainnet", "eth_blockNumber", []))
for h in ("robinhood-mainnet", "robinhoodchain-mainnet", "robinhood-chain-mainnet"):
    print(h, "bloque:", rpc(h, "eth_blockNumber", []))
