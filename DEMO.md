# The demo

`docs/demo.mp4` is 85 seconds and 5.3 MB. It is assembled from three real sources, not acted out:

| Layer | Where it comes from |
| --- | --- |
| Terminal | `tools/rec.py` recorded an actual `node run.mjs` against testnet, then `tools/cast2mp4.py` replayed those timings |
| Dashboard | screenshots of the deployed page reading the same contract |
| Cards | drawn by `tools/film.py` with the page's own fonts |
| Voice | one file per sentence, so every subtitle cue time is measured instead of estimated |

Rebuild it:

```sh
python3 tools/film.py           # writes docs/demo.mp4; needs demo/lines/ and ffmpeg
python3 tools/film.py --fresh   # re-synthesise the voice (needs edge-tts)
```

Three things in the edit are deliberate.

The terminal segment is retimed with a beat map, so each beat (genesis, the two locks, the mint, the early
exit, the deadline burn) lands under the sentence that names it rather than drifting against the voice.

The dashboard stills move with a sub-pixel affine transform. ffmpeg's `zoompan` crops on integer pixels,
which is why a zoom built on it judders, and these frames are dense enough that the judder is visible.

The subtitles are burned in rather than supplied as a track, because the video is meant to be watched on X,
where the default is silence and a number only counts if it is on screen.

Frame order and timing are whatever the run produced. The editing only decides what you look at, and when.
