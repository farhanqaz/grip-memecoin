# GRIP: submission sheet

An NEP-141 token on NEAR whose supply is a function of how much of its live float the holders keep locked.

| | |
| --- | --- |
| Track | `memecoins` (also entered under `social`) |
| Repository | https://github.com/farhanqaz/grip-memecoin |
| Live dashboard | https://farhanqaz.github.io/grip-memecoin/ |
| Demo video (85s) | [`docs/demo.mp4`](docs/demo.mp4) |
| Contract | `grip5391e9.grip-21a10e2e.testnet` |
| Explorer | https://testnet.nearblocks.io/address/grip5391e9.grip-21a10e2e.testnet (mirror: https://near.rocks/address/grip5391e9.grip-21a10e2e.testnet) |
| One command check | `./scripts/verify.sh` (also proves the deployed contract answers) |
| License | MIT |

## The problem

Every memecoin has the same supply curve: the deployer decides how much exists, and nothing the community
does changes it. The meme is decoration on a fixed number.

## What this does

```
engaged      = total_supply - reserve
locked_share = total_locked / engaged

locked_share >= 60%  ->  mint 1% of supply, pro rata to lockers, paid out unlocked
locked_share <= 35%  ->  burn 2% of supply, out of the reserve only
otherwise            ->  nothing
```

Three properties that make it a mechanic rather than a gimmick:

1. **Locks expire.** A lock stops counting at its deadline, before the rule is evaluated, so grip has to be
   renewed. One passive holder cannot hold the metric up forever.
2. **Rewards are paid out unlocked.** The locked total always equals the sum of positions, so a reward never
   inflates the principal that earned it.
3. **Nobody can change the rule.** No owner mint, no pause, no setters, no upgrade path. `tick()` is
   permissionless, so an epoch can be evaluated by anyone and blocked by no one.

## What is in the repository

| Path | What it is | Check |
| --- | --- | --- |
| `contract/` | the token and its epoch rule, Rust + `near-sdk` 5 | `cd contract && cargo test` (11 tests) |
| `sim/` | 60 epoch supply study behind the chosen parameters | `cd sim && python3 sim.py` |
| `demo/` | testnet deploy, three scripted actors, the keeper | `cd demo && npm run demo` |
| `docs/` | the live dashboard and the recorded run | open `docs/index.html` |
| `tools/` | RPC proxy, and the recorder that produced the video | `python3 tools/rec.py` |
| `scripts/verify.sh` | runs every claim above and exits non-zero on failure | `./scripts/verify.sh` |

The parameters were not guessed. 108 combinations were swept and this set kept because it produces the
supply behaviour the rule is supposed to have:

```
scenario  supply  mint  burn
grip       1.75x    58     1     the community holds the line, supply expands, lockers get paid
churn      1.17x    20     2     roughly flat
fold       0.86x    15    15     the reserve is spent down, supply contracts
```

## Reading the chain without a browser

Explorers render client-side and some of them block scripted fetches. The machine-checkable path is the
RPC call that `scripts/verify.sh` already runs:

```sh
curl -s https://rpc.testnet.fastnear.com -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"query","params":{"request_type":"call_function",
       "finality":"final","account_id":"grip5391e9.grip-21a10e2e.testnet",
       "method_name":"get_state","args_base64":"e30="}}'
```

It returns supply, reserve, locked share, every fixed parameter and the last 90 epochs, with no browser
and no key.

## Known limits, stated plainly

1. **`tick` needs a caller.** The rule is permissionless, not autonomous. A keeper script is included and
   runs off chain on purpose, so the mechanic has no privileged actor.
2. **The burn budget is finite.** The reserve is 30% of genesis. When it is spent, a fold epoch records
   `hold` instead. A test pins that behaviour.
3. **At most 32 concurrent lockers.** One `tick` releases every expired lock in a bounded loop, so the
   locker list is capped. A production version would index expiries by epoch.
4. **No sybil resistance.** Locking is per account; a wallet farm could hold the share up. It is a mechanic
   demo and the README says so.
5. **No AMM.** The track scores the mechanic, not the chart, so there is no market on purpose.
6. **1e-12 rounding dust** in the pro rata accumulator, bounded and unsweepable, asserted in the tests.

## Status

Deployed to NEAR testnet, running with a keeper. Built during the NEAR HACKATHON window, 1 to 14 Nov 2026.
