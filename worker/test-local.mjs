// Local harness: prove the Worker's signing path against testnet before deploying anything.
//
//   node worker/test-local.mjs
//
// It reads the same key the keeper uses, reads the contract, waits for an epoch to be due, and ticks.

import { readFileSync } from "node:fs";
import { call, view } from "./src/near.js";

const RPC = "https://rpc.testnet.fastnear.com";
const saved = JSON.parse(readFileSync(new URL("../demo/canonical-account.json", import.meta.url), "utf8"));
const contractId = process.argv[2] || saved.accountId;

const state = () => view({ rpcUrl: RPC, contractId, method: "get_state" });

let s = await state();
const dueAt = Number(BigInt(s.epoch_start) + BigInt(s.epoch_length_ns)) / 1e6;
console.log(`epoch ${s.epoch}, supply ${Number(BigInt(s.total_supply) / 10n ** 18n).toLocaleString()}`);
console.log(`due ${((dueAt - Date.now()) / 1000).toFixed(1)}s from now`);

const wait = Math.max(0, dueAt - Date.now()) + 1500;
if (wait > 0) {
  console.log(`waiting ${(wait / 1000).toFixed(1)}s`);
  await new Promise((r) => setTimeout(r, wait));
}

const out = await call({
  rpcUrl: RPC,
  signerId: saved.accountId,
  secretKey: saved.secretKey,
  contractId,
  method: "tick",
});

console.log("tx:", out.tx, "| ok:", out.ok, "| gas:", out.gas);
if (!out.ok) {
  console.log("status:", out.status);
  process.exit(1);
}

s = await state();
console.log(`epoch now ${s.epoch} (was ${s.epoch - 1} or more), history ${s.history.length}`);
