"""Freno mensual de minutos de GitHub Actions (plan gratis 2.000 min/mes; Fran pidió aviso a 1.800, 15-nov).

Suma los minutos de las corridas del mes (cada corrida cuenta mínimo 1 min, redondeando hacia arriba)
y decide si la tarea actual corre. Escribe corre=true/false en $GITHUB_OUTPUT.
  Uso: python3 scripts/presupuesto.py <escaneo|escaneo_opcional|reloj|otro>
Reglas: escaneo_opcional solo si el gasto va por debajo del ritmo del mes (tope × día / días del mes);
escaneo se salta desde 1.900 min; reloj y lo demás desde 1.950 min. Las corridas manuales siempre corren.
"""
import calendar, datetime as dt, json, math, os, subprocess, sys

TOPE = 2000
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
    corre = usado < ritmo and usado < 1900
elif tipo == "escaneo":
    corre = usado < 1900
else:
    corre = usado < 1950
# 19-nov (Fran eligió "recortar a 1 escaneo diario" para no pasar 2.000 min en noviembre): hasta fin de mes solo
# corre el escaneo programado de las 9:07 AM Bogotá (cron "7 14 * * *"); el resto de programados (otros escaneos,
# reloj 1:07 AM, muertos 1:23 AM) se salta. Las corridas manuales siguen corriendo. Se apaga solo el 1-dic.
if not manual and hoy.strftime("%Y-%m") == "2026-11" and hoy.day >= 19:
    try:
        cron = json.load(open(os.environ.get("GITHUB_EVENT_PATH", ""))).get("schedule", "")
    except Exception:
        cron = ""
    if not (tipo.startswith("escaneo") and cron == "7 14 * * *"):
        print(f"modo 1 escaneo diario (Fran 19-nov): {tipo} {cron!r} se salta")
        corre = False
    else:
        corre = usado < 1990  # el único escaneo del día aguanta hasta casi el tope
# 17-nov: si GitHub dispara el programado tarde y el guardián ya lanzó uno a mano, no repetir (choque al subir datos).
if corre and not manual and tipo.startswith("escaneo"):
    r = subprocess.run(["gh", "api", f"repos/{repo}/actions/workflows/escaneo.yml/runs?per_page=5"], capture_output=True, text=True)
    if r.returncode == 0:
        for x in json.loads(r.stdout).get("workflow_runs", []):
            t = dt.datetime.fromisoformat(x["created_at"].replace("Z", "+00:00"))
            if str(x["id"]) != os.environ.get("GITHUB_RUN_ID") and (hoy - t).total_seconds() < 45 * 60:
                print(f"ya hubo un escaneo hace {(hoy - t).total_seconds() / 60:.0f} min (corrida {x['id']}): este se salta")
                corre = False
                break
print(f"uso del mes {usado} min | ritmo hoy {ritmo:.0f} | tope {TOPE} | {tipo}: {'corre' if corre else 'SE SALTA'}")
# Aviso a Fran (issue de GitHub, le llega por correo/app) al cruzar 800 y 950 min, una vez por mes cada uno
mes = hoy.strftime("%Y-%m")
for umbral in (1500, 1800):
    if usado is not None and usado >= umbral:
        titulo = f"Minutos GitHub {mes}: pasamos {umbral} de {TOPE}"
        r = subprocess.run(["gh", "api", f"repos/{repo}/issues?state=all&per_page=50"], capture_output=True, text=True)
        ya = r.returncode == 0 and any(i.get("title") == titulo for i in json.loads(r.stdout))
        if r.returncode == 0 and not ya:
            cuerpo = (f"Uso del mes: {usado} min (ritmo esperado hoy: {ritmo:.0f}). Tope: {TOPE} min.\n\n"
                      "Desde 1.900 el freno salta los escaneos; desde 1.950, el reloj y lo demás. Las corridas manuales siempre corren.")
            subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", titulo, "--body", cuerpo])

if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"corre={'true' if corre else 'false'}\n")
