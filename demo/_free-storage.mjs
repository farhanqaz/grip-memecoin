// One-off migration: recover the storage deposit from the instance that cannot be upgraded.
//
// The contract has no update path by design, so the only way to ship a fixed build is a new account. That
// costs about 2.7 NEAR of storage for the wasm, and the parent account has 0.36. This script removes the
// code from the old instance (an empty deploy refunds its storage deposit), then forwards the balance to
// the parent so the new instance can be paid for.
//
// Run from demo/: node _free-storage.mjs

import { readFileSync } from 'node:fs';
import { JsonRpcProvider, Account } from 'near-api-js';

const NEAR = 10n ** 24n;
const PARENT = 'grip-21a10e2e.testnet';
const saved = JSON.parse(readFileSync('./canonical-account.json', 'utf8'));
const provider = new JsonRpcProvider({ url: 'https://rpc.testnet.fastnear.com' });
const account = new Account(saved.accountId, provider, saved.secretKey);

const show = async (id, label) => {
  const a = await provider.query({ request_type: 'view_account', finality: 'final', account_id: id });
  console.log(`${label.padEnd(22)} ${(Number(a.amount) / 1e24).toFixed(3)} NEAR  storage ${a.storage_usage} bytes`);
  return a;
};

await show(saved.accountId, 'old instance');

await account.deployContract(new Uint8Array(0));
const after = await show(saved.accountId, 'after empty deploy');

// 0.1 NEAR stays behind to keep the now-codeless account alive
const send = BigInt(after.amount) - NEAR / 10n;
if (send <= 0n) throw new Error('nothing to move');
await account.transfer({ receiverId: PARENT, amount: send.toString(), waitUntil: 'FINAL' });
console.log(`moved                  ${(Number(send) / 1e24).toFixed(3)} NEAR to ${PARENT}`);

await show(PARENT, 'parent');
