// Deploy GRIP to testnet and initialise it.
//
//   node deploy.mjs            # reuse ./demo-account.json, or mint a throwaway account
//   node deploy.mjs --fresh    # always mint a new throwaway account
//
// The account and key are written to ./demo-account.json, which .gitignore keeps out of the repo.
// No mainnet, no real funds, no wallet: the testnet helper funds the account for free.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { KeyPair, JsonRpcProvider, Account } from 'near-api-js';
import { viewCall } from './rpc.mjs';

const WASM = new URL('../contract/target/wasm32-unknown-unknown/release/grip_contract.wasm', import.meta.url);
const STATE = new URL('./demo-account.json', import.meta.url);
const RPC = 'https://rpc.testnet.fastnear.com';
const TGAS = 1_000_000_000_000n;

// Genesis parameters, identical to the set the simulation picked (see ../sim and ../contract/README.md).
// epoch_length_ns is 10s here so a judge can watch an epoch turn over inside a two-minute demo;
// production would use 86_400e9 (one day). Every other number is the real one.
export const GENESIS_ARGS = {
  genesis: '10000000000000000000000000', // 10M GRIP at 18 decimals
  reserve_bps: 3000,
  lock_target_bps: 6000,
  burn_target_bps: 3500,
  mint_bps: 100,
  burn_bps: 200,
  early_exit_bps: 1000,
  epoch_length_ns: Number(process.env.EPOCH_NS || 10_000_000_000),
};

async function newTestnetAccount(provider) {
  const kp = KeyPair.fromRandom('ed25519');
  const accountId = `grip-${randomBytes(4).toString('hex')}.testnet`;
  const res = await fetch('https://helper.testnet.near.org/account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kind: 'CREATE_ACCOUNT',
      newAccountId: accountId,
      newAccountPublicKey: kp.getPublicKey().toString(),
    }),
  });
  const text = await res.text();
  if (!res.ok || !text.includes('SuccessValue')) {
    throw new Error(`testnet helper refused: ${res.status} ${text.slice(0, 300)}`);
  }
  console.log(`created throwaway testnet account ${accountId} (funded by the helper)`);
  return { accountId, secretKey: kp.toString(), provider };
}

async function loadOrCreate(provider, forceFresh) {
  if (!forceFresh && existsSync(STATE)) {
    const saved = JSON.parse(readFileSync(STATE, 'utf8'));
    console.log(`reusing ${saved.accountId}`);
    return new Account(saved.accountId, provider, saved.secretKey);
  }
  const created = await newTestnetAccount(provider);
  writeFileSync(STATE, JSON.stringify({ accountId: created.accountId, secretKey: created.secretKey }, null, 2) + '\n');
  return new Account(created.accountId, provider, created.secretKey);
}

const provider = new JsonRpcProvider({ url: RPC });
const account = await loadOrCreate(provider, process.argv.includes('--fresh'));

const code = new Uint8Array(readFileSync(WASM));
console.log(`deploying ${(code.length / 1024).toFixed(0)} KiB of wasm to ${account.accountId}`);
const deployRes = await account.deployContract(code);
console.log('deploy status:', deployRes.status?.SuccessValue !== undefined ? 'ok' : JSON.stringify(deployRes.status));

console.log('calling new()', { ...GENESIS_ARGS, owner: account.accountId });
const initRes = await account.callFunction({
  contractId: account.accountId,
  methodName: 'new',
  args: { owner: account.accountId, ...GENESIS_ARGS },
  gas: 100n * TGAS,
  deposit: 0n,
});
console.log('init status:', JSON.stringify(initRes.status));

const state = await viewCall(account.accountId, 'get_state');
console.log('get_state:', JSON.stringify(state));

console.log(`\nGRIP live at ${account.accountId}`);
