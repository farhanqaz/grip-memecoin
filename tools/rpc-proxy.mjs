// Local CORS-safe proxy to a NEAR RPC. Only needed when the browser running the dashboard
// cannot reach the RPC directly (sandboxed preview, offline CI, strict firewall).
//
//   node tools/rpc-proxy.mjs            # then open http://localhost:8765/index.html?rpc=http://localhost:8799
//
// Forwards any POST body to UPSTREAM unchanged and returns the response untouched.

import { createServer } from 'node:http';

const UPSTREAM = process.env.RPC_UPSTREAM || 'https://rpc.testnet.fastnear.com';
const PORT = Number(process.env.RPC_PROXY_PORT || 8799);

createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST,OPTIONS');
  if (req.method === 'OPTIONS') {
    res.writeHead(204).end();
    return;
  }
  const chunks = [];
  for await (const c of req) chunks.push(c);
  try {
    const upstream = await fetch(UPSTREAM, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: Buffer.concat(chunks),
    });
    const text = await upstream.text();
    res.writeHead(upstream.status, { 'Content-Type': 'application/json' }).end(text);
  } catch (e) {
    res.writeHead(502, { 'Content-Type': 'application/json' }).end(JSON.stringify({ error: String(e) }));
  }
}).listen(PORT, () => console.log(`proxying POST :${PORT} -> ${UPSTREAM}`));
