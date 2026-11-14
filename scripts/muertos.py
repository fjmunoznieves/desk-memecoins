"""H16: lee UNA sola vez el historial diario de cada token del universo (GeckoTerminal).

Guarda en datos/muertos.json["estado"] por token: pico, último día que cerró por encima del 20 % del pico
(ultimo_arriba) y el volumen base por hora. Después el reloj (resurreccion.py) mantiene ese estado al día
con DexScreener, sin volver a pedir velas. Esta tarea solo trabaja con tokens nuevos o pendientes.
Desde GitHub GeckoTerminal va lento (~14 s por token), por eso trabaja en tandas de 50 min.
"""
import json, os, statistics, time, urllib.request

U = "datos/resurreccion_universo.json"
OUT = "datos/muertos.json"
PRESUPUESTO = 50 * 60
BASE_MIN = 50.0
UMBRAL = 0.2


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return {}
            time.sleep(30 if getattr(e, "code", None) == 429 else 3)
    return None


def cargar():
    return json.load(open(OUT)) if os.path.exists(OUT) else {}


def guardar(prev, estado):
    prev["estado"] = estado
    prev["muertos"] = [e for e in estado.values() if e.get("muerto")]
    prev["fecha"] = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())
    json.dump(prev, open(OUT, "w"))


if __name__ == "__main__":
    universo = json.load(open(U))
    prev = cargar()
    estado = prev.get("estado", {})
    pend = [t for t in universo if "ultimo_arriba" not in estado.get(f"{t['net']}:{t['token']}", {})
            and estado.get(f"{t['net']}:{t['token']}", {}).get("motivo") != "historia<21d"]
    inicio, hechos = time.time(), 0
    for t in pend:
        if time.time() - inicio > PRESUPUESTO:
            break
        k = f"{t['net']}:{t['token']}"
        d = get(f"https://api.geckoterminal.com/api/v2/networks/{t['net']}/pools/{t['pool']}/ohlcv/day?limit=181&currency=usd&token=base")
        time.sleep(2.1)
        hechos += 1
        if d is None:
            continue  # falló: queda pendiente para la próxima tanda
        v = sorted((d.get("data") or {}).get("attributes", {}).get("ohlcv_list") or [])
        if len(v) < 21:
            # muy joven: se reintenta cuando tenga 21 días (se borra la marca a los 7 días)
            estado[k] = {"motivo": "historia<21d", "fecha": int(time.time()), **t}
            continue
        pico = max(c[2] for c in v)
        arriba = [c[0] for c in v if c[4] > UMBRAL * pico]
        vols = [c[5] for c in v[-7:]]
        e = dict(t, fecha=int(time.time()), pico=pico, ultimo_arriba=max(arriba) + 86400 if arriba else v[0][0],
                 vols={time.strftime("%Y-%m-%d", time.gmtime(c[0])): c[5] for c in v[-7:]},
                 base_h=round(max(statistics.median(vols) / 24, BASE_MIN), 2))
        e["muerto"] = time.time() - e["ultimo_arriba"] >= 7 * 86400
        estado[k] = e
        if hechos % 50 == 0:
            print(hechos, "revisados", flush=True)
    # los jóvenes se reintentan a la semana
    for k, e in list(estado.items()):
        if e.get("motivo") == "historia<21d" and time.time() - e.get("fecha", 0) > 7 * 86400:
            e.pop("motivo")
    guardar(prev, estado)
    con = sum(1 for e in estado.values() if "ultimo_arriba" in e)
    print(f"esta tanda {hechos} | con historia {con}/{len(universo)} | pendientes {len(pend) - hechos} | muertos {len(prev['muertos'])}")
