"""27-nov (Fran): lee canales PÚBLICOS de Telegram por su versión web (t.me/s/<canal>), sin cuenta, solo lectura.
Guarda cada contrato mencionado (Solana / EVM) con canal, hora del mensaje y texto corto → datos/telegram/menciones.tsv (sin duplicados).
Canales en datos/telegram/canales.txt (uno por línea)."""
import csv, html, os, re, sys, time, urllib.request
os.makedirs("datos/telegram", exist_ok=True)
CAN = "datos/telegram/canales.txt"; OUT = "datos/telegram/menciones.tsv"
canales = [l.strip().lstrip("@") for l in open(CAN) if l.strip() and not l.startswith("#")] if os.path.exists(CAN) else []
SOL = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"); EVM = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
ya = set()
if os.path.exists(OUT):
    ya = {(r["canal"], r["msg_id"], r["contrato"]) for r in csv.DictReader(open(OUT), delimiter="\t")}
nuevo = not os.path.exists(OUT)
f = open(OUT, "a", newline=""); w = csv.writer(f, delimiter="\t")
if nuevo: w.writerow(["visto_ts", "canal", "msg_id", "msg_utc", "contrato", "tipo", "texto"])
n = 0
for c in canales:
    try:
        s = urllib.request.urlopen(urllib.request.Request(f"https://t.me/s/{c}", headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read().decode("utf8", "ignore")
    except Exception as e:
        print("canal", c, "falló:", str(e)[:80]); continue
    bloques = s.split('class="tgme_widget_message_wrap')[1:]
    print(f"canal {c}: {len(bloques)} mensajes visibles")
    for b in bloques:
        mid = (re.search(r'data-post="[^/]+/(\d+)"', b) or [None, ""])[1]
        hora = (re.search(r'datetime="([^"]+)"', b) or [None, ""])[1]
        txt = html.unescape(re.sub(r"<[^>]+>", " ", b))
        txt += " " + " ".join(re.findall(r'href="([^"]+)"', b))
        cs = {(x, "evm") for x in EVM.findall(txt)} | {(x, "sol") for x in SOL.findall(txt) if not x.startswith("0x") and any(ch.isdigit() for ch in x)}
        for x, t in cs:
            if (c, mid, x) in ya: continue
            ya.add((c, mid, x)); n += 1
            w.writerow([int(time.time()), c, mid, hora, x, t, " ".join(txt.split())[:160]])
f.close(); print("menciones nuevas:", n)
