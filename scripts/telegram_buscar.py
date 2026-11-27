"""27-nov (Fran): busca contratos en canales públicos con la búsqueda web de Telegram (t.me/s/<canal>?q=<contrato>).
Entrada datos/telegram/x2_tokens.tsv (clave,...). Salida datos/telegram/x2_menciones.tsv (clave, canal, msg_id, hora)."""
import csv, re, time, urllib.request, sys, os
canales = [l.strip() for l in open("datos/telegram/canales.txt") if l.strip() and not l.startswith("#") and "RobinHood" not in l]
if os.environ.get("TG_CANALES"): canales = os.environ["TG_CANALES"].split(",")
toks = [r["clave"] for r in csv.DictReader(open(os.environ.get("TG_IN") or "datos/telegram/x2_tokens.tsv"), delimiter="\t")]
RUTA = os.environ.get("TG_OUT", "datos/telegram/x2_menciones.tsv")
out = open(RUTA, "w"); out.write("clave\tcanal\tmsg_id\thora\n"); n = 0; err = 0
for i, k in enumerate(toks):
    for c in canales:
        try:
            s = urllib.request.urlopen(urllib.request.Request(f"https://t.me/s/{c}?q={k}", headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode("utf8", "ignore")
        except Exception as e:
            err += 1; time.sleep(5); continue
        for b in s.split('class="tgme_widget_message_wrap')[1:]:
            if k not in b: continue
            mid = (re.search(r'data-post="[^/]+/(\d+)"', b) or [None, ""])[1]; h = (re.search(r'datetime="([^"]+)"', b) or [None, ""])[1]
            out.write(f"{k}\t{c}\t{mid}\t{h}\n"); n += 1
        time.sleep(0.6)
    if i % 25 == 0: print(i, "tokens, menciones", n, "errores", err, flush=True)
out.close(); print("fin: menciones", n, "errores", err)
