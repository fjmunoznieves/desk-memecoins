"""Estudio de reglas en sombra (H15). Solo registro; no cambia reglas.
Uso:
  python3 sombra.py registrar rows2.json   -> anota tokens cercanos del escaneo
  python3 sombra.py medir                  -> simula la salida del desk a 24 h en filas pendientes
  python3 sombra.py resumen                -> resultado por filtro
"""
import json, sys, time, urllib.request, os, csv, collections

OUT = os.environ.get("SOMBRA_OUT", "/mnt/project-files/desk/estudio_reglas_sombra.tsv")
VENTANA = float(os.environ.get("SOMBRA_HORAS", "24"))
COLS = ["hora_utc", "ts", "cadena", "direccion", "simbolo", "banda", "precio", "mc", "liq", "v5", "bs5", "c5", "c1",
        "quote", "fallos", "n_fallos", "pool", "estado", "max24_pct", "fin24_pct", "sim_pct", "sim_detalle"]
BASEQ = {"SOL", "WSOL", "USDC", "USDT", "WBNB", "BNB", "USD1", "ETH", "WETH", "BUSD", "FDUSD"}
GNET = {"solana": "solana", "bsc": "bsc", "robinhood": "robinhood"}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seguridad import revisar


def get(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "desk-scan", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", None) == 429:
                PAUSA[0] = min(PAUSA[0] + 1, 6)
                time.sleep(8 + 4 * k)
            else:
                time.sleep(3)
    return None


PAUSA = [2.1]          # sube sola si GeckoTerminal frena (429)
PRESUPUESTO_MEDIR = 180  # segundos por corrida: lo que no alcance se mide en el siguiente escaneo


def load():
    if not os.path.exists(OUT):
        return []
    with open(OUT) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def save(rows):
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})


def registrar(path):
    R = json.load(open(path))
    rows = load()
    seen = {(r["cadena"], r["direccion"]) for r in rows if r["estado"] == "pendiente"}
    now = os.path.getmtime(path)
    n = 0
    for r in R:
        # bandas A–E y "resurrecciones" (>7 d con +50 % en 1 h): solo registro
        if r.get("band") not in ("A", "B", "C", "D", "E") and not (r.get("band") == ">7d" and (r.get("c1") or 0) >= 50):
            continue
        f = r.get("f", [])
        if len(f) > 2 or r["liq"] < 15000 or (r["chain"], r["addr"]) in seen:
            continue
        f = list(f)
        if not f:  # seguridad 5.2 en las tres cadenas (seguridad.py)
            sf, _ = revisar(r["chain"], r["addr"])
            f += sf
            time.sleep(1.2)
        rows.append(dict(hora_utc=time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)), ts=int(now), cadena=r["chain"],
                         direccion=r["addr"], simbolo=r["sym"], banda=r["band"], precio=r["price"], mc=int(r["mc"]),
                         liq=int(r["liq"]), v5=int(r["v5"]), bs5=round(r.get("bs", 0), 2), c5=r["c5"], c1=r["c1"],
                         quote=r["quote"], fallos="+".join(f) or "ninguno", n_fallos=len(f), pool=r.get("pair") or "", estado="pendiente"))
        n += 1
    save(rows)
    print("registrados", n)


def pool_de(ch, addr):
    d = get(f"https://api.dexscreener.com/tokens/v1/{ch}/{addr}") or []
    if not d:
        return None
    return max(d, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)["pairAddress"]


def liq_actual(ch, addr):
    """Liquidez total del token ahora (0 si ya no tiene pares: rug / liquidez retirada). None si la API falla."""
    d = get(f"https://api.dexscreener.com/tokens/v1/{ch}/{addr}")
    if d is None:
        return None
    return sum((p.get("liquidity") or {}).get("usd") or 0 for p in d)


SIN_SALIDA = 1000  # USD: por debajo, la posición que seguía abierta se da por perdida (no hay con quién vender)
CERRADAS = ("stop", "time stop 45 min")  # salidas que ocurren antes; un rug posterior no las afecta


def ajustar_rug(r):
    """Si la simulación terminaba con posición abierta y el token ya no tiene liquidez, resultado -100 %."""
    if r.get("sim_detalle") in CERRADAS or str(r.get("sim_detalle", "")).startswith("rug"):
        return False
    liq = liq_actual(r["cadena"], r["direccion"])
    time.sleep(0.4)
    if liq is not None and liq < SIN_SALIDA:
        r["sim_pct"] = -100.0
        r["sim_detalle"] = f"rug: liquidez retirada (antes {r.get('sim_detalle')}, {r.get('sim_pct')} %)"
        return True
    return False


def simular(c, p0):
    """Velas de 5 min [ts,o,h,l,c,v] desde la entrada. Reglas del desk simplificadas:
    stop -20 %, TP1 50 % a +60 % (luego stop en break-even), TP2 25 % a +120 %, resto trailing 20 %,
    time stop 45 min sin TP1, cierre forzado a 24 h. Si en una vela tocan stop y TP, se asume el stop (conservador)."""
    pos, pnl, tp1, tp2, peak, stop = 1.0, 0.0, False, False, p0, p0 * 0.8
    for i, (ts, o, h, l, cl, v) in enumerate(c):
        if l <= stop:
            pnl += pos * (stop / p0 - 1)
            return pnl * 100, ("stop" if not tp1 else "break-even/trailing")
        if not tp1 and h >= p0 * 1.6:
            pnl += 0.5 * 0.6; pos -= 0.5; tp1 = True; stop = p0
        if tp1 and not tp2 and h >= p0 * 2.2:
            pnl += 0.25 * 1.2; pos -= 0.25; tp2 = True
        peak = max(peak, h)
        if tp1:
            stop = max(stop, peak * 0.8)
        if not tp1 and (i + 1) * 5 >= 45:
            pnl += pos * (cl / p0 - 1)
            return pnl * 100, "time stop 45 min"
    if c:
        pnl += pos * (c[-1][4] / p0 - 1)
    return pnl * 100, "cierre 24 h"


def medir():
    rows = load()
    now = time.time()
    n = 0
    for r in rows:
        if time.time() - now > PRESUPUESTO_MEDIR:
            break
        if r["estado"] != "pendiente" or now - int(r["ts"]) < VENTANA * 3600 or r["cadena"] not in GNET:
            if r["estado"] == "pendiente" and r["cadena"] not in GNET and now - int(r["ts"]) >= VENTANA * 3600:
                r["estado"] = "sin datos (cadena)"
            continue
        pool = r["pool"] or pool_de(r["cadena"], r["direccion"])
        time.sleep(0.5)
        if not pool:
            r["estado"] = "sin pool"; continue
        r["pool"] = pool
        t0 = int(r["ts"])
        d = get(f"https://api.geckoterminal.com/api/v2/networks/{GNET[r['cadena']]}/pools/{pool}/ohlcv/minute"
                f"?aggregate=5&limit=300&currency=usd&token={r['direccion']}&before_timestamp={t0 + 24 * 3600}")
        time.sleep(PAUSA[0])
        try:
            c = sorted(x for x in d["data"]["attributes"]["ohlcv_list"] if t0 <= x[0] <= t0 + 24 * 3600)
        except Exception:
            r["estado"] = "sin velas"; continue
        p0 = float(r["precio"] or 0)
        if not c or not p0:
            r["estado"] = "sin velas"; continue
        if abs(c[0][1] / p0 - 1) > 0.5:
            r["estado"] = "precio no cuadra"; continue
        if max(x[2] for x in c) > 50 * p0:
            r["estado"] = "dato raro (mecha >50x)"; continue
        r["max24_pct"] = round((max(x[2] for x in c) / p0 - 1) * 100, 1)
        r["fin24_pct"] = round((c[-1][4] / p0 - 1) * 100, 1)
        s, det = simular(c, p0)
        r["sim_pct"] = round(s, 1); r["sim_detalle"] = det; r["estado"] = "medido"
        ajustar_rug(r)
        n += 1
    save(rows)
    print("medidos", n)


def resumen():
    rows = [r for r in load() if r["estado"] == "medido"]
    g = collections.defaultdict(list)
    for r in rows:
        f = r["fallos"].split("+")
        if r["fallos"] == "ninguno":
            g["pasa numéricos"].append(float(r["sim_pct"]))
        elif len(f) == 1:
            g["solo falla " + f[0]].append(float(r["sim_pct"]))
        else:
            g["2 fallos"].append(float(r["sim_pct"]))
    print("grupo | n | media sim % | mediana sim % | % ganadoras | suma USD con 12 USD/operación")
    for k, v in sorted(g.items()):
        m = sorted(v)[len(v) // 2]
        print(k, "|", len(v), "|", round(sum(v) / len(v), 1), "|", round(m, 1), "|", round(100 * sum(x > 0 for x in v) / len(v)), "|",
              round(sum(v) * 0.12, 2))


if __name__ == "__main__":
    {"registrar": lambda: registrar(sys.argv[2]), "medir": medir, "resumen": resumen}[sys.argv[1]]()
