#!/usr/bin/env python3
"""Rip the original-quality tiles from floor796's per-tile mp4s.

The `preview_b` WebPs in matrix.json are low-quality thumbnails: their edge
energy is ~2.7 vs ~39.7 for the real artwork, which is why anything rendered
from them looks blurry. The per-tile mp4 (1024x820, 60 frames, h264) is the
actual artwork stream the site plays.

For each tile this downloads the mp4 and extracts frame 0 to a **lossless**
WebP in vendor/rips/. Lossless matters: pixel art + lossy codecs = smeared
edges, which is the bug we're fixing.

    python3 tools/rip_tiles.py            # all missing tiles
    python3 tools/rip_tiles.py t3l1 b1r5  # specific tiles
    python3 tools/rip_tiles.py --frames 0,30   # several frames per tile

Requires ffmpeg and curl. ~4 MB of mp4 per tile, ~0.9 MB of lossless WebP out.
"""

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CDN = "https://cdn.floor796.com/data/"
RIPS = os.path.join(ROOT, "vendor", "rips")
WORKERS = 4


def load(name):
    with open(os.path.join(ROOT, "vendor", name)) as f:
        return json.load(f)


def tile_table(matrix):
    out = {}
    for row in matrix["mat"]:
        for t in row:
            if isinstance(t, dict) and t.get("id") and t.get("video", {}).get("mp4"):
                out[t["id"]] = t["video"]["mp4"]
    return out


def rip(tid, rel, frames):
    os.makedirs(RIPS, exist_ok=True)
    made = []
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = os.path.join(tmp, f"{tid}.mp4")
        subprocess.run(["curl", "-fsSL", CDN + rel, "-o", mp4],
                       check=True, timeout=180)
        for n in frames:
            suffix = "" if n == 0 else f"_{n}"
            dst = os.path.join(RIPS, f"{tid}{suffix}.webp")
            if os.path.exists(dst) and os.path.getsize(dst) > 1024:
                made.append(dst)
                continue
            # -vf select keeps the frame index exact; -lossless 1 preserves
            # every pixel of the source frame.
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", mp4,
                 "-vf", f"select=eq(n\\,{n})", "-frames:v", "1",
                 "-c:v", "libwebp", "-lossless", "1", "-compression_level", "6",
                 dst],
                check=True, timeout=180)
            made.append(dst)
    return tid, made


def main():
    args = [a for a in sys.argv[1:]]
    frames = [0]
    if "--frames" in args:
        i = args.index("--frames")
        frames = [int(x) for x in args[i + 1].split(",")]
        del args[i:i + 2]

    table = tile_table(load("matrix.json"))
    todo = [(tid, table[tid]) for tid in (args or table) if tid in table]
    if not todo:
        sys.exit("no matching tiles")

    print(f"ripping {len(todo)} tile(s), frames {frames}")
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(rip, tid, rel, frames): tid for tid, rel in todo}
        for fut in as_completed(futures):
            tid = futures[fut]
            try:
                _, made = fut.result()
                done += 1
                if done % 10 == 0 or len(todo) <= 12:
                    size = sum(os.path.getsize(p) for p in made) / 1e6
                    print(f"  [{done}/{len(todo)}] {tid}: {size:.1f} MB")
            except Exception as e:
                print(f"  [{tid}] FAILED: {e}")

    total = sum(os.path.getsize(os.path.join(RIPS, f))
                for f in os.listdir(RIPS)) / 1e6
    print(f"done: {done}/{len(todo)} tiles, vendor/rips now {total:.1f} MB")


if __name__ == "__main__":
    main()
