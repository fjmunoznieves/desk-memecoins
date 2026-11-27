"""Prueba candidatos de canales públicos: ¿se leen en t.me/s? ¿cuántos mensajes y contratos Solana/EVM? ¿hora del último?"""
import re, urllib.request, html, time
SOL = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"); EVM = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
for c in [l.strip() for l in open("datos/telegram/candidatos.txt") if l.strip()]:
    try:
        s = urllib.request.urlopen(urllib.request.Request(f"https://t.me/s/{c}", headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode("utf8", "ignore")
    except Exception as e:
        print(f"{c}\tERROR\t{str(e)[:50]}"); continue
    b = s.split('class="tgme_widget_message_wrap')[1:]
    subs = (re.search(r'tgme_page_extra">([^<]+)', s) or re.search(r'counter_value">([^<]+)</span>\s*<span class="counter_type">subscribers', s) or [None, "?"])[1]
    horas = re.findall(r'datetime="([^"]+)"', s)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", s)) + " ".join(re.findall(r'href="([^"]+)"', s))
    sol = {x for x in SOL.findall(txt) if any(ch.isdigit() for ch in x)}; evm = set(EVM.findall(txt))
    print(f"{c}\tmsgs {len(b)}\tsubs {subs.strip()}\tsol {len(sol)}\tevm {len(evm)}\tprimero {horas[0] if horas else '-'}\tultimo {horas[-1] if horas else '-'}")
    time.sleep(1)
