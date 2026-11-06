#!/usr/bin/env python3
"""Build half-resolution hologram packs (vendor/holo_lo).

A full hologram scene is 60 frames of 805x646 = 125 MB of page cache. At the
default 0.5 zoom the projection is only ~400 px wide on screen, so the half-res
set is 1:1 and costs 31 MB instead.

Frames are resized individually with NEAREST — bilinear would smear the
pixel-art edges, same reason the renderer never uses it.
"""

import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "vendor", "holo")
OUT = os.path.join(ROOT, "vendor", "holo_lo")
W, H = 805, 646
FW, FH = W // 2, H // 2
FRAME_BYTES = W * H * 4


def main():
    if not os.path.isdir(SRC):
        sys.exit(f"no {SRC} — run tools/rip_hologram.py first")
    os.makedirs(OUT, exist_ok=True)
    for name in sorted(f for f in os.listdir(SRC) if f.endswith(".raw")):
        dst = os.path.join(OUT, name)
        if os.path.exists(dst) and os.path.getsize(dst) > 1024:
            print(f"  {name}: exists")
            continue
        with open(os.path.join(SRC, name), "rb") as f:
            data = f.read()
        n = len(data) // FRAME_BYTES
        chunks = []
        for i in range(n):
            off = i * FRAME_BYTES
            im = Image.frombytes("RGBA", (W, H), data[off:off + FRAME_BYTES],
                                 "raw", "BGRA")
            chunks.append(im.resize((FW, FH), Image.NEAREST)
                          .tobytes("raw", "BGRA"))
        with open(dst, "wb") as f:
            for c in chunks:
                f.write(c)
        print(f"  {name}: {n} frames -> {os.path.getsize(dst)/1e6:.1f} MB")
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"vendor/holo_lo: {total/1e6:.1f} MB")


if __name__ == "__main__":
    main()
