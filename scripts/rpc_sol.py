"""RPC de Solana para los escaneos (20-nov, Fran eligió cuidar Helius): Shyft primero (gratis, sin tope de créditos,
10 consultas/s), Helius solo como respaldo si Shyft falla. Las claves salen de secretos y nunca se imprimen."""
import json, os, time, urllib.request, urllib.error

_H = os.environ.get("HELIUS_API_KEY", "").strip()
_S = os.environ.get("SHYFT_API_KEY", "").strip()
_A = os.environ.get("ALCHEMY_API_KEY", "").strip()
ALCHEMY = f"https://solana-mainnet.g.alchemy.com/v2/{_A}" if _A else ""
# 20-nov: Shyft gratis NO permite métodos de índice (403 IndexNotAllowedOnFreePlan). Esos van a Alchemy
# (plan gratis se renueva el 1-dic; hasta entonces falla y cae a Helius) y Helius de respaldo.
INDICE = {"getTokenAccountsByOwner", "getProgramAccounts", "getTokenLargestAccounts", "getTokenAccountsByDelegate"}
HELIUS = f"https://mainnet.helius-rpc.com/?api-key={_H}" if _H else ""
SHYFT = f"https://rpc.shyft.to?api_key={_S}" if _S else ""
PRINCIPAL = SHYFT or HELIUS
USO = {"shyft": 0, "alchemy": 0, "helius": 0, "fallos": 0, "error": ""}
CLAVES = [k for k in (_H, _S, _A) if k]


def hay():
    return bool(PRINCIPAL)


def limpio(m):
    m = str(m)
    for k in CLAVES:
        m = m.replace(k, "***")
    return m


def _uno(url, body, intentos, timeout):
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "desk-scan"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            if isinstance(d, dict) and d.get("error") and not d.get("result"):
                raise RuntimeError(str(d["error"])[:120])
            return d
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == intentos - 1:
                raise
            time.sleep(2 + 2 * i)
    raise RuntimeError("sin respuesta")


CAIDOS = {}


def _nombre(url):
    return "shyft" if url == SHYFT else "alchemy" if url == ALCHEMY else "helius"


def post_json(body_dict, intentos=5, timeout=40):
    """Devuelve la respuesta JSON completa. Prueba la cadena de proveedores según el método; lanza excepción si fallan todos."""
    body = json.dumps(body_dict).encode()
    cadena = [ALCHEMY, HELIUS] if body_dict.get("method") in INDICE else [SHYFT, HELIUS]
    cadena = [u for u in cadena if u and CAIDOS.get(u, 0) < 3] or [HELIUS]
    ult = None
    for j, url in enumerate(cadena):
        try:
            d = _uno(url, body, intentos if j == len(cadena) - 1 else 1, timeout if j == len(cadena) - 1 else 10)
            USO[_nombre(url)] += 1
            CAIDOS[url] = 0
            return d
        except Exception as e:
            ult = e
            if j < len(cadena) - 1:
                USO["fallos"] += 1
                CAIDOS[url] = CAIDOS.get(url, 0) + 1  # 3 fallos seguidos: se salta ese proveedor el resto de la corrida
                if not USO["error"]:
                    m = limpio(e)
                    if hasattr(e, "read"):
                        try: m += " " + limpio(e.read().decode()[:200])
                        except Exception: pass
                    USO["error"] = f"{_nombre(url)}: " + m[:300]
    raise RuntimeError(limpio(ult))


def resumen():
    return f"RPC: Shyft {USO['shyft']}, Alchemy {USO['alchemy']}, Helius {USO['helius']} (respaldos: {USO['fallos']}){' — primer error: ' + USO['error'] if USO['error'] else ''}"
