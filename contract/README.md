# GRIP contract

An NEP-141 token whose **supply is decided by the community's own locking behaviour**, not by the deployer.

Everything in this folder is the on-chain half of the GRIP project. The supply study behind the
chosen parameters is in [`../sim`](../sim). The dashboard is in [`../web`](../web).

## The mechanic

One rule, evaluated once per epoch, callable by anyone:

```text
engaged      = total_supply - reserve
locked_share = total_locked / engaged

locked_share >= 60%  ->  mint 1% of supply, pro-rata to whoever is locked
locked_share <= 35%  ->  burn 2% of supply, out of the reserve only
otherwise            ->  nothing
```

Locks are released automatically at their deadline, before the rule is evaluated: grip has to be
maintained, not set once.

Why `engaged` and not raw supply: 30% of genesis is minted into a contract-owned `reserve`, which is
the coin's fixed deflation budget. It can only ever leave through the burn rule. Counting it as float
would cap grip at 70% forever, so grip is measured on live float.

Why the asymmetry (1% mint / 2% burn): a grip epoch should reward, a fold epoch should cost. The study
below shows the two together produce a supply that expands under grip, stays roughly flat under churn
and contracts under a fold.

## What the deployer cannot do

| Action | Possible? |
| --- | --- |
| Mint after `new` | No. There is no mint method. |
| Touch the reserve except through the burn rule | No. `reserve` is only decremented by `apply_epoch_rule`. |
| Change the eight parameters | No. They are set in `new` and there are no setters. |
| Pause, upgrade, or whitelist | No. No `#[private]` methods, no upgrade path. |
| Block `tick` | No. `tick` is permissionless; nobody can stop it. |

The `owner` field is stored for provenance only. No method reads it.

## Genesis parameters (what will be deployed)

| Parameter | Value | Meaning |
| --- | --- | --- |
| `genesis` | 10,000,000 GRIP | total supply at `new` |
| `reserve_bps` | 3000 | 30% minted into the contract's burn reserve |
| `lock_target_bps` | 6000 | mint when 60% of live float is locked |
| `burn_target_bps` | 3500 | burn when 35% or less is locked |
| `mint_bps` | 100 | 1% of supply per mint epoch |
| `burn_bps` | 200 | 2% of supply per burn epoch |
| `early_exit_bps` | 1000 | exiting a lock early burns 10% of it |
| `max_supply` | 4x genesis | the mint stops here; see the note below |
| `epoch_length_ns` | 86,400e9 | 1 day in production; the testnet demo uses 10s |

## Do this, see that

Requires Rust with the wasm target: `rustup target add wasm32-unknown-unknown`.

```sh
# 1. all twelve unit tests, ~1s
cargo test

# 2. build the contract a judge can deploy
cargo build --release --target wasm32-unknown-unknown
ls -lh target/wasm32-unknown-unknown/release/grip_contract.wasm

# 3. rebuild the supply study this parameter set came from
cd ../sim && python3 sim.py
```

Expected from step 3 (60 epochs, 200 holders, fixed seeds; the numbers are reproducible):

```
scenario    supply  mint  burn  skip
grip         1.75x    58     1     0
churn        1.17x    20     2     0
fold         0.86x    15    15     4
```

Read it as: if the community keeps 60%+ locked for 60 epochs, supply ends 75% higher and pays the
lockers in unlocked tokens. If it folds, the reserve is spent down and supply ends 14% lower. Churn is roughly flat.

## Contract surface

| Method | Kind | Notes |
| --- | --- | --- |
| `new(owner, genesis, reserve_bps, lock_target_bps, burn_target_bps, mint_bps, burn_bps, early_exit_bps, epoch_length_ns)` | init | validates every parameter; mints genesis |
| `ft_transfer(receiver_id, amount)` | payable | unlocked balances only |
| `ft_balance_of(account_id)` / `ft_total_supply()` / `ft_metadata()` | view | NEP-141 |
| `lock(amount, epochs)` | call | moves unlocked balance into the lock; `epochs` 1..=30 |
| `unlock()` | call | before the deadline burns `early_exit_bps` of it; after it, a no-op (the tick already released it) |
| `tick()` | call | permissionless epoch roll; applies the rule once per elapsed epoch (max 12 per call) |
| `get_state()` | view | supply, reserve, engaged, locked share, params, expiry count, last 90 epochs |
| `locked_of(account_id)` / `until_epoch_of(account_id)` | view | a locker's settled position |

Events follow NEP-297 (`EVENT_JSON:`) so an indexer can rebuild the log: `ft_transfer`, `ft_burn`,
`grip:lock`, `grip:unlock`, and `grip:epoch_mint` (the mint has many recipients, so it is not a
single-account `ft_mint`. The event carries the amount, the supply after, and the share it was
earned on).

## Known limits, stated plainly

These are deliberate trade-offs, not oversights:

1. **`tick` needs a caller.** The rule is permissionless, not autonomous. If nobody calls `tick`, no
   epoch is evaluated; the next call rolls up to 12 elapsed epochs at once and applies the rule per
   epoch, so nothing is lost, but a dormant token does not move on its own. A keeper is a 20-line
   script, deliberately kept off-chain so the mechanic has no privileged actor.
2. **The mint is capped at 4x genesis.** A rule that pays 1% of the *current* supply every epoch
   compounds without limit: at a 60 second epoch it passes u128 in about two days, and with overflow
   checks on, `tick` would panic and the rule would never run again. The ceiling is why that cannot
   happen. It is also why the history can show a `capped` row: the rule ran, it just had nothing to pay.
   None of the studied scenarios reach 4x (the strongest is 1.75x), so the cap never binds in the sim.

2. **The burn budget is finite.** The reserve is 30% of genesis. Once it is spent, a fold epoch can no
   longer burn, and the history records `hold` instead. `burn_can_never_take_more_than_the_reserve`
   pins this behaviour.
3. **1e-12 rounding dust.** The mint accumulator is scaled by 1e12, so pro-rata distribution leaves at
   most ~1e-11 of a mint unassigned. `total_locked` can stay a few thousand yocto above the sum of
   individual locks forever; it is unsweepable and economically meaningless (bounded by `DUST` in the
   tests).
4. **At most 32 concurrent lockers.** One `tick` releases every expired lock in a bounded loop, so the
   locker list is capped at 32. A production contract would index expiries by epoch instead of scanning;
   the cap is here so a tick can never run out of gas.
5. **No sybil resistance.** Locking is per account, so a wallet farm could hold the share up. This is a
   mechanic demo; identity would be the next layer, and pretending otherwise would be worse than
   saying it.
6. **No AMM or liquidity.** The token has no market in this repository on purpose: the track says the
   price chart does not count. The mechanic is demonstrated on testnet with scripted actors.

## Tests

`cargo test` runs twelve tests: genesis split, mint on grip, burn on fold, the reserve floor, early-exit
penalty, free exit after the deadline, `tick` rate limiting, transfer isolation from locks, the live-float
denominator invariant, a lock expiring on its own and dragging grip down with it, and `unlock` after an
expiry being a no-op.

## License

MIT.
