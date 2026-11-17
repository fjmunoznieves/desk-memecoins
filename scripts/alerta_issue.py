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

# 17-nov (Fran, caso GEKKO avisado 52 min tarde): cada candidato del escaneo abre un aviso al momento.
import glob as _glob, re as _re
_esc = sorted(_glob.glob("escaneos/escaneo_*.md"))
_hecho = "datos/candidatos_avisados.txt"
_ya = set(open(_hecho).read().split()) if _os.path.exists(_hecho) else set()
if _esc and _os.path.basename(_esc[-1]) not in _ya and _os.environ.get("GITHUB_REPOSITORY"):
    _sec = next((s for s in _re.split(r"\n## ", open(_esc[-1]).read()) if s.startswith("Candidatos")), "")
    _cands = _re.findall(r"\*\*(.+?)\*\* \((\w+)\) `([^`]+)`", _sec)
    if _cands:
        _body = ["Paper trading: solo aviso. Candidato = pasa filtros numéricos y seguridad; falta revisar señales de entrada.", ""]
        _body += [f"- **{s}** ({c}) `{t}` https://dexscreener.com/{c}/{t}" for s, c, t in _cands]
        subprocess.run(["gh", "issue", "create", "--repo", _os.environ["GITHUB_REPOSITORY"], "--title",
                        "Candidato del escaneo: " + ", ".join(s for s, c, t in _cands), "--body", "\n".join(_body)], check=False)
    with open(_hecho, "a") as _f:
        _f.write(_os.path.basename(_esc[-1]) + "\n")
    subprocess.run(["git", "add", _hecho], check=False)
