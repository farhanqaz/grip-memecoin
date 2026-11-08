// GRIP keeper, on a Cloudflare cron trigger.
//
// The rule is permissionless, not autonomous: an epoch only advances when someone calls tick(). This
// Worker is that someone. It calls two public methods and nothing else, and the key it holds has no
// power over the contract, because there is no admin method, no pause, no setter, no upgrade path.
//
//   GET /        -> the current state, so the deployment can be eyeballed
//   GET /run     -> tick now, if x-token matches TRIGGER_TOKEN

import { call, view } from "./near.js";

const RPC = "https://rpc.testnet.fastnear.com";
const MAX_TICKS_PER_RUN = 3; // enough for a 10 minute backlog, and it keeps the gas bill sane

const due = (s) => Date.now() >= Number(BigInt(s.epoch_start) + BigInt(s.epoch_length_ns)) / 1e6;

/** The signing key lives in one secret, as the same JSON shape the local keeper reads. */
function signerFrom(env) {
  if (env.GRIP_SIGNER) {
    const j = JSON.parse(env.GRIP_SIGNER);
    return { accountId: j.accountId, secretKey: j.secretKey };
  }
  return { accountId: env.SIGNER, secretKey };
}

async function keeper(env) {
  const rpcUrl = env.RPC_URL || RPC;
  const contractId = env.CONTRACT;
  const { accountId: signerId, secretKey } = signerFrom(env);

  let s = await view({ rpcUrl, contractId, method: "get_state" });
  const out = { startedAt: new Date().toISOString(), epochStart: s.epoch, ticks: 0, relocked: false };

  // Catch up rather than tick once: a scheduled caller can be late, and one tick only rolls so much.
  for (let n = 0; n < MAX_TICKS_PER_RUN && due(s); n++) {
    const res = await call({ rpcUrl, signerId, secretKey, contractId, method: "tick" });
    out.ticks += 1;
    if (!res.ok) {
      out.error = res.status;
      break;
    }
    s = await view({ rpcUrl, contractId, method: "get_state" });
  }

  // If grip has fallen under the mint target, put the stand-in float back. That is the same call any
  // wallet could make; the dashboard says this account is scripted.
  if (s.locked_share_bps < s.lock_target_bps) {
    const free = await view({ rpcUrl, contractId, method: "ft_balance_of", args: { account_id: signerId } });
    if (BigInt(free) > 0n) {
      const res = await call({
        rpcUrl, signerId, secretKey, contractId,
        method: "lock",
        args: { amount: free, epochs: Number(env.LOCK_EPOCHS || 30) },
      });
      out.relocked = res.ok;
      if (res.ok) s = await view({ rpcUrl, contractId, method: "get_state" });
    }
  }

  out.epochEnd = s.epoch;
  out.supply = s.total_supply;
  out.gripBps = s.locked_share_bps;
  return out;
}

export default {
  async scheduled(event, env, ctx) {
    // one run per trigger; waitUntil keeps the invocation alive until the transactions finalise
    ctx.waitUntil(keeper(env).then((r) => console.log(JSON.stringify(r))));
  },

  async fetch(req, env) {
    const url = new URL(req.url);

    if (url.pathname === "/run") {
      if (!env.TRIGGER_TOKEN || req.headers.get("x-token") !== env.TRIGGER_TOKEN) {
        return new Response("forbidden\n", { status: 403 });
      }
      return Response.json(await keeper(env));
    }

    try {
      const s = await view({ rpcUrl: env.RPC_URL || RPC, contractId: env.CONTRACT, method: "get_state" });
      return Response.json({
        contract: env.CONTRACT,
        signer: signerFrom(env).accountId,
        epoch: s.epoch,
        supply: s.total_supply,
        reserve: s.reserve,
        grip_bps: s.locked_share_bps,
        last_actions: s.history.slice(-5).map((h) => h.action),
      });
    } catch (e) {
      return new Response("chain read failed: " + e.message + "\n", { status: 502 });
    }
  },
};
