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
