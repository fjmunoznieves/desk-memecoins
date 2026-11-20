"""RPC de Solana para los escaneos (20-nov, Fran eligió cuidar Helius): Shyft primero (gratis, sin tope de créditos,
10 consultas/s), Helius solo como respaldo si Shyft falla. Las claves salen de secretos y nunca se imprimen."""
import json, os, time, urllib.request, urllib.error

_H = os.environ.get("HELIUS_API_KEY", "").strip()
_S = os.environ.get("SHYFT_API_KEY", "").strip()
HELIUS = f"https://mainnet.helius-rpc.com/?api-key={_H}" if _H else ""
SHYFT = f"https://rpc.shyft.to?api_key={_S}" if _S else ""
PRINCIPAL = SHYFT or HELIUS
RESPALDO = HELIUS if SHYFT else ""
USO = {"shyft": 0, "helius": 0, "fallos": 0, "error": ""}
CLAVES = [k for k in (_H, _S) if k]


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


def post_json(body_dict, intentos=5, timeout=40):
    """Devuelve la respuesta JSON completa. Lanza excepción si fallan Shyft y Helius."""
    body = json.dumps(body_dict).encode()
    try:
        d = _uno(PRINCIPAL, body, intentos, timeout)
        USO["shyft" if PRINCIPAL == SHYFT else "helius"] += 1
        return d
    except Exception as e:
        if not RESPALDO:
            raise RuntimeError(limpio(e))
        USO["fallos"] += 1
        if not USO["error"]:
            m = limpio(e)
            if hasattr(e, "read"):
                try: m += " " + limpio(e.read().decode()[:200])
                except Exception: pass
            USO["error"] = m[:300]
        d = _uno(RESPALDO, body, intentos, timeout)
        USO["helius"] += 1
        return d


def resumen():
    return f"RPC: Shyft {USO['shyft']}, Helius {USO['helius']} (respaldo tras {USO['fallos']} fallos de Shyft){' — primer error: ' + USO['error'] if USO['error'] else ''}"
