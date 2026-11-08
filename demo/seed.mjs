// Seed the "demo community" on a fresh instance: the deployer locks its whole live float for a while,
// so the dashboard has a real grip reading and the mint has something to pay.
//
//   LOCK_EPOCHS=30 node seed.mjs
//
// This is one account standing in for a community, and the dashboard says so. It exists so the public
// deployment is not a dead chart; it is not a claim that a community exists.

import { readFileSync } from 'node:fs';
import { JsonRpcProvider, Account } from 'near-api-js';
import { viewCall } from './rpc.mjs';

const TGAS = 1_000_000_000_000n;
const { accountId, secretKey } = JSON.parse(readFileSync(new URL('./demo-account.json', import.meta.url), 'utf8'));
const epochs = Number(process.env.LOCK_EPOCHS || 30);

const provider = new JsonRpcProvider({ url: 'https://rpc.testnet.fastnear.com' });
const account = new Account(accountId, provider, secretKey);

const free = BigInt(await viewCall(accountId, 'ft_balance_of', { account_id: accountId }));
console.log(`${accountId} holds ${Number(free / 10n ** 18n).toLocaleString()} unlocked GRIP`);

const res = await account.callFunction({
  contractId: accountId,
  methodName: 'lock',
  args: { amount: free.toString(), epochs },
  gas: 60n * TGAS,
  waitUntil: 'FINAL',
});
console.log(`locked for ${epochs} epochs`, res ? '' : '(no response)');

const s = await viewCall(accountId, 'get_state');
console.log(`grip ${(s.locked_share_bps / 100).toFixed(1)}% · epoch ${s.epoch} · supply ${Number(BigInt(s.total_supply) / 10n ** 18n).toLocaleString()}`);
console.log(`dashboard: docs/index.html?contract=${accountId}`);
