"""Build the demo film.

    python3 tools/film.py            # builds docs/demo.mp4
    python3 tools/film.py --fresh    # re-synthesises the voice

One timeline, three sources, no hand-waving:

  * the narration is synthesised one sentence at a time, so every cue time is measured instead of
    estimated from word counts
  * the recorded run (`demo/demo.cast`) is retimed with a beat map, so each beat lands under the sentence
    that describes it
  * the dashboard stills move with a sub-pixel affine transform rather than zoompan's integer crop,
    which is what made the first cut judder

Nothing is faked. The editing only decides what you look at, and when.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "docs" / "fonts"
STILLS = ROOT / "demo" / "stills"
CACHE = ROOT / "demo" / "lines"
OUT = ROOT / "docs" / "demo.mp4"   # the page serves docs/, so this is the artifact

W, H = 1280, 720
FPS = 25
SS = 1.6  # supersample factor for the zoomed stills

VOICE = "en-US-AndrewNeural"
RATE = "-4%"

LEAD = 0.7      # silence before the first sentence
GAP = 0.45      # between sentences
TAIL = 3.0      # after the last one

BG = (11, 11, 10)
INK = (244, 241, 234)
MUTED = (142, 138, 128)
FAINT = (93, 90, 84)
LIME = (203, 255, 77)

SERIF = str(FONTS / "fraunces-300_700-normal.woff2")
SANS = str(FONTS / "archivo-400_600-normal.woff2")
MONO = str(FONTS / "ibm-plex-mono-400-normal.woff2")

# edge-tts is only needed to regenerate the voice; the cached wavs in demo/lines/ are enough to re-cut
EDGE_TTS = os.environ.get("EDGE_TTS") or shutil.which("edge-tts")

# shot, source, line. `cast` entries carry the cast timestamp the sentence belongs to.
SCRIPT = [
    ("card1", None, "Every memecoin's supply is decided by whoever deployed it."),
    ("card1", None, "GRIP makes supply follow the float that its holders keep locked."),

    ("cast", 0.0, "This is a real run on NEAR testnet: three accounts, created and funded for gas."),
    ("cast", 7.8, "Ten million tokens exist once, at genesis, and thirty percent of them go into a reserve."),
    ("cast", 11.4, "The rest is handed out, so the float sits with the holders, not the deployer."),
    ("cast", 22.9, "Two of them lock, and grip climbs past the sixty percent target."),
    ("cast", 27.4, "The contract reads that number directly. No oracle, no backend."),
    ("cast", 31.1, "The epoch rolls, and one percent of supply mints to both lockers, pro rata."),
    ("cast", 35.7, "One actor exits early, and ten percent of her own lock is burned."),
    ("cast", 40.0, "When the locks reach their deadline, grip collapses on its own, and the burn fires."),

    ("still", "s1_hero.png", "This is the dashboard, reading the same contract."),
    ("still", "s2_chart.png", "Every point here is an epoch the contract applied to itself, not an indexer."),
    ("still", "s3_ledger.png", "Every mint and burn is a transaction you can open."),

    ("card2", None, "No owner mint. No pause. No setters."),
    ("card2", None, "tick() is permissionless: anyone can call it, and nobody can block it."),
    ("card2", None, "Contract, twelve tests, and the sixty epoch study, are in the repository."),
]


def font(path, size):
    return ImageFont.truetype(path, size)


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(str(c) for c in cmd)[:180])
        print(r.stderr[-2500:])
        raise SystemExit(1)
    if not quiet and r.stdout.strip():
        print(r.stdout.strip()[-600:])
    return r


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


# ---------------------------------------------------------------- voice

def synth(idx, text, fresh=False):
    """One file per sentence, so cue times are measured, never guessed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    mp3, wav = CACHE / f"{idx:02d}.mp3", CACHE / f"{idx:02d}.wav"
    if fresh or not wav.exists():
        if not EDGE_TTS:
            raise SystemExit("edge-tts is not installed (pip install edge-tts), and demo/lines/ has no cached "
                             "audio for this line. Set EDGE_TTS=/path/to/edge-tts, or run without --fresh.")
        # the edge endpoint drops requests now and then; a sentence is small enough to just ask again
        last = None
        for attempt in range(4):
            try:
                run([EDGE_TTS, "--voice", VOICE, f"--rate={RATE}", "--text", text,
                     "--write-media", str(mp3)])
                break
            except SystemExit:
                last = attempt
                time.sleep(2 * (attempt + 1))
        else:
            raise SystemExit(f"tts failed for line {idx}: {text!r}")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)])
    return wav


def build_narration(lines, fresh=False):
    """Concatenate the sentences with fixed gaps, in wav, and return their cue times."""
    tmp = Path(tempfile.mkdtemp(prefix="narr-"))
    parts = []
    for i, text in enumerate(lines):
        wav = synth(i, text, fresh)
        with wave.open(str(wav)) as w:
            parts.append((w.getparams(), w.readframes(w.getnframes())))

    params = parts[0][0]
    silence = b"\x00" * (int(params.framerate * GAP) * params.sampwidth)
    lead = b"\x00" * (int(params.framerate * LEAD) * params.sampwidth)
    tail = b"\x00" * (int(params.framerate * TAIL) * params.sampwidth)

    cues, cursor = [], LEAD
    body = [lead]
    for i, (p, data) in enumerate(parts):
        d = len(data) / (params.framerate * params.sampwidth)
        cues.append((cursor, d))
        body.append(data)
        body.append(silence if i < len(parts) - 1 else tail)
        cursor += d + GAP

    out = tmp / "narration.wav"
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        for chunk in body:
            w.writeframes(chunk)
    total = sum(len(c) for c in body) / (params.framerate * params.sampwidth)
    return out, cues, total


# ---------------------------------------------------------------- cards

def ring(d, cx, cy, r, lit=4, segs=6, width=4):
    span = 360 / segs - 14
    start = -90 - span / 2 + 30
    for i in range(segs):
        a0 = start + i * (360 / segs)
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + span,
              fill=LIME if i < lit else (60, 60, 50), width=width)
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=LIME)


def card_one(path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ring(d, 92, 92, 24, width=5)
    d.text((130, 78), "grip", font=font(SERIF, 40), fill=INK)
    d.text((92, 236), "Supply follows", font=font(SERIF, 96), fill=INK)
    d.text((92, 344), "grip.", font=font(SERIF, 96), fill=LIME)
    d.text((96, 470), "Lock the float and the token mints.", font=font(SANS, 27), fill=MUTED)
    d.text((96, 508), "Fold and it burns.", font=font(SANS, 27), fill=MUTED)
    d.text((96, 566), "NEP-141  ·  NEAR TESTNET  ·  NO OWNER MINT", font=font(MONO, 15), fill=FAINT)
    img.save(path)


def card_two(path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ring(d, 92, 92, 24, width=5)
    d.text((130, 78), "grip", font=font(SERIF, 40), fill=INK)
    d.text((92, 188), "No owner mint.", font=font(SERIF, 58), fill=INK)
    d.text((92, 252), "No pause. No setters.", font=font(SERIF, 58), fill=INK)
    rows = [
        ("contract", "grip599cb0.grip-21a10e2e.testnet", LIME),
        ("tests", "12 passing, cargo test", INK),
        ("study", "60 epochs, 108 parameter sets swept", INK),
        ("rule", "tick() is permissionless", INK),
        ("check", "./scripts/verify.sh", INK),
        ("repo", "github.com/farhanqaz/grip-memecoin", INK),
    ]
    y = 352
    for k, v, col in rows:
        d.text((96, y), k, font=font(MONO, 15), fill=FAINT)
        d.text((216, y - 2), v, font=font(MONO, 19), fill=col)
        y += 39
        d.line([(96, y - 11), (1184, y - 11)], fill=(28, 28, 26), width=1)
    d.text((96, 578), "BUILT AT NEAR HACKATHON 2026  ·  TRACK MEMECOINS", font=font(MONO, 14), fill=FAINT)
    img.save(path)


# ---------------------------------------------------------------- motion

def encode(frames, path):
    """Pipe frames straight into x264: no intermediate PNGs, no filter graph to fight."""
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(path)],
        stdin=subprocess.PIPE)
    for im in frames:
        p.stdin.write(im.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()


def zoom(src, start_scale, end_scale, seconds):
    """Sub-pixel zoom: the affine source rect is fractional, so motion is smooth at any speed.

    zoompan, which the first cut used, crops on integer pixels. That is exactly why it juddered.
    """
    im = Image.open(src).convert("RGB")
    total = max(2, int(round(seconds * FPS)))
    big = (int(W * SS), int(H * SS))
    cx, cy = im.width / 2, im.height / 2
    for n in range(total):
        s = start_scale + (end_scale - start_scale) * (n / (total - 1))
        a = 1.0 / (SS * s)
        # at x=0 the source coordinate must be cx - (W/s)/2, and the step per output pixel is
        # 1/(SS*s): anything else shifts the picture instead of framing it
        ox, oy = cx - (big[0] / 2) * a, cy - (big[1] / 2) * a
        frame = im.transform(big, Image.AFFINE, (a, 0, ox, 0, a, oy), resample=Image.BICUBIC)
        yield frame.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- subtitles

def wrap_text(d, text, f, max_w):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=f) > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def subtitle_band(text, path):
    """1280x170 RGBA strip: one or two lines, centred, outlined so it reads on any frame."""
    img = Image.new("RGBA", (W, 170), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(SANS, 31)
    lines = wrap_text(d, text, f, W - 240)
    lh = 42
    y = 170 - 30 - lh * len(lines)
    for line in lines:
        tw = d.textlength(line, font=f)
        d.text(((W - tw) / 2, y), line, font=f, fill=(244, 241, 234, 255),
               stroke_width=4, stroke_fill=(10, 10, 9, 240))
        y += lh
    img.save(path)


# ---------------------------------------------------------------- the cut

def main():
    fresh = "--fresh" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="film-"))

    narration, cues, total = build_narration([t for _, _, t in SCRIPT], fresh)
    starts = [c[0] for c in cues]
    durs = [c[1] for c in cues]

    def first(shot):
        return min(starts[i] for i, e in enumerate(SCRIPT) if e[0] == shot)

    cast_start = first("cast")
    card2_start = first("card2")
    still_i = [i for i, e in enumerate(SCRIPT) if e[0] == "still"]
    bounds = [starts[i] for i in still_i] + [card2_start]

    print(f"narration {total:.1f}s · {len(SCRIPT)} cues · cast shot {bounds[0] - cast_start:.1f}s")

    # 1. opening card
    c1, c2 = tmp / "c1.png", tmp / "c2.png"
    card_one(c1)
    card_two(c2)
    seg1 = tmp / "s1.mp4"
    encode(zoom(c1, 1.0, 1.018, cast_start), seg1)

    # 2. the recorded run, retimed so every beat sits under the sentence that names it
    beats = [(e[1], starts[i] - cast_start) for i, e in enumerate(SCRIPT) if e[0] == "cast"]
    beats.append((46.0, bounds[0] - cast_start))
    raw = tmp / "cast.mp4"
    run(["python3", str(ROOT / "tools" / "cast2mp4.py"), str(ROOT / "demo" / "demo.cast"),
         str(raw), "--title", "grip-hackathon/demo  ·  node run.mjs, live on NEAR testnet",
         "--beats", ",".join(f"{a:.2f}:{b:.2f}" for a, b in beats)], quiet=False)
    seg2 = tmp / "s2.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-r", str(FPS), "-an",
         "-vf", f"scale={W}:{H}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(seg2)])

    # 3. the dashboard, one still per sentence, settling rather than pushing in
    stills = []
    for k, i in enumerate(still_i):
        seg = tmp / f"still{k}.mp4"
        encode(zoom(STILLS / SCRIPT[i][1], 1.055, 1.0, bounds[k + 1] - bounds[k]), seg)
        stills.append(seg)

    # 4. closing card
    seg4 = tmp / "s4.mp4"
    encode(zoom(c2, 1.0, 1.015, total - card2_start), seg4)

    # 5. picture, then subtitles, then voice
    liste = tmp / "list.txt"
    parts = [seg1, seg2] + stills + [seg4]
    liste.write_text("".join(f"file '{p}'\n" for p in parts))
    silent = tmp / "silent.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(liste),
         "-c", "copy", str(silent)])

    subl = tmp / "subs"
    subl.mkdir()
    blank = tmp / "blank.png"
    Image.new("RGBA", (W, 170), (0, 0, 0, 0)).save(blank)
    cue_png = {}
    for i in range(len(cues)):
        p = tmp / f"cue{i}.png"
        subtitle_band(SCRIPT[i][2], p)
        cue_png[i] = p

    current = -2
    for n in range(int(round(total * FPS))):
        t = n / FPS
        want = next((i for i, (s, d) in enumerate(cues) if s - 0.06 <= t < s + d + 0.12), None)
        dst = subl / f"f{n:05d}.png"
        if want != current:
            shutil.copy(cue_png[want] if want is not None else blank, dst)
            current = want
        else:
            try:
                os.link(subl / f"f{n - 1:05d}.png", dst)
            except OSError:
                shutil.copy(subl / f"f{n - 1:05d}.png", dst)

    burned = tmp / "burned.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent),
         "-framerate", str(FPS), "-i", str(subl / "f%05d.png"),
         "-filter_complex", "[0:v][1:v]overlay=0:550:format=auto,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(burned)])

    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(burned), "-i", str(narration),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(OUT)])

    print(f"{OUT.relative_to(ROOT)}: {probe_duration(OUT):.1f}s · {OUT.stat().st_size / 1e6:.1f} MB")
    for i, (s, d) in enumerate(cues):
        print(f"  {s:6.2f} +{d:4.2f}  {SCRIPT[i][0]:6s} {SCRIPT[i][2][:62]}")
    print("workdir", tmp)


if __name__ == "__main__":
    main()
