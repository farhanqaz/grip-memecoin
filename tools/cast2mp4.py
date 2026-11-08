"""Render an asciinema-style cast (the format tools/rec.py writes) into a real mp4.

  python3 tools/cast2mp4.py demo/demo.cast demo/demo.mp4 --title "npm run demo"

It replays the recorded events at their original timestamps, so the video is a recording of the run,
not a re-enactment: frame timing and line order are whatever the child process actually produced.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
BG = (11, 12, 14)
FG = (216, 220, 226)
DIM = (120, 128, 138)
ACCENT = (74, 222, 128)
BAR = (18, 20, 23)

W, H = 1280, 720
FS = 21
LH = 27
COLS = 84
ROWS = 22
PAD_X, PAD_TOP, BAR_H = 42, 62, 38


def load(cast_path):
    with open(cast_path) as f:
        header = json.loads(f.readline())
        events = [json.loads(line) for line in f if line.strip()]
    return header, events


def screen_state(lines, rows=ROWS):
    """Keep the last `rows` logical lines, with a cursor block on the final one."""
    return lines[-rows:]


def render(lines, title, t_now, t_total):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, FS)
    bold = ImageFont.truetype(BOLD, FS)
    small = ImageFont.truetype(FONT, 13)

    # window bar
    d.rectangle([0, 0, W, BAR_H], fill=BAR)
    d.ellipse([16, 14, 26, 24], fill=(240, 95, 90))
    d.ellipse([32, 14, 42, 24], fill=(250, 200, 90))
    d.ellipse([48, 14, 58, 24], fill=(80, 200, 120))
    d.text((W // 2, BAR_H // 2), title, font=small, fill=DIM, anchor="mm")

    # progress hairline
    d.rectangle([0, BAR_H, int(W * min(1.0, t_now / max(t_total, 0.001))), BAR_H + 2], fill=ACCENT)

    y = PAD_TOP
    for i, line in enumerate(screen_state(lines)):
        last = i == len(screen_state(lines)) - 1
        color = FG
        if line.startswith("---"):
            color = ACCENT
        elif line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
            color = (255, 255, 255)
        elif "supply" in line and "|" in line:
            color = (170, 200, 230)
        f = bold if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")) else font
        d.text((PAD_X, y), line, font=f, fill=color)
        if last:
            w = d.textlength(line, font=f)
            d.rectangle([PAD_X + w + 2, y - 1, PAD_X + w + 12, y + LH - 5], fill=ACCENT)
        y += LH
    return img


def wrap(text, cols=COLS):
    out = []
    for raw in text.split("\n"):
        while len(raw) > cols:
            out.append(raw[:cols])
            raw = raw[cols:]
        out.append(raw)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cast")
    ap.add_argument("out")
    ap.add_argument("--title", default="npm run demo")
    ap.add_argument("--audio", help="optional narration mp3; the video is padded to fit it")
    ap.add_argument("--min-duration", type=float, default=0.0)
    ap.add_argument("--beats", help='pin cast timestamps to film timestamps: "0:0,7.8:1.5,46:30"')
    args = ap.parse_args()

    header, events = load(args.cast)
    cast_total = events[-1][0] + 2.5 if events else 3.0

    # A beat map is piecewise linear: between two anchors the picture plays at whatever rate gets it to
    # the next line on time. That is how the edit stays in sync with the voice without cutting content.
    if args.beats:
        pts = sorted(tuple(float(v) for v in a.split(":")) for a in args.beats.split(","))

        def tmap(t):
            if t <= pts[0][0]:
                return pts[0][1]
            for (a0, f0), (a1, f1) in zip(pts, pts[1:]):
                if t <= a1:
                    return f1 if a1 == a0 else f0 + (f1 - f0) * (t - a0) / (a1 - a0)
            return pts[-1][1]
    else:
        pts = None

        def tmap(t):
            return t

    total = tmap(cast_total)
    total = max(total, args.min_duration)

    tmp = tempfile.mkdtemp(prefix="cast2mp4-")
    frames = []
    lines = []
    idx = 0

    for i, (t, kind, data) in enumerate(events):
        if kind != "o":
            continue
        lines.extend(wrap(data))
        nxt = events[i + 1][0] if i + 1 < len(events) else cast_total
        ft, fnxt = tmap(t), tmap(nxt)
        hold = max(0.05, fnxt - ft)
        path = os.path.join(tmp, f"f{idx:05d}.png")
        render(lines, args.title, ft, total).save(path)
        frames.append((path, hold, ft))
        idx += 1

    # tail: hold the final screen so the narration can finish
    if frames:
        last_path = frames[-1][0]
        pad = max(0.0, total - (frames[-1][2] + frames[-1][1]))
        frames.append((last_path, max(1.5, pad + 1.5), total))

    concat = os.path.join(tmp, "list.txt")
    with open(concat, "w") as f:
        f.write("ffconcat version 1.0\n")
        for path, hold, _ in frames:
            f.write(f"file '{path}'\nduration {hold:.3f}\n")
        f.write(f"file '{frames[-1][0]}'\n")

    silent = os.path.join(tmp, "silent.mp4")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat,
         "-fps_mode", "cfr", "-r", "5", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         silent],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("ffmpeg failed:\n", r.stderr[-3000:])
        print("list kept at", concat)
        raise SystemExit(1)

    if args.audio:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", args.audio,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", args.out],
            check=True,
        )
    else:
        shutil.move(silent, args.out)

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nw=1:nk=1", args.out],
                               capture_output=True, text=True, check=True).stdout.strip())
    print(f"{args.out}: {dur:.1f}s, {len(frames)} frames, {os.path.getsize(args.out) / 1e6:.1f} MB")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
