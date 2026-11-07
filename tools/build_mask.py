#!/usr/bin/env python3
"""Build a silhouette mask for the scene — the file you edit in GIMP.

White = keep (art), black = cut (void, wallpaper shows through).

The starter comes from the keyed tiles (flat #333333 backing knocked out), so
most of the outline is already correct. The point of hand-editing is to fix what
a colour key gets wrong: interiors that happen to be flat, or single-colour art.

Output is cropped to the art bounding box so it stays a sane image to edit:
    vendor/mask_base.png   8136x8128, 8-bit greyscale

    python3 tools/build_mask.py
"""

import json
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def content_index():
    """The art bounding box, computed by the scene if nobody has yet.

    `vendor/content_index.json` is a cache `Scene` writes on first use; a fresh
    clone has not run the app, and this tool used to fail on the missing file.
    """
    path = os.path.join(ROOT, "vendor", "content_index.json")
    if not os.path.exists(path):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "app"))
        from scene import Scene
        Scene()                      # writes the cache
    with open(path) as f:
        return json.load(f)


KEYED = os.path.join(ROOT, "vendor", "keyed")
OUT = os.path.join(ROOT, "vendor", "mask_base.png")
INDEX = os.path.join(ROOT, "vendor", "content_index.json")
MATRIX = os.path.join(ROOT, "vendor", "matrix.json")

SPACING_W, SPACING_H = 1016, 812
TILE_W, TILE_H = 1024, 820


def main():
    bbox = content_index()["bbox"]
    x1, y1, x2, y2 = bbox
    W, H = x2 - x1, y2 - y1

    with open(MATRIX) as f:
        matrix = json.load(f)
    pos = {}
    for r, row in enumerate(matrix["mat"]):
        for c, t in enumerate(row):
            if isinstance(t, dict) and t.get("id"):
                pos[t["id"]] = (r, c)

    mask = Image.new("L", (W, H), 0)
    files = sorted(f for f in os.listdir(KEYED) if f.endswith(".png"))
    for name in files:
        tid = name[:-4]
        if tid not in pos:
            continue
        r, c = pos[tid]
        tx, ty = c * SPACING_W - x1, r * SPACING_H - y1
        alpha = Image.open(os.path.join(KEYED, name)).getchannel("A")
        keep = alpha.point(lambda v: 255 if v > 8 else 0)
        mask.paste(255, (tx, ty, tx + TILE_W, ty + TILE_H), keep)

    mask.save(OUT)
    hist = mask.histogram()
    kept = hist[255]
    total = W * H
    print(f"wrote {OUT}  {W}x{H}")
    print(f"  keep {100 * kept / total:.1f}%   cut {100 * (1 - kept / total):.1f}%")
    print("  edit in GIMP: white = keep art, black = cut (backdrop shows)")


if __name__ == "__main__":
    main()
