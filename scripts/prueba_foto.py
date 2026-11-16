"""Diagnóstico (manual): qué devuelve getTokenAccountsByOwner para una billetera. Solo lectura."""
import json, os, urllib.request
K = os.environ["HELIUS_API_KEY"].strip()
w, mint = "2EJPiGHWCddwUnoWoRHD3dfycjQwDV9iQceshn2HDpht", "AzeNfRi7DX5HndH7dUgCxMD5sQPV7FPFH1cwDkoqpump"
for prog in ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"]:
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner", "params": [w, {"programId": prog}, {"encoding": "jsonParsed"}]}
    r = json.load(urllib.request.urlopen(urllib.request.Request(f"https://mainnet.helius-rpc.com/?api-key={K}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}), timeout=40))
    v = (r.get("result") or {}).get("value") or []
    print(prog[:6], "cuentas", len(v), "error", r.get("error"), "keys", list((r.get("result") or {}).keys()))
    for a in v:
        inf = a["account"]["data"]["parsed"]["info"]
        if inf["mint"] == mint: print("  KNIGHT", inf["tokenAmount"])
    print("  ejemplo", [a["account"]["data"]["parsed"]["info"]["mint"][:8] for a in v[:5]])
