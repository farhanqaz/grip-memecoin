# Recording the demo (target: 100 seconds, one take)

The demo has to show **one complete moment**: a real user action ending in a visible on-chain result.
No architecture slides, no setup.

## Before you hit record

```sh
cd demo && npm install          # once
cd ../contract && cargo build --release --target wasm32-unknown-unknown   # fresh wasm
```

Have three things open and ready:

1. a terminal at `near-hackathon/demo/`
2. the dashboard in a browser: `cd docs && python3 -m http.server 8765`,
   then `http://localhost:8765/index.html`
3. the contract on the explorer: `https://testnet.near.org/accounts/grip5391e9.grip-21a10e2e.testnet`

## Shot list

| Time | On screen | Say (roughly) |
| --- | --- | --- |
| 0:00–0:12 | Dashboard, top numbers | "Every memecoin's supply is decided by its developer. Nothing the community does changes it. GRIP makes supply a function of the one thing a community actually controls: how much of the coin it keeps locked." |
| 0:12–0:30 | The rule strip on the dashboard | "Lock 60% of the live float and the token mints 1%, paid to the lockers. Drop under 35% and it burns 2% out of a reserve — never out of holders' pockets. The deployer has no mint, no pause, no setter." |
| 0:30–1:15 | Terminal: `npm run demo` | Let it print. Narrate the beats: genesis 10M / three actors funded / two lock past the target / an epoch rolls and supply goes 10,000,000 → 10,100,000, all of it to the lockers / carol exits early and 10% of her own lock is burned. |
| 1:15–1:35 | Dashboard, refreshed | "Those are not local numbers. This page reads `get_state` off the contract over public RPC. Same supply, same grip, same epoch log — and the chart is the contract's own history array." |
| 1:35–1:50 | Explorer tab | "The whole rule is one method on NEAR, `tick()` — permissionless, unblockable, callable by anyone. There is no admin key that can stop it or change the numbers." |
| 1:50–2:00 | README / repo | "The parameters came from a 60-epoch simulation in the repo — 108 combinations swept, this set kept. Repo link below. What would make you trust a token like this — more lockers, or a longer lock?" |

## The post

```text
Memecoins have a supply curve decided by their developer. Nothing the community does changes it.

GRIP makes supply a function of the one thing a community controls: how much of the coin it keeps locked.

- lock 60% of the live float -> mints 1%, paid to the lockers
- fall under 35% -> burns 2% from a reserve, never from holders' pockets

No owner mint. No pause. No setters. The deployer's key has no power after deployment — on NEAR the rule
is one permissionless method, tick(), that nobody can block or change.

Built at NEAR HACKATHON. Contract on testnet: grip5391e9.grip-21a10e2e.testnet · repo + 60-epoch supply study here:
<link>

What would make you trust a token like this: more lockers, or a longer lock?
#NEARHackathon @NEARProtocol
```

## Checklist before posting

- [ ] repo is **public** (`git status` clean, no `demo-account.json`, no keys)
- [ ] `cargo test` prints 9 passed
- [ ] `python3 sim/sim.py` prints the grip/churn/fold table
- [ ] video is attached to the post (not a link only)
- [ ] post says "built at NEAR HACKATHON", tags @NEARProtocol, has #NEARHackathon
- [ ] dashboard is reachable from a phone on mobile data (GitHub Pages is enough)
