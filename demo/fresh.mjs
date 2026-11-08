// Spin up a fresh public instance as a sub-account of an existing funded account.
//
//   node fresh.mjs            # -> writes canonical-account.json, prints the new contract id
//
// The testnet account helper rate-limits by IP, but a sub-account costs nothing and needs no helper,
// so this is the reliable way to get a clean instance to demo once the helper says 429.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { KeyPair, JsonRpcProvider, Account } from 'near-api-js';
import { viewCall } from './rpc.mjs';
import { GENESIS_ARGS } from './params.mjs';

const RPC = 'https://rpc.testnet.fastnear.com';
const TGAS = 1_000_000_000_000n;
const NEAR = 10n ** 24n;
const WASM = new URL('../contract/target/wasm32-unknown-unknown/release/grip_contract.wasm', import.meta.url);
const PARENT = new URL('./demo-account.json', import.meta.url);
const OUT = new URL('./canonical-account.json', import.meta.url);

const parent = JSON.parse(readFileSync(PARENT, 'utf8'));
const provider = new JsonRpcProvider({ url: RPC });
const owner = new Account(parent.accountId, provider, parent.secretKey);

const key = KeyPair.fromRandom('ed25519');
const prefix = 'grip' + randomBytes(3).toString('hex');
const contractId = `${prefix}.${parent.accountId}`;

console.log(`creating ${contractId} as a sub-account of ${parent.accountId}`);
await owner.createSubAccount({ accountOrPrefix: prefix, publicKey: key.getPublicKey().toString(), nearToTransfer: ((36n * NEAR) / 10n).toString() });

// the sub-account is not always visible to the next request
let ready = false;
for (let i = 0; i < 10 && !ready; i += 1) {
  try {
    await provider.viewAccount({ accountId: contractId });
    ready = true;
  } catch {
    await new Promise((r) => setTimeout(r, 900));
  }
}
if (!ready) throw new Error(`${contractId} never became visible`);

const account = new Account(contractId, provider, key.toString());
const code = new Uint8Array(readFileSync(WASM));
console.log(`deploying ${(code.length / 1024).toFixed(0)} KiB of wasm`);
await account.deployContract(code);
await account.callFunction({ contractId, methodName: 'new', args: { owner: contractId, ...GENESIS_ARGS }, gas: 100n * TGAS, waitUntil: 'FINAL' });

// seed the stand-in community: the deployer locks its whole live float so the demo instance is minting
const free = BigInt(await viewCall(contractId, 'ft_balance_of', { account_id: contractId }));
await account.callFunction({
  contractId,
  methodName: 'lock',
  args: { amount: free.toString(), epochs: Number(process.env.LOCK_EPOCHS || 30) },
  gas: 60n * TGAS,
  waitUntil: 'FINAL',
});

writeFileSync(OUT, JSON.stringify({ accountId: contractId, secretKey: key.toString(), parent: parent.accountId }, null, 2) + '\n');
const s = await viewCall(contractId, 'get_state');
console.log(`\nlive: ${contractId}`);
console.log(`grip ${(s.locked_share_bps / 100).toFixed(1)}% · epoch ${s.epoch} · epoch length ${Number(s.epoch_length_ns) / 1e9}s`);
console.log(`dashboard: docs/index.html?contract=${contractId}`);
console.log(`keeper:    STATE_FILE=./canonical-account.json node keeper.mjs`);
