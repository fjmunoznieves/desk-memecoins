"""H16 paso diario: marca qué tokens del universo están "muertos" (candidatos a resurrección).

Muerto = al menos 21 velas diarias y las últimas 7 cierran a ≤20 % del máximo histórico.
Guarda datos/muertos.json con el volumen base por hora (mediana diaria de 7 días / 24).
Solo lectura de GeckoTerminal; ~2 s por token por el límite de 30 consultas/min.
"""
import json, statistics, time, urllib.request

U = "datos/resurreccion_universo.json"
OUT = "datos/muertos.json"
BASE_MIN = 50.0  # USD/h: piso para que un token casi sin volumen no dispare con cualquier compra


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(30 if getattr(e, "code", None) == 429 else 3)
    return None


universo = json.load(open(U))
muertos, vivos, sin = [], 0, 0
for i, t in enumerate(universo):
    d = get(f"https://api.geckoterminal.com/api/v2/networks/{t['net']}/pools/{t['pool']}/ohlcv/day?limit=181&currency=usd&token=base")
    time.sleep(2.1)
    v = sorted(((d or {}).get("data") or {}).get("attributes", {}).get("ohlcv_list") or [])
    if len(v) < 21:
        sin += 1
        continue
    pico = max(c[2] for c in v)
    ult = v[-7:]
    if pico > 0 and all(c[4] <= 0.2 * pico for c in ult):
        base = max(statistics.median(c[5] for c in ult) / 24, BASE_MIN)
        muertos.append(dict(t, pico=pico, cierre=ult[-1][4], minimo7=min(c[3] for c in ult), base_h=round(base, 2), velas=len(v)))
    else:
        vivos += 1
    if i % 100 == 0:
        print(i, len(universo), "muertos", len(muertos), flush=True)

json.dump({"fecha": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "muertos": muertos}, open(OUT, "w"), indent=0)
print(f"universo {len(universo)} | muertos {len(muertos)} | vivos {vivos} | sin historia suficiente {sin}")
