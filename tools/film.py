"""Build the demo film: cards, the real recorded run, and stills of the live dashboard.

    python3 tools/film.py <narration.mp3> <out.mp4>

Every moving part is real: the terminal segment is `tools/rec.py`'s capture of an actual testnet run,
and the dashboard frames are screenshots of the deployed page reading the same contract. Nothing here is
a mock; the editing only decides what you look at and when.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "docs" / "fonts"
W, H = 1280, 720
FPS = 25

BG = (11, 11, 10)
INK = (244, 241, 234)
MUTED = (142, 138, 128)
FAINT = (93, 90, 84)
LIME = (203, 255, 77)

SERIF = str(FONT_DIR / "fraunces-300_700-normal.woff2")
SANS = str(FONT_DIR / "archivo-400_600-normal.woff2")
MONO = str(FONT_DIR / "ibm-plex-mono-400-normal.woff2")

CAST = ROOT / "demo" / "demo.cast"
STILLS = ROOT / "docs" / "film"


def font(path, size, weight=None):
    f = ImageFont.truetype(path, size)
    if weight:
        f.set_variation_by_axes([weight])
    return f


def ring(draw, cx, cy, r, lit=4, segs=6, width=4):
    """The GRIP mark: six segments, four lit."""
    import math
    gap = 14
    span = 360 / segs - gap
    start = -90 - span / 2 + 30
    for i in range(segs):
        a0 = start + i * (360 / segs)
        col = LIME if i < lit else (60, 60, 50)
        draw.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + span, fill=col, width=width)
    draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=LIME)


def card_one(path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ring(d, 92, 92, 24, width=5)
    d.text((130, 78), "grip", font=font(SERIF, 40, 600), fill=INK)

    d.text((92, 236), "Supply follows", font=font(SERIF, 96, 500), fill=INK)
    d.text((92, 344), "grip.", font=font(SERIF, 96, 500), fill=LIME)

    d.text((96, 486), "Lock the float and the token mints.", font=font(SANS, 27, 400), fill=MUTED)
    d.text((96, 524), "Fold and it burns.", font=font(SANS, 27, 400), fill=MUTED)

    d.text((96, 618), "NEP-141  ·  NEAR TESTNET  ·  NO OWNER MINT", font=font(MONO, 15), fill=FAINT)
    img.save(path)


def card_two(path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ring(d, 92, 92, 24, width=5)
    d.text((130, 78), "grip", font=font(SERIF, 40, 600), fill=INK)

    d.text((92, 190), "No owner mint.", font=font(SERIF, 58, 500), fill=INK)
    d.text((92, 254), "No pause. No setters.", font=font(SERIF, 58, 500), fill=INK)

    rows = [
        ("contract", "grip5391e9.grip-21a10e2e.testnet", LIME),
        ("tests", "11 passing, cargo test", INK),
        ("study", "60 epochs, 108 parameter sets swept", INK),
        ("rule", "tick() is permissionless", INK),
        ("check", "./scripts/verify.sh", INK),
        ("repo", "github.com/farhanqaz/grip-memecoin", INK),
    ]
    y = 372
    for k, v, col in rows:
        d.text((96, y), k, font=font(MONO, 15), fill=FAINT)
        d.text((216, y - 2), v, font=font(MONO, 19), fill=col)
        y += 42
        d.line([(96, y - 12), (1184, y - 12)], fill=(28, 28, 26), width=1)

    d.text((96, 654), "BUILT AT NEAR HACKATHON 2026  ·  TRACK MEMECOINS", font=font(MONO, 14), fill=FAINT)
    img.save(path)


def caption(path, text, sub=None):
    """Full-frame transparent overlay: a line of text on a soft scrim, bottom left."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(SANS, 30, 500)
    fs = font(SANS, 21, 400)
    pad = 26
    tw = d.textlength(text, font=f)
    sw = d.textlength(sub, font=fs) if sub else 0
    box_w = max(tw, sw) + pad * 2
    box_h = (86 if sub else 62)
    x0, y0 = 64, H - box_h - 56
    d.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=4, fill=(11, 11, 10, 232))
    d.rectangle([x0, y0, x0 + 3, y0 + box_h], fill=LIME)  # a hairline, not a decoration
    d.text((x0 + pad, y0 + 14), text, font=f, fill=INK)
    if sub:
        d.text((x0 + pad, y0 + 52), sub, font=fs, fill=MUTED)
    img.save(path)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd)[:200])
        print(r.stderr[-2500:])
        raise SystemExit(1)


def still_segment(src, out, seconds, zoom="in"):
    frames = int(seconds * FPS)
    if zoom == "in":
        z = f"min(1+0.0008*on,1.08)"
    elif zoom == "out":
        z = f"max(1.08-0.0008*on,1.0)"
    else:
        z = "1.04"
    vf = (
        f"scale=1400:-1,zoompan=z='{z}':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},format=yuv420p"
    )
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(src),
         "-vf", vf, "-t", str(seconds), "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def hold_segment(src, out, seconds):
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(src),
         "-t", str(seconds), "-r", str(FPS), "-vf", f"scale={W}:{H},format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def main():
    narration = Path(sys.argv[1])
    out = Path(sys.argv[2])
    tmp = Path(tempfile.mkdtemp(prefix="film-"))

    # 1. cards
    c1, c2 = tmp / "c1.png", tmp / "c2.png"
    card_one(c1)
    card_two(c2)

    # 2. the recorded terminal run, silent, with captions laid over the exact beats
    term = tmp / "term_silent.mp4"
    run(["python3", str(ROOT / "tools" / "cast2mp4.py"), str(CAST), str(term),
         "--title", "grip-hackathon/demo  ·  node run.mjs (NEAR testnet, live)"])

    caps = [
        (2.0, 8.6, "Three accounts, funded from genesis", "no wallet, no backend"),
        (20.0, 27.0, "Two of them lock: grip 71%", "above the 60% target"),
        (28.5, 35.0, "An epoch rolls: 1% mints to both lockers", "pro rata, paid out unlocked"),
        (36.0, 40.6, "One actor exits early: 10% of her lock burns", "her own tokens, not anyone else's"),
        (41.2, 46.5, "Locks hit their deadline: grip collapses, burn fires", "grip has to be maintained"),
    ]
    inputs = ["-i", str(term)]
    filters = []
    last = "[0:v]"
    for i, (t0, t1, txt, sub) in enumerate(caps, start=1):
        p = tmp / f"cap{i}.png"
        caption(p, txt, sub)
        inputs += ["-loop", "1", "-i", str(p)]
        nxt = f"[v{i}]"
        filters.append(f"{last}[{i}:v]overlay=0:0:enable='between(t,{t0},{t1})'{nxt}")
        last = nxt
    filters.append(f"{last}format=yuv420p[vout]")
    seg2 = tmp / "seg2.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
        ["-filter_complex", ";".join(filters), "-map", "[vout]",
         "-r", str(FPS), "-t", "46.5", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(seg2)])

    # 3. the live dashboard, three stills
    seg3, seg4, seg5 = tmp / "seg3.mp4", tmp / "seg4.mp4", tmp / "seg5.mp4"
    # settle rather than push in: a zoom that ends at 1.0 never crops the page, and these stills are dense
    still_segment(STILLS / "s1_hero.png", seg3, 8.0, "out")
    still_segment(STILLS / "s2_chart.png", seg4, 8.0, "out")
    still_segment(STILLS / "s3_ledger.png", seg5, 6.0, "out")

    # 4. cards
    seg1, seg6 = tmp / "seg1.mp4", tmp / "seg6.mp4"
    hold_segment(c1, seg1, 7.5)
    hold_segment(c2, seg6, 9.0)

    # 5. concat, then lay the narration over it
    liste = tmp / "list.txt"
    parts = [seg1, seg2, seg3, seg4, seg5, seg6]
    liste.write_text("".join(f"file '{p}'\n" for p in parts))
    silent = tmp / "silent.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(liste),
         "-c", "copy", str(silent)])
    # pad the narration rather than cutting the picture: the closing card should sit in silence
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(narration),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-af", "apad=pad_dur=12", "-shortest", str(out)])

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(out)], capture_output=True, text=True).stdout.strip()
    print(f"{out}: {float(dur):.1f}s, {os.path.getsize(out)/1e6:.1f} MB, {len(parts)} segments")
    print("frames kept in", tmp)


if __name__ == "__main__":
    main()
