// Keeper: calls the permissionless tick() when an epoch is due.
//
//   node keeper.mjs            # loop forever, one tick per due epoch
//   node keeper.mjs --once     # one check, exit — use this from cron
//
// The contract cannot tick itself and does not need anyone's permission to be ticked. This script is
// the whole keeper: it holds no special key and has no power the burn rule does not already have.
// If it stops, nothing is lost — the next tick rolls up to 12 elapsed epochs at once.

import { readFileSync } from 'node:fs';
import { JsonRpcProvider, Account } from 'near-api-js';
import { viewCall } from './rpc.mjs';

const TGAS = 1_000_000_000_000n;
const once = process.argv.includes('--once');
const saved = JSON.parse(readFileSync(new URL(process.env.STATE_FILE || './demo-account.json', import.meta.url), 'utf8'));
const { secretKey } = saved;
// The signer only pays for gas: tick() is permissionless, so the keeper can drive any deployment.
// CONTRACT is what gets ticked; SIGNER is the funded account that signs (defaults to the local key's own).
const contractId = process.env.CONTRACT || saved.accountId;
const signerId = process.env.SIGNER || saved.accountId;
const provider = new JsonRpcProvider({ url: 'https://rpc.testnet.fastnear.com' });
const account = new Account(signerId, provider, secretKey);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function step() {
  const s = await viewCall(contractId, 'get_state');
  const dueAt = Number(BigInt(s.epoch_start) + BigInt(s.epoch_length_ns));
  if (Date.now() * 1e6 < dueAt) {
    return { ticked: false, epoch: s.epoch, waitMs: Math.ceil((dueAt - Date.now() * 1e6) / 1e6) };
  }
  await account.callFunction({ contractId, methodName: 'tick', args: {}, gas: 100n * TGAS, waitUntil: 'FINAL' });
  const after = await viewCall(contractId, 'get_state');
  const last = after.history[after.history.length - 1];
  return { ticked: true, epoch: after.epoch, action: last?.action, supply: after.total_supply, grip: after.locked_share_bps };
}

if (once) {
  const r = await step();
  console.log(r.ticked ? `ticked -> epoch ${r.epoch}: ${r.action}` : `not due (epoch ${r.epoch}, ${Math.round(r.waitMs / 1000)}s left)`);
  process.exit(0);
}

console.log(`keeper watching ${contractId} (signer ${signerId})`);
for (;;) {
  try {
    const r = await step();
    if (r.ticked) console.log(`epoch ${r.epoch}: ${r.action} | grip ${(r.grip / 100).toFixed(1)}% | supply ${Number(BigInt(r.supply) / 10n ** 18n).toLocaleString()}`);
    else console.log(`  not due, ${Math.round(r.waitMs / 1000)}s left`);
  } catch (e) {
    console.error('tick failed:', e.message.slice(0, 120));
  }
  await sleep(15000);
}
