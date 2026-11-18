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

# 18-nov (Fran, caso :3 avisado 3 h tarde y luego x3,9): H21 con 2+ operadores en token maduro abre aviso al momento. Solo aviso.
import csv as _csv
_h21, _h21ya = "datos/h21_consenso.tsv", "datos/h21_avisados.txt"
if _os.path.exists(_h21) and _os.environ.get("GITHUB_REPOSITORY"):
    _ya21 = set(open(_h21ya).read().split()) if _os.path.exists(_h21ya) else set()
    _nuevos = [r for r in _csv.DictReader(open(_h21), delimiter="\t")
               if (r["token"] + "@" + r["ts"]) not in _ya21 and float(r.get("n_oper") or r.get("n") or 0) >= 2 and float(r.get("edad_d") or 0) >= 7]
    for r in _nuevos:
        _b = ["Paper trading: solo aviso. H21 = 2+ operadores de la watchlist compran un token maduro (≥7 d).", "",
              f"- **{r['sym']}** (solana) `{r['token']}` https://dexscreener.com/solana/{r['token']}",
              f"- Operadores: {r.get('n_oper')} · edad {r['edad_d']} d · precio {r['precio']} · MC {r['mc']} · liq {r['liq']} ({r['hora_utc']} UTC)",
              "- Billeteras: " + ", ".join("`" + b + "`" for b in r["billeteras"].split(","))]
        subprocess.run(["gh", "issue", "create", "--repo", _os.environ["GITHUB_REPOSITORY"], "--title",
                        f"H21 consenso maduro: {r['sym']} ({r.get('n_oper')} operadores)", "--body", "\n".join(_b)], check=False)
    if _nuevos:
        with open(_h21ya, "a") as _f:
            _f.write("".join(r["token"] + "@" + r["ts"] + "\n" for r in _nuevos))
        subprocess.run(["git", "add", _h21ya], check=False)
