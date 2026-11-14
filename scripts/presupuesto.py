"""Freno mensual de minutos de GitHub Actions (tope 1.000 min/mes).

Suma los minutos de las corridas del mes (cada corrida cuenta mínimo 1 min, redondeando hacia arriba)
y decide si la tarea actual corre. Escribe corre=true/false en $GITHUB_OUTPUT.
  Uso: python3 scripts/presupuesto.py <escaneo|escaneo_opcional|reloj|otro>
Reglas: escaneo_opcional solo si el gasto va por debajo del ritmo del mes (tope × día / días del mes);
escaneo se salta desde 950 min; reloj y lo demás desde 985 min. Las corridas manuales siempre corren.
"""
import calendar, datetime as dt, json, math, os, subprocess, sys

TOPE = 1000
tipo = sys.argv[1] if len(sys.argv) > 1 else "otro"
repo = os.environ.get("GITHUB_REPOSITORY", "fjmunoznieves/desk-memecoins")
hoy = dt.datetime.now(dt.timezone.utc)
inicio = hoy.replace(day=1).strftime("%Y-%m-%d")


def minutos():
    total, page = 0, 1
    while True:
        r = subprocess.run(["gh", "api", f"repos/{repo}/actions/runs?created=>={inicio}&per_page=100&page={page}"],
                           capture_output=True, text=True)
        if r.returncode:
            print("no se pudo leer el uso:", r.stderr[:200])
            return None
        runs = json.loads(r.stdout).get("workflow_runs", [])
        for x in runs:
            if not x.get("run_started_at") or x.get("status") != "completed":
                continue
            a = dt.datetime.fromisoformat(x["run_started_at"].replace("Z", "+00:00"))
            b = dt.datetime.fromisoformat(x["updated_at"].replace("Z", "+00:00"))
            total += max(1, math.ceil((b - a).total_seconds() / 60))
        if len(runs) < 100:
            return total
        page += 1


usado = minutos()
dias = calendar.monthrange(hoy.year, hoy.month)[1]
ritmo = TOPE * hoy.day / dias
manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
if usado is None or manual:
    corre = True
elif tipo == "escaneo_opcional":
    corre = usado < ritmo and usado < 950
elif tipo == "escaneo":
    corre = usado < 950
else:
    corre = usado < 985
print(f"uso del mes {usado} min | ritmo hoy {ritmo:.0f} | tope {TOPE} | {tipo}: {'corre' if corre else 'SE SALTA'}")
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"corre={'true' if corre else 'false'}\n")
