#!/usr/bin/env python3
"""Make each tile's flat background transparent.

Every tile is drawn on a uniform backing colour. Tiles at the edge of the
complex have real art *plus* that backing, so drawing them paints a grey slab
over whatever wallpaper sits behind — which is exactly the "grey patches around
the render" problem.

This finds each tile's backing colour (its most common pixel value) and writes
vendor/keyed/<tile>.png with those pixels fully transparent. Art pixels are
untouched: no tolerance, no feathering, because the source is flat-colour pixel
art and an approximate key leaves halos.

    python3 tools/build_keyed.py            # all content tiles
    python3 tools/build_keyed.py t3l1 b1r5
"""

import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Every empty tile is exactly this colour (verified across ten of them), so the
# void is a global constant, not a per-tile mode. Using the per-tile most-common
# colour keys a room's floor instead and leaves the actual void opaque.
VOID = (51, 51, 51)

SRC = os.path.join(ROOT, "vendor", "rips")
OUT = os.path.join(ROOT, "vendor", "keyed")
INDEX = os.path.join(ROOT, "vendor", "content_index.json")


def _record(tid, pct):
    """Remember the keyed fraction so the renderer can avoid animating a tile
    that is mostly backing (its frames would paint the slab back in)."""
    idx = os.path.join(ROOT, "vendor", "keyed_index.json")
    try:
        with open(idx) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d[tid] = round(pct, 1)
    os.makedirs(os.path.dirname(idx), exist_ok=True)
    with open(idx, "w") as f:
        json.dump(d, f, indent=0, sort_keys=True)


def key_tile(tid):
    dst = os.path.join(OUT, f"{tid}.png")
    if os.path.exists(dst) and os.path.getsize(dst) > 1024:
        return tid, "exists", 0
    src = os.path.join(SRC, f"{tid}.webp")
    if not os.path.exists(src):
        return tid, "missing", 0
    im = Image.open(src).convert("RGBA")
    bg = VOID
    px = im.load()
    w, h = im.size
    keyed = 0
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if p[0] == bg[0] and p[1] == bg[1] and p[2] == bg[2]:
                px[x, y] = (0, 0, 0, 0)
                keyed += 1
    os.makedirs(OUT, exist_ok=True)
    im.save(dst, optimize=True)
    pct = 100 * keyed / (w * h)
    _record(tid, pct)
    return tid, f"bg {bg} keyed {pct:.0f}%", os.path.getsize(dst)


def main():
    want = sys.argv[1:]
    if not want:
        try:
            with open(INDEX) as f:
                empty = set(json.load(f)["empty"])
        except Exception:
            empty = set()
        want = [f[:-5] for f in os.listdir(SRC)
                if f.endswith(".webp") and f[:-5] not in empty]
    print(f"keying {len(want)} content tiles -> {OUT}")
    tot = 0
    for tid in want:
        n, what, size = key_tile(tid)
        tot += size
        print(f"  {tid}: {what}  {size/1e6:.2f} MB")
    print(f"total {tot/1e6:.1f} MB")


if __name__ == "__main__":
    main()
