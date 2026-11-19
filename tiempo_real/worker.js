// Receptor de webhooks de Helius (solo lectura, paper). 19-nov, Fran: vigilancia en tiempo real para medir H34.
// POST /webhook  : Helius envía transacciones (enhanced, tipo SWAP) de las billeteras vigiladas.
//                  Si una billetera compra un token que el Worker no había visto, consulta DexScreener y guarda
//                  la detección (precio, MC, liquidez, edad del pool) en KV, una sola clave por token.
// GET  /eventos  : lista de detecciones (lo lee el escaneo de GitHub; datos públicos de la cadena, sin clave).
// POST exige el header Authorization que Helius repite en cada envío.
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
        try { await procesar(tx, env); } catch (e) { /* un error no debe hacer reintentar a Helius */ }
      }
      return new Response("ok");
    }
    if (req.method === "GET" && url.pathname === "/eventos") {
      const out = [];
      let cursor;
      do {
        const r = await env.H34.list({ prefix: "m:", cursor });
        for (const k of r.keys) if (k.metadata) out.push(k.metadata);
        cursor = r.list_complete ? undefined : r.cursor;
      } while (cursor);
      return Response.json(out);
    }
    return new Response("ok");
  },
};
async function procesar(tx, env) {
  const w = tx.feePayer;
  if (!w || tx.transactionError) return;
  const compras = new Set();
  for (const t of tx.tokenTransfers || []) {
    if (t.toUserAccount === w && t.mint && !BASES.has(t.mint)) compras.add(t.mint);
  }
  for (const mint of compras) {
    const key = "m:" + mint;
    if (await env.H34.get(key) !== null) continue;  // ya visto: solo cuenta la primera compra
    const md = { mint, billetera: w, ts_tx: tx.timestamp || 0, ts_det: Math.floor(Date.now() / 1000), firma: (tx.signature || "").slice(0, 88) };
    try {
      const r = await fetch("https://api.dexscreener.com/tokens/v1/solana/" + mint);
      const d = await r.json();
      if (Array.isArray(d) && d.length) {
        const p = d.reduce((a, b) => (((b.liquidity || {}).usd || 0) > ((a.liquidity || {}).usd || 0) ? b : a));
        md.sym = ((p.baseToken || {}).symbol || "").slice(0, 20);
        md.precio = p.priceUsd; md.mc = Math.round(p.marketCap || p.fdv || 0);
        md.liq = Math.round((p.liquidity || {}).usd || 0);
        md.pool = p.pairAddress; md.creado = p.pairCreatedAt || 0;
      }
    } catch (e) { md.error = "dexscreener"; }
    await env.H34.put(key, "1", { metadata: md, expirationTtl: 60 * 60 * 24 * 14 });
  }
}
