"""GRIP parameter study: 60 epochs of supply dynamics under three community scenarios.

The mechanic mirrored 1:1 by the contract:

    engaged      = total_supply - reserve
    locked_share = total_locked / engaged
    locked_share >= lock_target -> mint mint_bps of supply, pro-rata to lockers
    locked_share <= burn_target -> burn burn_bps of supply, out of the reserve only
    otherwise                   -> nothing

Why the reserve is excluded from the denominator: the reserve is the coin's fixed
deflation budget, held by the contract and spendable by nothing but the burn rule.
Counting it as float would let a 30% reserve cap grip at 70% forever, so a "grip"
metric the community can actually move has to be measured on live float.

No price model, no oracle. This studies supply only, which is what the track says
is judged ("the mechanic, not the chart").

Run:  python3 sim/sim.py
"""

import random
from dataclasses import dataclass, field

EPOCHS = 60
HOLDERS = 200
GENESIS = 10_000_000
RESERVE_BPS = 3000  # 30% of genesis -> contract-owned burn reserve


@dataclass
class Params:
    name: str
    lock_target: float
    burn_target: float
    mint_bps: int
    burn_bps: int


@dataclass
class Holder:
    free: float
    locked: float = 0.0
    timer: int = 0
    rng: random.Random = field(default_factory=random.Random, repr=False)

    def act(self, sentiment: float, p_lock: float = 0.38, p_relock: float = 0.85) -> None:
        if self.locked > 0:
            self.timer -= 1
            if self.timer <= 0:
                if self.rng.random() < p_relock * sentiment:
                    self.timer = self.rng.randint(1, 3)
                else:  # folds: everything comes back to float
                    self.free += self.locked
                    self.locked = 0.0
        elif self.free > 0 and self.rng.random() < p_lock * sentiment:
            self.locked, self.free = self.free, 0.0
            self.timer = self.rng.randint(2, 5)


def scenario(name: str) -> list[float]:
    """Sentiment path per epoch. Deterministic on purpose: anyone can rerun it."""
    if name == "grip":
        return [0.95] * EPOCHS
    if name == "churn":
        return [0.75 if (e // 5) % 2 else 0.42 for e in range(EPOCHS)]
    if name == "fold":
        return [max(0.10, 0.98 - 0.015 * e) for e in range(EPOCHS)]
    raise ValueError(name)


def run(p: Params, scen: str, seed: int = 11) -> dict:
    rng = random.Random(seed)
    holders = [Holder(GENESIS * (1 - RESERVE_BPS / 10000) / HOLDERS, rng=rng) for _ in range(HOLDERS)]
    supply = float(GENESIS)
    reserve = GENESIS * RESERVE_BPS / 10000
    mints = burns = skipped = 0
    share_min, share_max = 1.0, 0.0
    series = []
    for e, s in enumerate(scenario(scen)):
        for h in holders:
            h.act(s)
        locked = sum(h.locked for h in holders)
        engaged = supply - reserve
        share = locked / engaged if engaged > 0 else 0.0
        share_min, share_max = min(share_min, share), max(share_max, share)
        if share >= p.lock_target:
            amt = supply * p.mint_bps / 10000
            supply += amt
            for h in holders:
                if h.locked > 0:
                    h.locked += amt * (h.locked / locked)
            mints += 1
        elif share <= p.burn_target:
            amt = min(supply * p.burn_bps / 10000, reserve)
            if amt <= 0:
                skipped += 1
            else:
                supply -= amt
                reserve -= amt
                burns += 1
        series.append((e, supply, share, locked, reserve))
    return {
        "mult": supply / GENESIS,
        "mints": mints,
        "burns": burns,
        "skipped": skipped,
        "share_min": share_min,
        "share_max": share_max,
        "reserve_left": reserve,
        "series": series,
    }


CANDS = [
    Params("CHOSEN 60/35 m1 b2", 0.60, 0.35, 100, 200),
    Params("A  60/40  1.0%/1.0%", 0.60, 0.40, 100, 50),
    Params("C  50/30  2.0%/1.0%", 0.50, 0.30, 200, 50),
]


def sweep() -> None:
    """Find parameter sets where the mechanic tells a clean story:
    grip expands supply, churn lands near flat, fold actually contracts it."""
    good = []
    for lt in (0.55, 0.60, 0.65):
        for bt in (0.30, 0.35, 0.40):
            for mb in (50, 75, 100):
                for bb in (75, 100, 150, 200):
                    p = Params(f"{lt:.2f}/{bt:.2f} m{mb} b{bb}", lt, bt, mb, bb)
                    g = run(p, "grip")["mult"]
                    c = run(p, "churn")["mult"]
                    f = run(p, "fold")["mult"]
                    if g >= 1.45 and 0.90 <= c <= 1.25 and f <= 0.92:
                        good.append((p.name, g, c, f))
    print(f"{len(good)} parameter sets pass: grip>=1.45x, 0.90<=churn<=1.25, fold<=0.92x\n")
    print(f"{'params':22s}{'grip':>8s}{'churn':>8s}{'fold':>8s}")
    for name, g, c, f in good:
        print(f"{name:22s}{g:7.2f}x{c:7.2f}x{f:7.2f}x")


if __name__ == "__main__":
    import sys

    print(f"genesis={GENESIS:,}  reserve={RESERVE_BPS/100:.0f}%  epochs={EPOCHS}  holders={HOLDERS}")
    print("locked_share is measured on live float (supply - reserve)\n")
    if "--sweep" in sys.argv:
        sweep()
        raise SystemExit
    for p in CANDS:
        print(f"--- {p.name}  mint@{p.lock_target:.0%}  burn@{p.burn_target:.0%} ---")
        print(f"{'scenario':9s}{'supply':>9s}{'mint':>6s}{'burn':>6s}{'skip':>6s}{'share<':>9s}{'share>':>9s}{'reserve':>12s}")
        for sc in ("grip", "churn", "fold"):
            r = run(p, sc)
            print(f"{sc:9s}{r['mult']:8.2f}x{r['mints']:6d}{r['burns']:6d}{r['skipped']:6d}"
                  f"{r['share_min']:8.0%}{r['share_max']:8.0%}{r['reserve_left']:12,.0f}")
        print()

    print("supply curve, CHOSEN parameters (every 15th epoch):")
    for sc in ("grip", "churn", "fold"):
        r = run(CANDS[0], sc)
        pts = [r["series"][i] for i in (0, 14, 29, 44, 59)]
        print(f"  {sc:6s} " + "  ".join(f"{s/1e6:5.2f}M" for _, s, *_ in pts))
