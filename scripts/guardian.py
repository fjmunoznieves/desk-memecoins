"""Guardián sin Claude: si una corrida programada no se creó ~15 min después de su hora, la dispara a mano.
escaneo: 08:47, 14:07, 20:47 UTC (17:27 es opcional, no se vigila). reloj: 06:07 UTC."""
import json, os, urllib.request, datetime as dt

REPO = os.environ["GITHUB_REPOSITORY"]
TOK = os.environ["GH_TOKEN"]
SLOTS = {"escaneo.yml": [(8, 47), (14, 7), (20, 47)], "reloj.yml": [(6, 7)]}


def api(path, data=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}",
                                 data=json.dumps(data).encode() if data else None,
                                 headers={"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json"},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
        return json.loads(b) if b else {}


now = dt.datetime.now(dt.timezone.utc)
for wf, slots in SLOTS.items():
    pasados = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in slots]
    pasados = [t if t <= now else t - dt.timedelta(days=1) for t in pasados]
    slot = max(pasados)
    # 25-nov: GitHub atrasó también al guardián (corrió 3-4 h tarde y no aplicaba). Ventana 12 h; ahora además corre
    # cada 15 min dentro de la escucha (casi continua). Solo dispara si pasaron 15 min desde la hora programada.
    if now - slot > dt.timedelta(hours=12) or now - slot < dt.timedelta(minutes=15):
        print(f"{wf}: último horario {slot:%H:%M}, fuera de ventana"); continue
    runs = api(f"actions/workflows/{wf}/runs?per_page=5")["workflow_runs"]
    desde = slot - dt.timedelta(minutes=10)
    ok = [r for r in runs if dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= desde]
    if ok:
        print(f"{wf}: corrida {ok[0]['id']} ({ok[0]['event']}, {ok[0]['status']}) desde {slot:%H:%M} → ok")
    else:
        api(f"actions/workflows/{wf}/dispatches", {"ref": "main"})
        print(f"{wf}: sin corrida desde {slot:%H:%M} → DISPARADA a mano")
