#!/usr/bin/env python3
"""Pack each tile's mp4 loop into one vertical sprite sheet of lossless WebP frames.

Why not decode at runtime: a GStreamer pipeline per visible tile costs ~10% of a
core each and churns memory through Python. A wallpaper should not do that. A
pre-packed sheet turns animation into "index into an image", which is a blit.

Each sheet is 60 frames of one tile stacked vertically:
    frame i lives at (0, i * FRAME_H)
so the renderer draws the sheet offset upward by i*frame_h and clips to the tile.

Tiles whose frames are all identical are reported as static and get no sheet —
most of the map doesn't move, and skipping them saves both disk and RAM.

    python3 tools/pack_frames.py            # all tiles, skips existing
    python3 tools/pack_frames.py t3l1 b1r5  # specific tiles
"""

import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image, ImageChops, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "vendor", "mp4")
OUT = os.path.join(ROOT, "vendor", "anim_512")   # --size overrides
SIZES = {256: (256, 205), 512: (512, 410), 1024: (1024, 820)}
FRAME_W, FRAME_H = SIZES[512][0], SIZES[512][1]   # replaced by --size
SHEET_COLS = 8                   # 8x8 grid: WebP refuses images >16383 px
WORKERS = 4
STATIC_THRESHOLD = 1.0           # mean abs diff below this => tile is static


def pack(tid):
    src = os.path.join(SRC, f"{tid}.mp4")
    dst = os.path.join(OUT, f"{tid}.raw")
    if os.path.exists(dst) and os.path.getsize(dst) > 1024:
        return tid, "exists", 0

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", src,
             "-vf", f"scale={FRAME_W}:{FRAME_H}:flags=neighbor",
             "-c:v", "png", os.path.join(tmp, "f%03d.png")],
            check=True, timeout=300)
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        if not frames:
            return tid, "no frames", 0

        first = Image.open(os.path.join(tmp, frames[0])).convert("RGB")
        moving = False
        for f in frames[1:]:
            im = Image.open(os.path.join(tmp, f)).convert("RGB")
            if ImageStat.Stat(ImageChops.difference(first, im)).mean[0] > STATIC_THRESHOLD:
                moving = True
                break
        if not moving:
            return tid, "static", 0

        imgs = [Image.open(os.path.join(tmp, f)).convert("RGB") for f in frames]
        os.makedirs(OUT, exist_ok=True)
        # Raw BGRX, one frame after another: frame i sits at i*FRAME_BYTES, so
        # the renderer mmaps the file and points cairo at a slice — no decode,
        # no copy. (A grid sheet would scatter each frame across rows.)
        with open(dst, "wb") as f:
            for im in imgs:
                rgba = im.convert("RGBA")
                r, g, b, a = rgba.split()
                f.write(Image.merge("RGBA", (b, g, r, a)).tobytes())
        return tid, f"packed {len(imgs)}f", os.path.getsize(dst)


def main():
    global FRAME_W, FRAME_H, OUT
    args = sys.argv[1:]
    if "--size" in args:
        i = args.index("--size")
        size = int(args[i + 1])
        del args[i:i + 2]
        if size not in SIZES:
            sys.exit(f"--size must be one of {sorted(SIZES)}")
        FRAME_W, FRAME_H = SIZES[size]
        OUT = os.path.join(ROOT, "vendor", f"anim_{size}")
    want = args or sorted(f[:-4] for f in os.listdir(SRC) if f.endswith(".mp4"))
    os.makedirs(OUT, exist_ok=True)
    print(f"packing {len(want)} tile(s) at {FRAME_W}x{FRAME_H} -> {OUT}")
    stats = {"packed": 0, "static": 0, "exists": 0}
    total = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(pack, tid): tid for tid in want}
        for fut in as_completed(futs):
            tid = futs[fut]
            try:
                _, what, size = fut.result()
                if what.startswith("packed"):
                    stats["packed"] += 1
                    total += size
                elif what == "static":
                    stats["static"] += 1
                elif what == "exists":
                    stats["exists"] += 1
                if what.startswith("packed"):
                    print(f"  {tid}: {what} {size/1e6:.2f} MB")
            except Exception as e:
                print(f"  {tid} FAILED: {e}")

    print(f"\npacked {stats['packed']}, static {stats['static']}, "
          f"already {stats['exists']}  ({total/1e6:.1f} MB new)")
    if os.path.isdir(OUT):
        allsz = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
        print(f"{OUT}: {allsz/1e9:.2f} GB, {len(os.listdir(OUT))} sheets")


if __name__ == "__main__":
    main()
