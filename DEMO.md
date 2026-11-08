# The demo

The demo is built, not acted out. `demo/demo.mp4` (85s, 3.3 MB) is assembled from three real sources:

| Layer | Where it comes from |
| --- | --- |
| Voice | one TTS file per sentence, so cue times are measured, not estimated |
| Subtitles | burned in, on the same timeline as the voice |
| Cards | `tools/film.py`, drawn with the page's own fonts |
| Terminal | `tools/rec.py` recorded an actual `node run.mjs` against testnet, then `tools/cast2mp4.py` replayed it |
| Dashboard | screenshots of the deployed page reading the same contract |

Rebuild it:

```sh
python3 tools/film.py           # narration is cached in demo/lines/
python3 tools/film.py --fresh   # re-synthesise the voice
```

Two things in the edit are deliberate. The terminal segment is retimed with a beat map, so each beat
(genesis, the two locks, the mint, the early exit, the deadline burn) lands under the sentence that names
it. And the dashboard stills move with a sub-pixel affine transform: ffmpeg's `zoompan` crops on integer
pixels, which is why a zoom built on it judders.

Why a produced video and not a Loom take: X plays silently by default, so the key numbers have to be on
screen as captions; the demo has to show two surfaces (terminal and dashboard) that one take struggles to
hold; and a retake, a microphone, or a stumble all cost more than they add. If you want a human voice on
top anyway, the script below is written for a 60 second screen-share.

## Optional: the Loom script (60s, if you want your own voice)

Share the dashboard at `https://farhanqaz.github.io/grip-memecoin/`, then read this. Square brackets are
stage directions, not lines.

> **[dashboard open, hero visible]**
> Every memecoin's supply is decided by whoever deployed it. Nothing the community does changes it.
>
> GRIP is a token on NEAR where supply follows one number: how much of the live float is locked.
> **[point at the gauge]** Right now that is eighty eight percent, so this epoch is minting.
>
> Lock sixty percent and the token mints one percent, paid to the lockers. Fall under thirty five and it
> burns two percent, out of a reserve the contract owns. **[scroll to the chart]** Every point here is an
> epoch the contract applied, read straight off chain, no indexer.
>
> The part I care about: locks expire at their deadline, before the rule runs. So grip has to be
> maintained, not set once. One person can't freeze it.
>
> There is no owner mint, no pause, no setters. `tick()` is permissionless, anyone can call it, nobody can
> block it. The contract, twelve tests, and the sixty epoch study that picked these parameters are in the
> repo.

If you record it: 60 seconds max, no intro longer than one sentence, say the numbers you can point at, and
post it with the same text as the draft below.

## The post

```text
Memecoins have a supply curve decided by their developer. Nothing the community does changes it.

GRIP makes supply a function of the one thing a community controls: how much of the coin it keeps locked.

- lock 60% of the live float -> mints 1%, paid to the lockers
- fall under 35% -> burns 2% from a reserve, never from holders' pockets

No owner mint. No pause. No setters. The deployer's key has no power after deployment, and on NEAR the
rule is one permissionless method, tick(), that nobody can block or change.

Built at NEAR HACKATHON. Contract on testnet: grip599cb0.grip-21a10e2e.testnet
Repo + 60-epoch supply study: <repo link>

What would make you trust a token like this: more lockers, or a longer lock?
#NEARHackathon @NEARProtocol
```

## Checklist before posting


- [ ] repo is **public** (`git status` clean, no `demo-account.json`, no `canonical-account.json`)
- [ ] `./scripts/verify.sh` prints all checks passed
- [ ] `cargo test` prints 12 passed
- [ ] video is attached to the post, not just linked
- [ ] post says "built at NEAR HACKATHON", tags @NEARProtocol, has #NEARHackathon
- [ ] dashboard opens on a phone on mobile data, and the numbers are alive, not frozen
- [ ] explorer link resolves in a normal browser (nearblocks, with near.rocks as the mirror)
- [ ] the idea text in the submission form is under 2000 characters and matches the repo
