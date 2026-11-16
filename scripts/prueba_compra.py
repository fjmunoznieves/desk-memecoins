"""Prueba (manual) del nuevo lector de compras de watch_solana: relee con getTransaction las últimas compras
registradas con el método viejo y compara token y SOL. Solo lectura; la clave nunca se imprime."""
import ast, csv, json, os, time, urllib.request
src = open("scripts/watch_solana.py").read()
ns = {"os": os, "time": time, "json": json, "urllib": urllib}
KEY = os.environ.get("HELIUS_API_KEY", "").strip()
for n in ast.parse(src).body:
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("KEY", "RPC", "ALC", "RPC_TX", "BASE") for t in n.targets):
        exec(compile(ast.Module([n], []), "w", "exec"), ns)
    if isinstance(n, ast.FunctionDef) and n.name in ("post", "safe", "tx_rpc", "compra_de"):
        exec(compile(ast.Module([n], []), "w", "exec"), ns)
filas = list(csv.DictReader(open("datos/watchlist_compras.tsv"), delimiter="\t"))[-12:]
ok = 0
for r in filas:
    t = ns["tx_rpc"](r["firma"])
    c = ns["compra_de"](t, r["billetera"]) if t else []
    hit = any(x["token"] == r["token"] for x in c)
    ok += hit
    print("OK " if hit else "MAL", r["token"][:8], "viejo", r["sol_gastado"], "nuevo", [(x["token"][:8], x["sol_gastado"]) for x in c])
print(f"coinciden {ok}/{len(filas)}")
