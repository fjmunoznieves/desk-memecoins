"""Convierte datos/alertas_pendientes.json en un aviso (issue) de GitHub con el CLI gh."""
import json, subprocess
for a in json.load(open("datos/alertas_pendientes.json")):
    t = a["token"]
    body = ["Paper trading: solo aviso, no es orden de compra. Revisar filtros 5.x, seguridad y señales antes de cualquier entrada simulada.", "",
            f"- Token (Solana): `{t}`", f"- DexScreener: https://dexscreener.com/solana/{t}", f"- GMGN: https://gmgn.ai/sol/token/{t}", "", "Billeteras de la watchlist que compraron:"]
    body += [f"- `{w['b']}` a las {w['hora']} UTC ({w['sol']} SOL)" for w in a["billeteras"]]
    subprocess.run(["gh", "issue", "create", "--title", f"Watchlist: {len(a['billeteras'])} billeteras compraron {t[:6]}…{t[-4:]}", "--body", "\n".join(body)], check=False)

# H21 (nov-15): consenso de la watchlist en tokens maduros. Corre aquí para no tocar los horarios.
subprocess.run(["python3", "scripts/h21.py"], check=False)

# Vigilancia de posiciones abiertas de A (16-nov, caso BLOB): avisa si sube un token que nuestras A aún sostienen.
subprocess.run(["python3", "scripts/vigila_sostenidas.py"], check=False)

# Consenso A en vivo (16-nov): abre el aviso de lo que dejó consenso_A.py.
subprocess.run(["python3", "scripts/consenso_A.py"], check=False)

# CONTROL de la foto de cartera (16-nov, Fran): si no coincide con las fotos de saldos, abre aviso.
import os as _os, json as _json
if _os.path.exists("datos/control_cartera_falla.json") and _os.environ.get("GITHUB_REPOSITORY"):
    f = _json.load(open("datos/control_cartera_falla.json"))
    r = subprocess.run(["gh", "issue", "create", "--repo", _os.environ["GITHUB_REPOSITORY"], "--title", "CONTROL: la foto de cartera no coincide con las fotos de saldos",
                        "--body", "\n".join(f"- {x['lista']}: {x['coinciden']} de {x['total']} posiciones coinciden" for x in f) + "\n\nRevisar watch_solana.py (modo CARTERA) antes de confiar en consenso A, H22 y H23."], check=False)
    if r.returncode == 0:
        _os.remove("datos/control_cartera_falla.json")
