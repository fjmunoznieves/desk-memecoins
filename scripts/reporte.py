"""Informe de un escaneo: lee rows2.json, revisa seguridad de los que pasan numéricos y escribe escaneos/escaneo_<fecha>.md.
Solo registro y paper trading: no opera ni toca billeteras."""
import json, collections, time, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seguridad import revisar

R = json.load(open("rows2.json"))
now = time.gmtime()
stamp = time.strftime("%Y-%m-%d_%H%M", now)
DS = {"solana": "solana", "bsc": "bsc", "robinhood": "robinhood"}
L = [f"# Escaneo automático: {time.strftime('%Y-%m-%d %H:%M', now)} UTC", "",
     "Solo lectura y paper trading. Fuentes: GeckoTerminal, DexScreener, RugCheck.", ""]
por_cadena = collections.Counter(r["chain"] for r in R)
bandas = collections.Counter(r["band"] for r in R)
fallos = collections.Counter(x for r in R for x in r["f"])
L += ["## Cobertura", f"- {len(R)} tokens: " + ", ".join(f"{k} {v}" for k, v in por_cadena.most_common()),
      "- Bandas: " + ", ".join(f"{k} {v}" for k, v in sorted(bandas.items())),
      "- Filtros que más fallan: " + ", ".join(f"{k} {v}" for k, v in fallos.most_common()), ""]
cand = [r for r in R if not r["f"] and r["band"] in ("A", "B", "C", "D")]
L += [f"## Pasan filtros numéricos (bandas A–D): {len(cand)}", ""]
ok = []
if cand:
    L += ["| Token | Cadena | Dirección | Banda | MC | Liq | Seguridad | DexScreener |", "|---|---|---|---|---|---|---|---|"]
    for r in cand:
        f, info = revisar(r["chain"], r["addr"])
        seg = "PASA" if not f else "NO: " + "+".join(f)
        if not f: ok.append(r)
        L.append(f"| {r['sym']} | {r['chain']} | `{r['addr']}` | {r['band']} | {int(r['mc']):,} | {int(r['liq']):,} | {seg} (top10 {info.get('top10')}{(', GoPlus ' + str(info['goplus'])) if isinstance(info.get('goplus'), dict) else ''}) | https://dexscreener.com/{DS.get(r['chain'], r['chain'])}/{r['addr']} |")
        time.sleep(1.2)
L += ["", f"## Candidatos (numéricos + seguridad): {len(ok)}"]
L += [f"- **{r['sym']}** ({r['chain']}) `{r['addr']}`: falta revisar señales de entrada y GMGN a mano." for r in ok] or ["- Ninguno."]
h2 = [r for r in R if (r["c5"] or 0) >= 50 or (r["c1"] or 0) >= 150]
L += ["", f"## H2: subidas fuertes (+50 % en 5m o +150 % en 1h): {len(h2)}"]
L += [f"- {r['sym']} ({r['chain']}) `{r['addr']}` banda {r['band']}, 5m {r['c5']} %, 1h {r['c1']} %, mc {int(r['mc']):,}, liq {int(r['liq']):,}, precio {r['price']}" for r in h2] or ["- Ninguna."]
os.makedirs("escaneos", exist_ok=True)
open(f"escaneos/escaneo_{stamp}.md", "w").write("\n".join(L) + "\n")
print(f"escaneos/escaneo_{stamp}.md", len(cand), len(ok))
