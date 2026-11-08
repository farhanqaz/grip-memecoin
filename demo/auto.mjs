// Keeps the public demo instance alive, using only public methods.
//
//   node auto.mjs
//
// It does two things, both of which any wallet could do by hand:
//   1. tick() if an epoch is due and nobody has rolled it yet
//   2. re-lock the deployer's balance when the grip has fallen under the mint target
//
// Nothing here is privileged. The contract has no admin method for this, and none is needed: locking
// and ticking are public. What it does mean is that the locked share on the public instance is one
// scripted account maintaining the mechanic, not organic demand, which is why the dashboard says so.

import { readFileSync } from 'node:fs';
import { JsonRpcProvider, Account } from 'near-api-js';
import { viewCall } from './rpc.mjs';

const TGAS = 1_000_000_000_000n;
const STATE = new URL(process.env.STATE_FILE || './canonical-account.json', import.meta.url);
const saved = JSON.parse(readFileSync(STATE, 'utf8'));
const accountId = process.env.CONTRACT || saved.accountId;

const provider = new JsonRpcProvider({ url: 'https://rpc.testnet.fastnear.com' });
const account = new Account(saved.accountId, provider, saved.secretKey);

const state = () => viewCall(accountId, 'get_state');
const did = [];

let s = await state();

const dueAt = Number(BigInt(s.epoch_start) + BigInt(s.epoch_length_ns)) / 1e6;
if (Date.now() >= dueAt) {
  await account.callFunction({ contractId: accountId, methodName: 'tick', args: {}, gas: 100n * TGAS, waitUntil: 'FINAL' });
  s = await state();
  did.push(`ticked to epoch ${s.epoch}`);
}

if (s.locked_share_bps < s.lock_target_bps) {
  const free = BigInt(await viewCall(accountId, 'ft_balance_of', { account_id: saved.accountId }));
  if (free > 0n) {
    await account.callFunction({
      contractId: accountId,
      methodName: 'lock',
      args: { amount: free.toString(), epochs: Number(process.env.LOCK_EPOCHS || 30) },
      gas: 60n * TGAS,
      waitUntil: 'FINAL',
    });
    s = await state();
    did.push(`re-locked to grip ${(s.locked_share_bps / 100).toFixed(1)}%`);
  } else {
    did.push(`grip ${(s.locked_share_bps / 100).toFixed(1)}% and nothing free to lock`);
  }
}

// silence when there was nothing to do, so a cron wrapper only speaks when it acted
if (did.length) {
  console.log(`${accountId}: ${did.join(', ')} (epoch ${s.epoch}, supply ${Number(BigInt(s.total_supply) / 10n ** 18n).toLocaleString()})`);
}
