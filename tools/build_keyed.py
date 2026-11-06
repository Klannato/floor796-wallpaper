#!/usr/bin/env python3
"""Make each tile's void transparent — but only the void.

Every tile is drawn on a uniform backing colour. Tiles at the edge of the
complex have real art *plus* that backing, so drawing them paints a grey slab
over whatever wallpaper sits behind.

Keying *every* pixel of that colour punches holes in legitimate dark artwork —
stray transparent pixels along the art edge. The void is connected, though: from
any empty tile you can walk to any other without crossing art. So only pixels of
that colour **reachable from the tile border** are keyed, and enclosed dark
areas inside the art survive because the fill cannot reach them.

    python3 tools/build_keyed.py              # all content tiles
    python3 tools/build_keyed.py t3l1 b1r5    # specific tiles
    python3 tools/build_keyed.py --force      # rebuild existing
"""

import json
import os
import sys
from collections import deque

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Every empty tile is exactly this colour (verified across ten of them), so the
# void is a global constant, not a per-tile mode.
VOID = (51, 51, 51)

SRC = os.path.join(ROOT, "vendor", "rips")
OUT = os.path.join(ROOT, "vendor", "keyed")
INDEX = os.path.join(ROOT, "vendor", "content_index.json")


def flood_from_border(w, h, is_void):
    """4-connected fill of void pixels reachable from the tile border."""
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            i = y * w + x
            if is_void[i] and not seen[i]:
                seen[i] = 1
                q.append(i)
    for y in range(h):
        for x in (0, w - 1):
            i = y * w + x
            if is_void[i] and not seen[i]:
                seen[i] = 1
                q.append(i)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        if x and is_void[i - 1] and not seen[i - 1]:
            seen[i - 1] = 1
            q.append(i - 1)
        if x + 1 < w and is_void[i + 1] and not seen[i + 1]:
            seen[i + 1] = 1
            q.append(i + 1)
        if y and is_void[i - w] and not seen[i - w]:
            seen[i - w] = 1
            q.append(i - w)
        if y + 1 < h and is_void[i + w] and not seen[i + w]:
            seen[i + w] = 1
            q.append(i + w)
    return seen


def _record(tid, pct):
    """Keyed fraction, so the renderer knows how much of a tile is void."""
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


def key_tile(tid, force=False):
    dst = os.path.join(OUT, f"{tid}.png")
    if os.path.exists(dst) and os.path.getsize(dst) > 1024 and not force:
        return tid, "exists", 0
    src = os.path.join(SRC, f"{tid}.webp")
    if not os.path.exists(src):
        return tid, "missing", 0

    im = Image.open(src).convert("RGBA")
    w, h = im.size
    data = im.tobytes()
    n = w * h

    is_void = bytearray(n)
    for i in range(n):
        o = i * 4
        if (data[o], data[o + 1], data[o + 2]) == VOID:
            is_void[i] = 1

    reach = flood_from_border(w, h, is_void)

    out = bytearray(data)
    keyed = 0
    for i in range(n):
        if reach[i]:
            o = i * 4
            out[o] = out[o + 1] = out[o + 2] = out[o + 3] = 0
            keyed += 1
    im = Image.frombytes("RGBA", (w, h), bytes(out))

    os.makedirs(OUT, exist_ok=True)
    im.save(dst, optimize=True)
    pct = 100 * keyed / n
    _record(tid, pct)
    return tid, f"keyed {pct:.0f}%", os.path.getsize(dst)


def main():
    args = [a for a in sys.argv[1:]]
    force = "--force" in args
    if force:
        args.remove("--force")
    want = args
    if not want:
        try:
            with open(INDEX) as f:
                empty = set(json.load(f)["empty"])
        except Exception:
            empty = set()
        want = [f[:-5] for f in os.listdir(SRC)
                if f.endswith(".webp") and f[:-5] not in empty]

    print(f"keying {len(want)} tile(s){' (force)' if force else ''} -> {OUT}")
    tot = 0
    for tid in want:
        name, what, size = key_tile(tid, force)
        tot += size
        print(f"  {name}: {what}  {size/1e6:.2f} MB")
    print(f"total {tot/1e6:.1f} MB")


if __name__ == "__main__":
    main()
