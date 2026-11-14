"""H16 paso diario: marca qué tokens del universo están "muertos" (candidatos a resurrección).

Muerto = al menos 21 velas diarias y las últimas 7 cierran a ≤20 % del máximo histórico.
Guarda datos/muertos.json con el volumen base por hora (mediana diaria de 7 días / 24).
Solo lectura de GeckoTerminal. Desde GitHub sale lento (~14 s por token por los límites), así que
trabaja por tandas de 50 min: cada corrida revisa primero los tokens revisados hace más tiempo y
guarda el avance; con 4 corridas al día se recorre todo el universo.
"""
import json, os, statistics, time, urllib.request

U = "datos/resurreccion_universo.json"
OUT = "datos/muertos.json"
PRESUPUESTO = 50 * 60  # segundos por corrida
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
prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
estado = prev.get("estado", {})  # "red:token" -> {"fecha": epoch, "muerto": bool, ...datos si muerto}
inicio = time.time()
orden = sorted(universo, key=lambda t: estado.get(f"{t['net']}:{t['token']}", {}).get("fecha", 0))
hechos = 0
for t in orden:
    if time.time() - inicio > PRESUPUESTO:
        break
    k = f"{t['net']}:{t['token']}"
    d = get(f"https://api.geckoterminal.com/api/v2/networks/{t['net']}/pools/{t['pool']}/ohlcv/day?limit=181&currency=usd&token=base")
    time.sleep(2.1)
    hechos += 1
    v = sorted(((d or {}).get("data") or {}).get("attributes", {}).get("ohlcv_list") or [])
    if d is None and k in estado:
        continue  # falló la consulta: se deja el dato anterior
    if len(v) < 21:
        estado[k] = {"fecha": int(time.time()), "muerto": False, "motivo": "historia<21d"}
        continue
    pico = max(c[2] for c in v)
    ult = v[-7:]
    if pico > 0 and all(c[4] <= 0.2 * pico for c in ult):
        base = max(statistics.median(c[5] for c in ult) / 24, BASE_MIN)
        estado[k] = dict(t, fecha=int(time.time()), muerto=True, pico=pico, cierre=ult[-1][4], minimo7=min(c[3] for c in ult), base_h=round(base, 2), velas=len(v))
    else:
        estado[k] = {"fecha": int(time.time()), "muerto": False}
    if hechos % 50 == 0:
        print(hechos, "revisados en esta corrida", flush=True)

muertos = [e for e in estado.values() if e.get("muerto")]
json.dump({"fecha": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "revisados_total": len(estado), "universo": len(universo),
           "muertos": muertos, "estado": estado}, open(OUT, "w"))
print(f"esta corrida {hechos} | revisados alguna vez {len(estado)}/{len(universo)} | muertos {len(muertos)}")
