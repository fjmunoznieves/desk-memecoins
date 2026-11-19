#!/usr/bin/env python3
"""Crea (o reutiliza) el webhook de Alchemy Address Activity en Solana para las 227 A (datos/watchlist_A_oper.tsv) y deja su
signing key en un archivo para pasarla como secreto al Worker. 19-nov (Fran). Solo lectura de la cadena, paper.
Entradas: ALCHEMY_NOTIFY_TOKEN, WEBHOOK_URL (…/alchemy), SALIDA (archivo donde escribir la signing key). Nada secreto se imprime."""
import csv, json, os, sys, urllib.request, urllib.error

T = os.environ.get("ALCHEMY_NOTIFY_TOKEN", ""); URL = os.environ.get("WEBHOOK_URL", ""); SAL = os.environ.get("SALIDA", "")
if not (T and URL and SAL):
    print("faltan variables"); sys.exit(1)
API = "https://dashboard.alchemy.com/api"


def pedir(metodo, ruta, cuerpo=None):
    req = urllib.request.Request(API + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"X-Alchemy-Token": T, "Content-Type": "application/json", "User-Agent": "desk-tiempo-real/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("Alchemy respondió", e.code, e.read()[:400].decode(errors="ignore")); sys.exit(1)


dirs = sorted({r["direccion"] for r in csv.DictReader(open("datos/watchlist_A_oper.tsv"), delimiter="\t")})
lista = (pedir("GET", "/team-webhooks") or {}).get("data", [])
mio = [w for w in lista if w.get("webhook_url") == URL]
if mio:
    w = mio[0]
    print(f"webhook Alchemy ya existe ({w.get('network')}, activo={w.get('is_active')}); se actualizan direcciones")
    pedir("PATCH", "/update-webhook-addresses", {"webhook_id": w["id"], "addresses_to_add": dirs, "addresses_to_remove": []})
else:
    for red in ("SOLANA_MAINNET", "SOL_MAINNET"):
        try:
            req = urllib.request.Request(API + "/create-webhook", method="POST",
                                         data=json.dumps({"network": red, "webhook_type": "ADDRESS_ACTIVITY", "webhook_url": URL,
                                                          "name": "desk-h34-227", "addresses": dirs}).encode(),
                                         headers={"X-Alchemy-Token": T, "Content-Type": "application/json", "User-Agent": "desk-tiempo-real/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                w = json.load(r).get("data", {}); break
        except urllib.error.HTTPError as e:
            print(f"red {red}: Alchemy respondió", e.code, e.read()[:300].decode(errors="ignore")); w = None
    if not w:
        sys.exit(1)
    print(f"webhook Alchemy creado ({w.get('network')}): {len(dirs)} direcciones")
k = w.get("signing_key") or ""
if not k:
    print("Alchemy no devolvió signing_key (se conserva la que tiene el Worker)"); sys.exit(0)
open(SAL, "w").write(k)
