"""Record a command's real output with timestamps, asciinema-cast style.

  python3 tools/rec.py demo/demo.cast -- npm run demo

Writes [time, "o", text] events in the order the child actually produced them, so the video built from
this is a recording of a real run, not a rendering of a script.
"""

import json
import subprocess
from pathlib import Path
import sys
import time

CAST = sys.argv[1]
CMD = sys.argv[3:] if sys.argv[2] == "--" else sys.argv[2:]

start = time.monotonic()
events = []

with open(CAST, "w") as f:
    f.write(json.dumps({"version": 2, "width": 110, "height": 34, "timestamp": int(time.time())}) + "\n")
    f.flush()

    proc = subprocess.Popen(
        CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(Path(__file__).resolve().parent.parent / "demo"),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        t = round(time.monotonic() - start, 3)
        sys.stdout.write(line)
        sys.stdout.flush()
        events.append([t, "o", line])
        f.write(json.dumps([t, "o", line]) + "\n")
        f.flush()
    proc.wait()

duration = round(time.monotonic() - start, 3)
print(f"\nrecorded {len(events)} events, {duration}s -> {CAST}")
