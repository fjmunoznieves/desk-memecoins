// Receptor de webhooks (solo lectura, paper). 19-nov, Fran: vigilancia en tiempo real para medir H34.
// POST /webhook : Helius (enhanced, SWAP) de 30 billeteras; exige header Authorization = WEBHOOK_AUTH.
// POST /alchemy : Alchemy Address Activity (Solana) de las 227 A; exige firma X-Alchemy-Signature (HMAC con ALCHEMY_SIGNING_KEY).
// Cada PRIMERA compra de un token por una billetera vigilada se guarda en D1 (tabla det) con precio/MC/liq/edad de DexScreener.
// Cron cada minuto (19-nov): sondeo de las 227 A por el RPC gratis de Shyft (sin cupo, 10 req/s): firmas nuevas → compra.
// GET /eventos : detecciones de los últimos 14 días (datos públicos de la cadena). Cron cada minuto: precio de DexScreener.
import { A } from "./billeteras.js";
const BASES = new Set([
  "So11111111111111111111111111111111111111112",
  "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
]);
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "POST" && url.pathname === "/webhook") {
      if (req.headers.get("Authorization") !== env.WEBHOOK_AUTH) return new Response("no", { status: 401 });
      let txs = [];
      try { txs = await req.json(); } catch (e) { return new Response("ok"); }
      for (const tx of Array.isArray(txs) ? txs : []) {
        try { await helius(tx, env); } catch (e) {}
      }
      return new Response("ok");
    }
    if (req.method === "POST" && url.pathname === "/alchemy") {
      await contar(env, "alchemy_llega");
      const cuerpo = await req.text();
      await contar(env, cuerpo.length > 200000 ? "alchemy_cuerpo_grande" : "alchemy_cuerpo_normal");
      if (!env.ALCHEMY_SIGNING_KEY || !(await firmaOk(cuerpo, req.headers.get("X-Alchemy-Signature") || "", env.ALCHEMY_SIGNING_KEY))) {
        await contar(env, "alchemy_firma_mala");
        return new Response("no", { status: 401 });
      }
      await contar(env, "alchemy_recibido");
      try { await alchemy(JSON.parse(cuerpo), env); await contar(env, "alchemy_ok"); } catch (e) { await contar(env, "alchemy_error"); }
      return new Response("ok");
    }
    if (req.method === "GET" && url.pathname === "/eventos") {
      const r = await env.DB.prepare("SELECT * FROM det WHERE ts_det > ? ORDER BY ts_det LIMIT 20000").bind(ahora() - 14 * 86400).all();
      return Response.json(r.results || []);
    }
    if (req.method === "GET" && url.pathname === "/muestra") {
      const r = await env.DB.prepare("SELECT ts, cuerpo FROM muestra ORDER BY id DESC LIMIT 5").all();
      return Response.json(r.results || []);
    }
    if (req.method === "GET" && url.pathname === "/estado") {
      const r = await env.DB.prepare("SELECT COUNT(*) n, SUM(mc IS NOT NULL) con_precio, SUM(mc IS NULL AND COALESCE(intentos,0) >= 6) sin_dex, SUM(fuente='alchemy') alchemy, SUM(fuente='helius') helius, SUM(fuente='shyft') shyft, MAX(ts_det) ultimo, MAX(ts_precio) ultimo_precio FROM det").first();
      let err = "";
      try { await completar(env); } catch (e) { err = String(e).slice(0, 300); }
      const c = await env.DB.prepare("SELECT k, n, ts FROM stats").all();
      return Response.json({ ...r, ahora: ahora(), error_completar: err, contadores: c.results || [] });
    }
    return new Response("ok");
  },
  // Cada minuto: completa precio/MC/liq/edad (DexScreener) de las detecciones nuevas. Se separa del aviso porque el plan
  // gratis limita la CPU por petición y un aviso grande de Alchemy no alcanzaba a consultar DexScreener.
  async scheduled(evento, env, ctx) {
    if (env.SHYFT_API_KEY) { try { await sondear(env); } catch (e) { await contar(env, "shyft_error_otro"); } }
    await completar(env);
  },
};
async function completar(env) {
  // hasta 30 detecciones de los últimos 15 min sin precio, en UNA consulta a DexScreener (acepta 30 tokens por llamada)
  const r = await env.DB.prepare("SELECT mint FROM det WHERE mc IS NULL AND COALESCE(intentos, 0) < 6 AND ts_det > ? ORDER BY ts_det DESC LIMIT 30")
    .bind(ahora() - 900).all();
  const mints = (r.results || []).map((x) => x.mint);
  if (!mints.length) return;
  let d = [];
  try { d = await (await fetch("https://api.dexscreener.com/tokens/v1/solana/" + mints.join(","))).json(); } catch (e) { d = []; }
  const mejor = new Map();
  for (const p of Array.isArray(d) ? d : []) {
    const t = (p.baseToken || {}).address;
    if (!t) continue;
    const q = mejor.get(t);
    if (!q || ((p.liquidity || {}).usd || 0) > ((q.liquidity || {}).usd || 0)) mejor.set(t, p);
  }
  const ops = [];
  for (const m of mints) {
    const p = mejor.get(m);
    if (p) ops.push(env.DB.prepare("UPDATE det SET sym = ?, precio = ?, mc = ?, liq = ?, pool = ?, creado = ?, ts_precio = ? WHERE mint = ?")
      .bind(((p.baseToken || {}).symbol || "").slice(0, 20), String(p.priceUsd || ""), Math.round(p.marketCap || p.fdv || 0),
            Math.round((p.liquidity || {}).usd || 0), p.pairAddress || "", p.pairCreatedAt || 0, ahora(), m));
    else ops.push(env.DB.prepare("UPDATE det SET intentos = COALESCE(intentos, 0) + 1 WHERE mint = ?").bind(m));
  }
  await env.DB.batch(ops);
}
const ahora = () => Math.floor(Date.now() / 1000);
async function contar(env, k) {
  try { await env.DB.prepare("INSERT INTO stats(k, n, ts) VALUES (?, 1, ?) ON CONFLICT(k) DO UPDATE SET n = n + 1, ts = excluded.ts").bind(k, ahora()).run(); } catch (e) {}
}
async function firmaOk(cuerpo, firma, clave) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(clave), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const s = new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(cuerpo)));
  const hex = [...s].map((b) => b.toString(16).padStart(2, "0")).join("");
  return hex === firma.toLowerCase();
}
async function helius(tx, env) {
  const w = tx.feePayer;
  if (!w || tx.transactionError) return;
  const compras = new Set();
  for (const t of tx.tokenTransfers || []) if (t.toUserAccount === w && t.mint && !BASES.has(t.mint)) compras.add(t.mint);
  for (const mint of compras) await registrar(env, mint, w, tx.timestamp || ahora(), tx.signature || "", "helius");
}
// Alchemy Solana: recorre el JSON buscando transacciones con saldos de tokens antes/después; compra = el dueño vigilado sube su saldo del mint.
async function alchemy(j, env) {
  const vistos = [];
  const rec = (o, sig, ts) => {
    if (!o || typeof o !== "object") return;
    if (Array.isArray(o)) { for (const x of o) rec(x, sig, ts); return; }
    if (typeof o.signature === "string") sig = o.signature;
    if (Array.isArray(o.signatures) && typeof o.signatures[0] === "string") sig = sig || o.signatures[0];
    const bt = o.block_time ?? o.blockTime ?? o.timestamp;
    if (typeof bt === "number") ts = bt > 1e12 ? Math.floor(bt / 1000) : bt;
    const pre = o.pre_token_balances ?? o.preTokenBalances, post = o.post_token_balances ?? o.postTokenBalances;
    if (Array.isArray(pre) && Array.isArray(post)) vistos.push({ pre, post, sig, ts });
    for (const k in o) if (o[k] && typeof o[k] === "object") rec(o[k], sig, ts);
  };
  rec(j, "", 0);
  const cant = (b) => { const u = b.ui_token_amount ?? b.uiTokenAmount ?? {}; return Number(u.amount ?? 0); };
  for (const v of vistos) {
    const suma = (lista) => { const m = new Map(); for (const b of lista) { if (!A.has(b.owner)) continue; const k = b.owner + "|" + b.mint; m.set(k, (m.get(k) || 0) + cant(b)); } return m; };
    const a = suma(v.pre), d = suma(v.post);
    for (const [k, q] of d) {
      const [w, mint] = k.split("|");
      if (q > (a.get(k) || 0) && !BASES.has(mint)) await registrar(env, mint, w, v.ts || ahora(), v.sig, "alchemy");
    }
  }
}
async function registrar(env, mint, w, ts_tx, firma, fuente) {
  // solo cuenta la primera compra de cada token; el precio lo completa el cron de cada minuto
  await env.DB.prepare("INSERT OR IGNORE INTO det(mint, billetera, ts_tx, ts_det, firma, fuente) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(mint, w, ts_tx, ahora(), String(firma).slice(0, 100), fuente).run();
}
async function precio(env, mint) {
  try {
    const d = await (await fetch("https://api.dexscreener.com/tokens/v1/solana/" + mint)).json();
    if (Array.isArray(d) && d.length) {
      const p = d.reduce((x, y) => (((y.liquidity || {}).usd || 0) > ((x.liquidity || {}).usd || 0) ? y : x));
      await env.DB.prepare("UPDATE det SET sym = ?, precio = ?, mc = ?, liq = ?, pool = ?, creado = ?, ts_precio = ? WHERE mint = ?")
        .bind(((p.baseToken || {}).symbol || "").slice(0, 20), String(p.priceUsd || ""), Math.round(p.marketCap || p.fdv || 0),
              Math.round((p.liquidity || {}).usd || 0), p.pairAddress || "", p.pairCreatedAt || 0, ahora(), mint).run();
      return;
    }
  } catch (e) {}
  await env.DB.prepare("UPDATE det SET intentos = COALESCE(intentos, 0) + 1 WHERE mint = ?").bind(mint).run();
}

// ---- Sondeo Shyft (19-nov) ----
const MAX_TX = 30; // tope de transacciones leídas por minuto (CPU del plan gratis); el resto se cuenta como saltada
async function rpc(env, lote) {
  const r = await fetch("https://rpc.shyft.to?api_key=" + env.SHYFT_API_KEY, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lote) });
  if (!r.ok) throw new Error("shyft " + r.status);
  const d = await r.json();
  return Array.isArray(d) ? d : [d];
}
async function sumar(env, k, n) {
  if (!n) return;
  try { await env.DB.prepare("INSERT INTO stats(k, n, ts) VALUES (?, ?, ?) ON CONFLICT(k) DO UPDATE SET n = n + excluded.n, ts = excluded.ts").bind(k, n, ahora()).run(); } catch (e) {}
}
async function sondear(env) {
  // Regla de bots del desk (operadores.tsv): >200 operaciones al día = bot. Se cuenta por billetera y día UTC;
  // pasada esa cifra se siguen avanzando sus firmas pero no se leen sus transacciones (19-nov: is6MTR ~250/h).
  const ws = [...A], dia = Math.floor(ahora() / 86400);
  const u = await env.DB.prepare("SELECT w, sig, dia, cnt FROM ult").all();
  const ult = new Map((u.results || []).map((x) => [x.w, x]));
  const nuevas = [], upd = [], dbg = [];
  let bots = 0;
  for (let i = 0; i < ws.length; i += 50) {
    const parte = ws.slice(i, i + 50);
    let res = [];
    try {
      res = await rpc(env, parte.map((w, j) => {
        const o = { limit: 15 }; const x = ult.get(w); if (x && x.sig) o.until = x.sig;
        return { jsonrpc: "2.0", id: j, method: "getSignaturesForAddress", params: [w, o] };
      }));
    } catch (e) { await contar(env, "shyft_error_firmas"); dbg.push({ err_firmas: String(e).slice(0, 200) }); continue; }
    for (const x of res) {
      const w = parte[x.id]; let l = x.result;
      if (!w || !Array.isArray(l) || !l.length) continue;
      const prev = ult.get(w) || {};
      // Shyft no respeta "until": se corta a mano en la última firma ya vista (y por tiempo, por si no aparece)
      const k = prev.sig ? l.findIndex((s) => s.signature === prev.sig) : -1;
      if (dbg.length < 6 && prev.sig) dbg.push({ w: w.slice(0, 6), n: l.length, k, t0: l[0].blockTime, tN: l[l.length - 1].blockTime, pts: prev.ts });
      if (k >= 0) l = l.slice(0, k);
      else if (prev.ts) l = l.filter((s) => (s.blockTime || 0) >= prev.ts - 120);
      if (!l.length) continue;
      const ok = l.filter((s) => s.err == null);
      const cnt = (prev.dia === dia ? prev.cnt || 0 : 0) + l.length;
      upd.push(env.DB.prepare("INSERT INTO ult(w, sig, ts, dia, cnt) VALUES (?, ?, ?, ?, ?) ON CONFLICT(w) DO UPDATE SET sig = excluded.sig, ts = excluded.ts, dia = excluded.dia, cnt = excluded.cnt")
        .bind(w, l[0].signature, ahora(), dia, cnt));
      if (!prev.sig) continue; // primera vez: solo fija el punto de partida
      if (cnt > 200) { bots += ok.length; continue; }
      for (const s of ok) nuevas.push({ w, sig: s.signature, ts: s.blockTime || ahora() });
    }
  }
  if (upd.length) await env.DB.batch(upd);
  await sumar(env, "shyft_minutos", 1);
  await sumar(env, "shyft_tx_nuevas", nuevas.length);
  await sumar(env, "shyft_tx_bots", bots);
  await sumar(env, "shyft_saltadas", Math.max(0, nuevas.length - MAX_TX));
  const leer = nuevas.slice(0, MAX_TX);
  for (let i = 0; i < leer.length; i += 15) {
    const parte = leer.slice(i, i + 15);
    let res = [];
    try {
      res = await rpc(env, parte.map((n, j) => ({ jsonrpc: "2.0", id: j, method: "getTransaction",
        params: [n.sig, { encoding: "json", maxSupportedTransactionVersion: 0, commitment: "confirmed" }] })));
    } catch (e) { await contar(env, "shyft_error_tx"); dbg.push({ err_tx: String(e).slice(0, 200) }); continue; }
    const malos = res.filter((x) => x.error);
    if (malos.length) dbg.push({ err_items: malos.length, e: JSON.stringify(malos[0].error).slice(0, 200) });
    for (const x of res) {
      const n = parte[x.id];
      if (n && x.result) await compraShyft(env, x.result, n);
    }
  }
  await sumar(env, "shyft_tx_leidas", leer.length);
  dbg.push({ nuevas: nuevas.length, bots });
  await env.DB.prepare("INSERT INTO muestra(ts, cuerpo) VALUES (?, ?)").bind(ahora(), JSON.stringify(dbg)).run();
  await env.DB.prepare("DELETE FROM muestra WHERE ts < ?").bind(ahora() - 3600).run();
}
// misma regla que watch_solana.compra_de: recibe un token no base sin entregar otro no base, y gasta ≥0,05 SOL o entrega USDC/USDT
async function compraShyft(env, t, n) {
  const meta = t.meta || {};
  if (meta.err != null) return;
  const w = n.w, dif = new Map();
  for (const [lado, sg] of [["preTokenBalances", -1], ["postTokenBalances", 1]])
    for (const b of meta[lado] || []) {
      if (b.owner !== w) continue;
      dif.set(b.mint, (dif.get(b.mint) || 0) + sg * Number((b.uiTokenAmount || {}).uiAmount || 0));
    }
  const recibe = [...dif].filter(([m, v]) => !BASES.has(m) && v > 0).map(([m]) => m);
  const entrega = [...dif].some(([m, v]) => !BASES.has(m) && v < 0);
  if (!recibe.length || entrega) return;
  const ks = ((t.transaction || {}).message || {}).accountKeys || [];
  const i = ks.indexOf(w);
  let sol = i >= 0 ? Math.max(0, ((meta.preBalances || [])[i] - (meta.postBalances || [])[i]) / 1e9 || 0) : 0;
  sol += Math.max(0, -(dif.get("So11111111111111111111111111111111111111112") || 0));
  const baseOut = [...dif].some(([m, v]) => BASES.has(m) && v < 0);
  if (sol < 0.05 && !baseOut) return;
  await contar(env, "shyft_compras");
  for (const m of recibe) await registrar(env, m, w, t.blockTime || n.ts, n.sig, "shyft");
}
