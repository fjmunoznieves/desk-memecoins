"""Escucha A en segundos (21-nov, Fran OK "Sí, activar en papel"). SOLO LECTURA, paper.

Fuente gratis: websocket público de Solana (logsSubscribe), sin clave, no gasta Helius.
- Se suscribe a las billeteras A (datos/watchlist_A_oper.tsv).
- Decodifica de los logs los eventos de pump.fun (TradeEvent) y PumpSwap (BuyEvent/SellEvent):
  token/pool, si es compra o venta, precio en SOL, hora del bloque.
- Cuando una A compra, sigue ese token/pool ~90 min (todas las operaciones, máx 1 cada 2 s)
  para tener el precio a +10 s, +30 s, +60 s... y medir en papel copiar con distintas salidas.
Salida: datos/escucha/ev_AAAAMMDD.tsv (lo analiza scripts/escucha_an.py). No opera, no firma nada.
"""
import asyncio, base64, csv, json, os, struct, subprocess, sys, time, datetime as dt

import websockets

WS = os.environ.get("ESCUCHA_WS", "wss://api.mainnet-beta.solana.com")
MINUTOS = float(os.environ.get("ESCUCHA_MINUTOS", "340"))
SEGUIR_S = 90 * 60          # cuánto seguir un token tras la compra A
MAX_SEGUIDOS = 120          # tope de tokens seguidos a la vez (carga del RPC público)
DEBUG = int(os.environ.get("ESCUCHA_DEBUG", "0"))
POR_CONEXION = int(os.environ.get("ESCUCHA_POR_CONEXION", "45"))   # tokens seguidos por conexión T
CONEX_A = 4; CONEX_T = 1    # el RPC público da 429 con más de ~5 conexiones por IP (prueba 21-nov)
RUIDO_MAX = int(os.environ.get("ESCUCHA_RUIDO_MAX", "60"))  # notif./min (21-nov: con 120 hubo ~100 cortes 1002 en 5,5 h) por billetera; prueba 21-nov: 97k notif. en 7 min
RALENTI_S = 2               # máx 1 fila de "trade" por token cada 2 s

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
D_TRADE = bytes.fromhex("bddb7fd34ee661ee")   # sha256("event:TradeEvent")[:8]
import hashlib
D_BUY = hashlib.sha256(b"event:BuyEvent").digest()[:8]
D_SELL = hashlib.sha256(b"event:SellEvent").digest()[:8]

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def decodificar(logs):
    """Devuelve lista de dicts: dex, clave(mint|pool), compra(bool), usuario, precio_sol, sol, ts."""
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "):
            continue
        try:
            d = base64.b64decode(l[14:])
        except Exception:
            continue
        try:
            if d[:8] == D_TRADE and len(d) >= 8 + 32 + 8 + 8 + 1 + 32 + 8 + 16:
                p = 8
                mint = b58(d[p:p+32]); p += 32
                sol, tok = struct.unpack_from("<QQ", d, p); p += 16
                compra = d[p] == 1; p += 1
                user = b58(d[p:p+32]); p += 32
                ts, = struct.unpack_from("<q", d, p); p += 8
                vsol, vtok = struct.unpack_from("<QQ", d, p)
                precio = (vsol / 1e9) / (vtok / 1e6) if vtok else 0
                out.append(dict(dex="pf", clave=mint, compra=compra, usuario=user, precio=precio, sol=sol / 1e9, ts=ts))
            elif d[:8] in (D_BUY, D_SELL) and len(d) >= 8 + 14 * 8 + 64:
                v = struct.unpack_from("<q13Q", d, 8)
                ts, base_amt, _, _, _, pbase, pquote, quote_amt = v[:8]
                p = 8 + 14 * 8
                pool = b58(d[p:p+32]); user = b58(d[p+32:p+64])
                precio = (pquote / 1e9) / (pbase / 1e6) if pbase else 0   # supone base 6 dec y quote WSOL
                out.append(dict(dex="ps", clave=pool, compra=d[:8] == D_BUY, usuario=user, precio=precio, sol=quote_amt / 1e9, ts=ts))
        except Exception:
            continue
    return out


class Conexion:
    """Una conexión websocket con hasta POR_CONEXION suscripciones (el RPC público corta si hay más)."""
    def __init__(self, padre, nombre, fijas):
        self.p = padre; self.nombre = nombre
        self.fijas = list(fijas)      # [("A", billetera)] fijas de esta conexión
        self.dinamicas = {}           # clave -> hasta_ts (tokens seguidos)
        self.ws = None; self.nid = 0; self.pend = {}; self.subs = {}; self.sid_de = {}

    def libre(self):
        return self.ws is not None and len(self.dinamicas) < POR_CONEXION

    async def pedir(self, metodo, params, que=None):
        self.nid += 1
        if que: self.pend[self.nid] = que
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self.nid, "method": metodo, "params": params}))

    async def sub(self, que):
        await self.pedir("logsSubscribe", [{"mentions": [que[1]]}, {"commitment": "confirmed"}], que)
        await asyncio.sleep(0.5)

    async def limpiar(self):
        ahora = time.time()
        for k, hasta in list(self.dinamicas.items()):
            if hasta < ahora:
                del self.dinamicas[k]; self.p.donde.pop(k, None)
                sid = self.sid_de.pop(k, None)
                if sid is not None:
                    self.subs.pop(sid, None)
                    await self.pedir("logsUnsubscribe", [sid])

    async def sesion(self, fin):
        async with websockets.connect(WS, ping_interval=20, ping_timeout=60, max_size=2**23) as ws:
            self.ws = ws; self.pend.clear(); self.subs.clear(); self.sid_de.clear()
            for q in self.fijas: await self.sub(q)
            for k in list(self.dinamicas): await self.sub(("T", k))
            ult = time.time()
            while time.time() < fin:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    await self.manejar(json.loads(raw))
                except asyncio.TimeoutError:
                    pass
                if time.time() - ult > 60:
                    ult = time.time(); await self.limpiar()

    async def manejar(self, msg):
        if "id" in msg and msg["id"] in self.pend:
            que = self.pend.pop(msg["id"])
            if "result" in msg:
                self.subs[msg["result"]] = que
                if que[0] == "T": self.sid_de[que[1]] = msg["result"]
                else: self.p.n["subsA"] += 1
            else:
                self.p.n["err"] += 1
                if self.p.n["err"] <= 5: print("error suscripción", self.nombre, que[0], msg.get("error"), flush=True)
            return
        if msg.get("method") != "logsNotification":
            return
        pr = msg["params"]; que = self.subs.get(pr["subscription"])
        if que: await self.p.notificacion(que, pr["result"]["value"])

    async def correr(self, fin):
        intentos = 0
        while time.time() < fin:
            t_ini = time.time()
            try:
                await self.sesion(fin); intentos = 0
            except Exception as ex:
                # 25-nov: si la sesión duró >2 min, el corte es nuevo: reintentar rápido. Antes el contador nunca se
                # reiniciaba y tras ~12 cortes cada reconexión esperaba 60 s (tarde 25-nov: 0-3 de 5 conexiones vivas).
                if time.time() - t_ini > 120: intentos = 0
                self.ws = None; intentos += 1
                if intentos <= 3 or intentos % 10 == 0:
                    print("conexión", self.nombre, "caída:", type(ex).__name__, str(ex)[:120], "reintento", intentos, flush=True)
                await asyncio.sleep(min(60, 5 * intentos))
            self.ws = None


class Escucha:
    def __init__(self):
        self.A = {}
        for r in csv.DictReader(open("datos/watchlist_A_oper.tsv"), delimiter="\t"):
            self.A[r["direccion"]] = r.get("operador") or r["direccion"][:6]
        os.makedirs("datos/escucha", exist_ok=True)
        ws_ = list(self.A)
        k = -(-len(ws_) // CONEX_A)
        self.conA = [Conexion(self, f"A{i}", [("A", w) for w in ws_[j:j + k]]) for i, j in enumerate(range(0, len(ws_), k))]
        self.conT = [Conexion(self, f"T{i}", []) for i in range(CONEX_T)]
        self.visto = set()       # (firma, usuario, clave): el mismo evento llega por varias suscripciones
        self.cuenta = {}         # billetera -> notificaciones en la ventana actual
        self.ruidosas = set()    # billeteras con > RUIDO_MAX notificaciones en 5 min (bots): se dejan de escuchar
        self.donde = {}       # clave seguida -> Conexion
        self.ult_fila = {}
        self.n = dict(subsA=0, A_compra=0, A_venta=0, trade=0, notif=0, err=0, sin_cupo=0)
        self.f = None; self.dia = None

    def escribir(self, fila):
        dia = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        if dia != self.dia:
            if self.f: self.f.close()
            ruta = f"datos/escucha/ev_{dia}.tsv"
            nuevo = not os.path.exists(ruta)
            self.f = open(ruta, "a", buffering=1); self.dia = dia
            if nuevo:
                self.f.write("recv_ts\tblock_ts\ttipo\tdex\tbilletera\toperador\tclave\tprecio_sol\tsol\tfirma\n")
        self.f.write("\t".join(str(x) for x in fila) + "\n")

    async def seguir(self, clave):
        c = self.donde.get(clave)
        if c:
            c.dinamicas[clave] = time.time() + SEGUIR_S; return
        c = next((c for c in self.conT if c.libre()), None)
        if not c:
            self.n["sin_cupo"] += 1; return
        c.dinamicas[clave] = time.time() + SEGUIR_S; self.donde[clave] = c
        await c.sub(("T", clave))

    async def notificacion(self, que, v):
        self.n["notif"] += 1
        if que[0] == "A":
            if que[1] in self.ruidosas:
                return
            self.cuenta[que[1]] = self.cuenta.get(que[1], 0) + 1
        if v.get("err"):
            return
        recv = round(time.time(), 2)
        firma = v.get("signature", "")
        if DEBUG and self.n["notif"] <= DEBUG:
            pd = [l[14:30] for l in v.get("logs") or [] if l.startswith("Program data: ")]
            progs = sorted({l.split()[1] for l in v.get("logs") or [] if l.startswith("Program ") and " invoke" in l})
            print("DEBUG", que[0], firma[:12], "progs", [x[:6] for x in progs], "data", pd[:4], flush=True)
        for e in decodificar(v.get("logs")):
            if e["precio"] <= 0:
                continue
            if e["usuario"] in self.A:
                tipo = "A_compra" if e["compra"] else "A_venta"
                self.n[tipo] += 1
                cl = (firma, e["usuario"], e["clave"], tipo)
                if cl in self.visto:
                    continue
                self.visto.add(cl)
                self.escribir([recv, e["ts"], tipo, e["dex"], e["usuario"], self.A[e["usuario"]], e["clave"], f"{e['precio']:.6g}", f"{e['sol']:.4f}", firma])
                if e["compra"]:
                    await self.seguir(e["clave"])
            elif que[0] == "T" and e["clave"] == que[1]:
                k = e["clave"]
                if recv - self.ult_fila.get(k, 0) < RALENTI_S:
                    continue
                self.ult_fila[k] = recv
                self.n["trade"] += 1
                self.escribir([recv, e["ts"], "trade", e["dex"], "", "", k, f"{e['precio']:.6g}", f"{e['sol']:.4f}", ""])

    async def reporte(self, fin):
        vuelta = 0
        while time.time() < fin:
            await asyncio.sleep(60); vuelta += 1
            for w, c in self.cuenta.items():
                if c > RUIDO_MAX and w not in self.ruidosas:
                    self.ruidosas.add(w)
                    print("ruidosa (deja de escucharse):", w, self.A.get(w), c, "notif/min", flush=True)
                    for con in self.conA:
                        con.fijas = [q for q in con.fijas if q[1] != w]
                        for sid, q in list(con.subs.items()):
                            if q[1] == w and con.ws is not None:
                                con.subs.pop(sid, None)
                                try: await con.pedir("logsUnsubscribe", [sid])
                                except Exception: pass
            self.cuenta = {}
            if vuelta % 15 == 0 and os.environ.get("GH_TOKEN"):  # 25-nov: guardián de escaneos cada 15 min (sin Claude)
                try:
                    r = await asyncio.to_thread(subprocess.run, [sys.executable, os.path.join(os.path.dirname(__file__), "guardian.py")],
                                                capture_output=True, text=True, timeout=60)
                    if "DISPARADA" in r.stdout: print("guardián:", r.stdout.strip(), flush=True)
                except Exception as e:
                    print("guardián falló:", str(e)[:80], flush=True)
            if vuelta % 5: continue
            if len(self.visto) > 200000: self.visto = set()
            vivas = sum(1 for c in self.conA + self.conT if c.ws is not None)
            print(dt.datetime.now(dt.timezone.utc).strftime("%H:%M"), f"conexiones vivas {vivas}/{len(self.conA)+len(self.conT)}, seguidos {len(self.donde)},", self.n, flush=True)

    async def correr(self):
        fin = time.time() + MINUTOS * 60
        tareas = []
        for c in self.conA + self.conT:
            tareas.append(asyncio.create_task(c.correr(fin)))
            await asyncio.sleep(2)
        tareas.append(asyncio.create_task(self.reporte(fin)))
        await asyncio.gather(*tareas)
        print("FIN", self.n, flush=True)


if __name__ == "__main__":
    asyncio.run(Escucha().correr())
