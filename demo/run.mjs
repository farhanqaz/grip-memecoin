// The demo: three actors, one epoch boundary, one early exit — on testnet, for real.
//
//   node run.mjs
//
// Every number printed below comes back from the deployed contract over JSON-RPC.
// Nothing is simulated here; ../sim is the offline study, this is the live token.

import { readFileSync, writeFileSync } from 'node:fs';
import { KeyPair, JsonRpcProvider, Account, actions } from 'near-api-js';
import { viewCall } from './rpc.mjs';

const TGAS = 1_000_000_000_000n;
const UNIT = 10n ** 18n; // 18 decimals
const NEAR = 10n ** 24n;

const STATE_URL = new URL('./demo-account.json', import.meta.url);
const saved = JSON.parse(readFileSync(STATE_URL, 'utf8'));
const { accountId: CONTRACT, secretKey } = saved;
const provider = new JsonRpcProvider({ url: 'https://rpc.testnet.fastnear.com' });
const owner = new Account(CONTRACT, provider, secretKey);

const fmt = (raw) => (Number(BigInt(raw) / 10n ** 12n) / 1e6).toLocaleString('en-US', { maximumFractionDigits: 2 });
const pct = (bps) => (bps / 100).toFixed(1) + '%';
const state = () => viewCall(CONTRACT, 'get_state');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function show(title, s) {
  console.log(`\n${title}`);
  console.log(`  supply ${fmt(s.total_supply)}  |  reserve ${fmt(s.reserve)}  |  locked ${fmt(s.total_locked)}  |  grip ${pct(s.locked_share_bps)}`);
  console.log(`  epoch ${s.epoch}  |  mint epochs ${s.mint_epochs}  |  burn epochs ${s.burn_epochs}`);
  for (const h of s.history.slice(-4)) console.log(`    ep ${h.epoch}: ${h.action.padEnd(26)} share ${pct(h.share_bps)}  supply ${fmt(h.supply)}`);
}

// waitUntil: 'FINAL' matters here: the next line reads the state back, and a read right after an
// optimistic execution can still land on a block that has not applied it yet.
const call = (account, methodName, args, gas = 60n * TGAS, deposit = 0n) =>
  account.callFunction({ contractId: CONTRACT, methodName, args, gas, deposit, waitUntil: 'FINAL' });

async function waitForEpoch(s) {
  const dueAt = Number(BigInt(s.epoch_start) + BigInt(s.epoch_length_ns)) / 1e6;
  const wait = dueAt - Date.now() + 1500;
  if (wait > 0) {
    console.log(`  ... wait ${(wait / 1000).toFixed(1)}s for epoch ${s.epoch + 1} to unlock`);
    await sleep(wait);
  }
}

// --- 3 actors, each its own account so locking is per-account as the contract requires.
// The actor key is generated once and kept next to the deploy key, so reruns reuse the same accounts.
if (!saved.actorsKey) {
  saved.actorsKey = KeyPair.fromRandom('ed25519').toString();
  writeFileSync(STATE_URL, JSON.stringify(saved, null, 2) + '\n');
}
const actorKey = KeyPair.fromString(saved.actorsKey);
const actors = {};
for (const name of ['alice', 'bob', 'carol']) {
  const subId = `${name}.${CONTRACT}`;
  const pub = actorKey.getPublicKey().toString();
  try {
    await owner.createSubAccount({ accountOrPrefix: name, publicKey: pub, nearToTransfer: (2n * NEAR).toString() });
    console.log(`created ${subId} (funded 2 NEAR for gas)`);
  } catch (e) {
    console.log(`${subId} already exists (${e.message.slice(0, 60)})`);
  }
  const acct = new Account(subId, provider, actorKey.toString());
  // top up so a rerun never stalls on gas
  const bal = await provider.viewAccount({ accountId: subId });
  if (BigInt(bal.amount) < NEAR) {
    await owner.signAndSendTransaction({ receiverId: subId, actions: [actions.transfer(2n * NEAR)] });
    console.log(`  topped up ${subId} with 2 NEAR`);
  }
  actors[name] = acct;
}

let s = await state();
show('1. genesis', s);

// --- fund the actors with the token itself
const stake = { alice: 2_500_000n, bob: 2_500_000n, carol: 2_000_000n };

// The whole stake comes from the deployer's genesis balance, so this demo runs once per instance.
const ownerGrip = await viewCall(CONTRACT, 'ft_balance_of', { account_id: CONTRACT });
if (BigInt(ownerGrip) < 7_000_000n * UNIT) {
  console.error(
    `\nThis instance has already been funded (deployer holds ${fmt(ownerGrip)} GRIP).\n` +
      `Run the demo on a clean instance instead:\n\n    npm run demo\n\n` +
      `which re-deploys a fresh account and then runs this script.`,
  );
  process.exit(1);
}
for (const [name, amount] of Object.entries(stake)) {
  await call(owner, 'ft_transfer', { receiver_id: actors[name].accountId, amount: (amount * UNIT).toString() }, 60n * TGAS, 1n);
  console.log(`sent ${Number(amount).toLocaleString()} GRIP to ${name}`);
}

// --- the community grips: 5M of the 7M live float goes under lock
for (const name of ['alice', 'bob']) {
  await call(actors[name], 'lock', { amount: (stake[name] * UNIT).toString(), epochs: 3 });
  console.log(`${name} locked ${Number(stake[name]).toLocaleString()} GRIP for 3 epochs`);
}
s = await state();
show('2. after two locks (grip above the 60% target)', s);

await waitForEpoch(s);
await call(owner, 'tick');
s = await state();
show('3. epoch rolled: mint fired, lockers paid', s);

// --- and one actor folds before the deadline: the penalty burns
await call(actors.carol, 'lock', { amount: (stake.carol * UNIT).toString(), epochs: 5 });
console.log(`\ncarol locked ${Number(stake.carol).toLocaleString()} GRIP for 5 epochs, then exits immediately`);
const supplyBefore = s.total_supply;
await call(actors.carol, 'unlock');
s = await state();
show('4. carol exits early: 10% of her lock is burned', s);
console.log(`  supply delta: ${fmt(supplyBefore)} -> ${fmt(s.total_supply)}`);

await waitForEpoch(s);
await call(owner, 'tick');
s = await state();
show('5. next epoch', s);

console.log(`\ncontract: ${CONTRACT}`);
console.log(`explorer: https://testnet.near.org/accounts/${CONTRACT}`);
