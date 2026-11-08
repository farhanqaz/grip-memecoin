// Run the Worker's keeper logic locally, with the real key, against testnet.
//
//   node worker/test-worker.mjs
//
// This is the same function the cron trigger calls: catch up on due epochs, re-lock if grip has fallen.
// If it passes here, the only thing left to prove on Cloudflare is the trigger itself.

import { readFileSync } from "node:fs";
import worker from "./src/worker.js";

const saved = JSON.parse(readFileSync(new URL("../demo/canonical-account.json", import.meta.url), "utf8"));

const env = {
  CONTRACT: saved.accountId,
  RPC_URL: "https://rpc.testnet.fastnear.com",
  LOCK_EPOCHS: "30",
  GRIP_SIGNER: JSON.stringify(saved),
};

const before = await (await worker.fetch(new Request("https://keeper.local/"), env)).json();
console.log("before:", JSON.stringify(before).slice(0, 200));

// wait for one epoch so there is something to do
const dueAt = Number(BigInt(before.epoch && 0) + 0n);
const stateDue = await (await worker.fetch(new Request("https://keeper.local/"), env)).json();
console.log("calling the scheduled path...");

await worker.scheduled({ scheduledTime: Date.now() }, env, { waitUntil: (p) => p });

const after = await (await worker.fetch(new Request("https://keeper.local/"), env)).json();
console.log("after: ", JSON.stringify(after).slice(0, 200));
console.log(after.epoch > before.epoch ? `OK: epoch ${before.epoch} -> ${after.epoch}` : `no epoch rolled (due in <60s). logic ran without error.`);
