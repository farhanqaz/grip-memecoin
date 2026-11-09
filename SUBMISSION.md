# GRIP: submission sheet

An NEP-141 token on NEAR whose supply is a function of how much of its live float the holders keep locked.

| | |
| --- | --- |
| Track | `memecoins` |
| Repository | https://github.com/farhanqaz/grip-memecoin |
| Live dashboard | https://farhanqaz.github.io/grip-memecoin/ |
| Demo video (85s) | [`docs/demo.mp4`](docs/demo.mp4) |
| Contract | `grip599cb0.grip-21a10e2e.testnet` |
| Explorer | https://testnet.nearblocks.io/address/grip599cb0.grip-21a10e2e.testnet (mirror: https://near.rocks/address/grip599cb0.grip-21a10e2e.testnet) |
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
| `contract/` | the token and its epoch rule, Rust + `near-sdk` 5 | `cd contract && cargo test` (12 tests) |
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

Explorers render client-side and some of them block scripted fetches. The machine-checkable path is a
view call, and the repo wraps it in one command:

```sh
./scripts/state.sh                    # get_state: supply, reserve, locked share, and every parameter
./scripts/state.sh ft_metadata        # or any other view method
```

It prints the block height on stderr, so you can see the reading is fresh, and the decoded JSON on stdout.

If you would rather do it by hand, this is the whole call, with no dependency beyond python3:

```sh
curl -sS https://rpc.testnet.fastnear.com -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"query","params":{"request_type":"call_function",
       "finality":"final","account_id":"grip599cb0.grip-21a10e2e.testnet",
       "method_name":"get_state","args_base64":"e30="}}' \
| python3 -c "import sys,json;print(bytes(json.load(sys.stdin)['result']['result']).decode())"
```

Not `jq -r '.result.result\[\]' | awk '{printf "%c",$1}'`: that works on ASCII and silently mangles
anything above byte 127 under gawk in a UTF-8 locale. `bytes()` drops each byte in as a byte.

## Known limits, stated plainly

1. **`tick` needs a caller.** The rule is permissionless, not autonomous. A keeper script is included and
   runs off chain on purpose, so the mechanic has no privileged actor.
2. **The burn budget is finite.** The reserve is 30% of genesis. When it is spent, a fold epoch records
   `hold` instead. A test pins that behaviour.
3. **At most 32 concurrent lockers.** One `tick` releases every expired lock in a bounded loop, so the
   locker list is capped. A production version would index expiries by epoch.
4. **The mint is capped at 4x genesis, on purpose.** Paying 1% of the current supply every epoch
   compounds: at the demo's 60 second epoch the number passes u128 in about two days, and because the
   contract is built with overflow checks, `tick` would panic and never recover. The ceiling is what makes
   the rule safe to leave running unattended, and a `capped` row in the history is what it looks like when
   the ceiling is reached. None of the studied scenarios get there (the strongest is 1.75x).
5. **No sybil resistance.** Locking is per account; a wallet farm could hold the share up. It is a mechanic
   demo and the README says so.
6. **No AMM.** The track scores the mechanic, not the chart, so there is no market on purpose.
7. **1e-12 rounding dust** in the pro rata accumulator, bounded and unsweepable, asserted in the tests.

## Status

Deployed to NEAR testnet, running with a keeper. Built during the NEAR HACKATHON window, 1 to 14 Nov 2026.

The live instance was redeployed once. The first deployment ran for 129 epochs and exposed a real defect:
the mint compounded without a ceiling, and at a 60 second epoch it would have hit u128 overflow inside two
days, which with overflow checks on means `tick` panics and the rule stops for good. The fix is the 4x
cap, a twelfth test pins it, and the instance this page points at runs the fixed build. The old account
still holds its state and its history is quoted in `contract/README.md` observation tables.
