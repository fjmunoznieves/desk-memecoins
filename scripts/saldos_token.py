#!/usr/bin/env python3
"""Saldo actual de un token en varias billeteras (Helius RPC, solo lectura). La clave nunca se imprime."""
import json, os, sys, urllib.request
K = os.environ.get("HELIUS_API_KEY", "")
RPC = f"https://mainnet.helius-rpc.com/?api-key={K}"
mint = os.environ["MINT"]; ws = os.environ["BILLETERAS"].split()
def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("result")
sup = float((rpc("getTokenSupply", [mint]) or {}).get("value", {}).get("uiAmount") or 0)
for w in ws:
    try:
        r = rpc("getTokenAccountsByOwner", [w, {"mint": mint}, {"encoding": "jsonParsed"}]) or {}
        amt = sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0) for a in r.get("value", []))
        print(f"{w}\t{amt:,.0f}\t{(amt / sup * 100 if sup else 0):.3f}% del suministro")
    except Exception as e:
        print(w, "error", type(e).__name__)
