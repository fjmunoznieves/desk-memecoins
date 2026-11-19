#!/usr/bin/env python3
"""Crea o actualiza el webhook de Helius (enhanced, SWAP) que avisa al Worker de Cloudflare cuando una de las
billeteras de datos/rt_billeteras.txt opera. 19-nov (Fran): vigilancia en tiempo real para H34.
Costo: 100 créditos por crear/editar + 1 crédito por aviso. Solo lectura de la cadena; la clave nunca se imprime.
Entradas por entorno: HELIUS_API_KEY, WEBHOOK_URL, WEBHOOK_AUTH."""
import json, os, sys, urllib.request

K = os.environ.get("HELIUS_API_KEY", ""); URL = os.environ.get("WEBHOOK_URL", ""); AUTH = os.environ.get("WEBHOOK_AUTH", "")
if not (K and URL and AUTH):
    print("faltan variables"); sys.exit(1)
BASE = "https://api.helius.xyz/v0/webhooks"


def pedir(metodo, ruta="", cuerpo=None):
    req = urllib.request.Request(f"{BASE}{ruta}?api-key={K}", method=metodo,
                                 data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "desk-tiempo-real/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("Helius respondió", e.code, e.read()[:300].decode(errors="ignore").replace(K, "***")); sys.exit(1)


dirs = [x.strip() for x in open("datos/rt_billeteras.txt") if x.strip()]
cuerpo = {"webhookURL": URL, "transactionTypes": ["SWAP"], "accountAddresses": dirs, "webhookType": "enhanced", "authHeader": AUTH}
existentes = pedir("GET") or []
mio = [w for w in existentes if w.get("webhookURL", "").rstrip("/") == URL.rstrip("/")]
if mio:
    w = mio[0]
    if sorted(w.get("accountAddresses", [])) == sorted(dirs) and w.get("transactionTypes") == ["SWAP"]:
        print(f"webhook ya existe con las mismas {len(dirs)} billeteras; no se edita (ahorra 100 créditos)")
    else:
        pedir("PUT", "/" + w["webhookID"], cuerpo); print(f"webhook actualizado: {len(dirs)} billeteras")
else:
    r = pedir("POST", "", cuerpo); print(f"webhook creado ({r.get('webhookID', '?')[:8]}…): {len(dirs)} billeteras; webhooks en la cuenta: {len(existentes) + 1}")
