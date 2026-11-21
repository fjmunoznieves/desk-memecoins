"""Escucha A en segundos (21-nov, Fran OK "Sí, activar en papel"). SOLO LECTURA, paper.

Fuente gratis: websocket público de Solana (logsSubscribe), sin clave, no gasta Helius.
- Se suscribe a las billeteras A (datos/watchlist_A_oper.tsv).
- Decodifica de los logs los eventos de pump.fun (TradeEvent) y PumpSwap (BuyEvent/SellEvent):
  token/pool, si es compra o venta, precio en SOL, hora del bloque.
- Cuando una A compra, sigue ese token/pool ~90 min (todas las operaciones, máx 1 cada 2 s)
  para tener el precio a +10 s, +30 s, +60 s... y medir en papel copiar con distintas salidas.
Salida: datos/escucha/ev_AAAAMMDD.tsv (lo analiza scripts/escucha_an.py). No opera, no firma nada.
"""
import asyncio, base64, csv, json, os, struct, sys, time, datetime as dt

import websockets

WS = os.environ.get("ESCUCHA_WS", "wss://api.mainnet-beta.solana.com")
MINUTOS = float(os.environ.get("ESCUCHA_MINUTOS", "340"))
SEGUIR_S = 90 * 60          # cuánto seguir un token tras la compra A
MAX_SEGUIDOS = 150          # tope de tokens seguidos a la vez (carga del RPC público)
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


class Escucha:
    def __init__(self):
        self.A = {}
        for r in csv.DictReader(open("datos/watchlist_A_oper.tsv"), delimiter="\t"):
            self.A[r["direccion"]] = r.get("operador") or r["direccion"][:6]
        os.makedirs("datos/escucha", exist_ok=True)
        self.nid = 0
        self.pend = {}        # id petición -> ("A", billetera) | ("T", clave)
        self.subs = {}        # id suscripción -> ("A", billetera) | ("T", clave)
        self.seguidos = {}    # clave -> (sub_id|None, hasta_ts)
        self.ult_fila = {}
        self.n = dict(A_compra=0, A_venta=0, trade=0, notif=0, err=0)
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

    async def pedir(self, ws, metodo, params, que):
        self.nid += 1
        self.pend[self.nid] = que
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": self.nid, "method": metodo, "params": params}))

    async def seguir(self, ws, clave):
        if clave in self.seguidos:
            sid, _ = self.seguidos[clave]
            self.seguidos[clave] = (sid, time.time() + SEGUIR_S)
            return
        if len(self.seguidos) >= MAX_SEGUIDOS:
            return
        self.seguidos[clave] = (None, time.time() + SEGUIR_S)
        await self.pedir(ws, "logsSubscribe", [{"mentions": [clave]}, {"commitment": "confirmed"}], ("T", clave))

    async def limpiar(self, ws):
        ahora = time.time()
        for clave, (sid, hasta) in list(self.seguidos.items()):
            if hasta < ahora:
                del self.seguidos[clave]
                if sid is not None:
                    self.subs.pop(sid, None)
                    self.nid += 1
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": self.nid, "method": "logsUnsubscribe", "params": [sid]}))

    async def manejar(self, ws, msg):
        if "id" in msg and msg["id"] in self.pend:
            que = self.pend.pop(msg["id"])
            if "result" in msg:
                self.subs[msg["result"]] = que
                if que[0] == "T" and que[1] in self.seguidos:
                    self.seguidos[que[1]] = (msg["result"], self.seguidos[que[1]][1])
            else:
                self.n["err"] += 1
                if self.n["err"] <= 5: print("error suscripción", que[0], msg.get("error"), flush=True)
                if que[0] == "T": self.seguidos.pop(que[1], None)
            return
        if msg.get("method") != "logsNotification":
            return
        self.n["notif"] += 1
        p = msg["params"]; v = p["result"]["value"]
        if v.get("err"):
            return
        que = self.subs.get(p["subscription"])
        if not que:
            return
        recv = round(time.time(), 2)
        firma = v.get("signature", "")
        for e in decodificar(v.get("logs")):
            if e["precio"] <= 0:
                continue
            if e["usuario"] in self.A:
                tipo = "A_compra" if e["compra"] else "A_venta"
                self.n[tipo] += 1
                self.escribir([recv, e["ts"], tipo, e["dex"], e["usuario"], self.A[e["usuario"]], e["clave"], f"{e['precio']:.6g}", f"{e['sol']:.4f}", firma])
                if e["compra"]:
                    await self.seguir(ws, e["clave"])
            elif que[0] == "T" and e["clave"] == que[1]:
                k = e["clave"]
                if recv - self.ult_fila.get(k, 0) < RALENTI_S:
                    continue
                self.ult_fila[k] = recv
                self.n["trade"] += 1
                self.escribir([recv, e["ts"], "trade", e["dex"], "", "", k, f"{e['precio']:.6g}", f"{e['sol']:.4f}", ""])

    async def sesion(self, fin):
        async with websockets.connect(WS, ping_interval=20, ping_timeout=60, max_size=2**23) as ws:
            self.pend.clear(); self.subs.clear()
            self.seguidos = {k: (None, h) for k, (_, h) in self.seguidos.items()}
            for i, w in enumerate(self.A):
                await self.pedir(ws, "logsSubscribe", [{"mentions": [w]}, {"commitment": "confirmed"}], ("A", w))
                if i % 20 == 19: await asyncio.sleep(0.5)
            for k in list(self.seguidos):
                del self.seguidos[k]; await self.seguir(ws, k)
            ult_rep = time.time()
            while time.time() < fin:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    await self.manejar(ws, json.loads(raw))
                except asyncio.TimeoutError:
                    pass
                if time.time() - ult_rep > 300:
                    ult_rep = time.time()
                    await self.limpiar(ws)
                    na = sum(1 for q in self.subs.values() if q[0] == "A")
                    print(dt.datetime.now(dt.timezone.utc).strftime("%H:%M"), f"subs A {na}/{len(self.A)}, seguidos {len(self.seguidos)},", self.n, flush=True)

    async def correr(self):
        fin = time.time() + MINUTOS * 60
        intentos = 0
        while time.time() < fin:
            try:
                await self.sesion(fin)
            except Exception as ex:
                intentos += 1
                print("conexión caída:", type(ex).__name__, str(ex)[:150], "reintento", intentos, flush=True)
                await asyncio.sleep(min(60, 5 * intentos))
        print("FIN", self.n, flush=True)


if __name__ == "__main__":
    asyncio.run(Escucha().correr())
