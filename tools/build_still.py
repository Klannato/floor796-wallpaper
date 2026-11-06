#!/usr/bin/env python3
"""Composite all tile previews into one whole-scene still, then draw boxes.

Proves the tile composition math (1024x820 art on a 1016x812 stride) before any
Wayland/video work. Needs Pillow.

    python3 tools/build_still.py [--boxes] [--crop x,y,w,h out.png]
"""

import argparse
import io
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STILL_DIR = os.path.join(ROOT, "vendor", "tiles")
SPACING_W, SPACING_H = 1016, 812
CDN_BASE = "https://cdn.floor796.com/data/"


def load(name):
    with open(os.path.join(ROOT, "vendor", name)) as f:
        return json.load(f)


def tiles(matrix):
    """[(tile_id, row, col, preview_path)]"""
    out = []
    for r, row in enumerate(matrix["mat"]):
        for c, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("preview"):
                out.append((tile["id"], r, c, tile["preview"]))
    return out


def fetch(item):
    tid, r, c, rel = item
    os.makedirs(STILL_DIR, exist_ok=True)
    dest = os.path.join(STILL_DIR, f"{tid}.webp")
    if not os.path.exists(dest) or os.path.getsize(dest) < 1024:
        req = urllib.request.Request(CDN_BASE + rel,
                                     headers={"User-Agent": "floor796-still/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
    return tid, r, c, dest


def build(matrix):
    items = tiles(matrix)
    with ThreadPoolExecutor(max_workers=8) as ex:
        got = list(ex.map(fetch, items))
    width = max(c for _, _, c, _ in got) * SPACING_W + 1024
    height = max(r for _, r, _, _ in got) * SPACING_H + 820
    scene = Image.new("RGB", (width, height), (0, 0, 0))
    for tid, r, c, path in got:
        with Image.open(path) as im:
            scene.paste(im.convert("RGB"), (c * SPACING_W, r * SPACING_H))
    return scene, got


def boxes(objects, pos):
    out = []
    for o in objects:
        verts = []
        for part in (o.get("p") or "").split(";"):
            f = part.split(",")
            if len(f) < 3:
                continue
            try:
                y, x = int(f[1]), int(f[2])
            except ValueError:
                continue
            rc = pos.get(f[0])
            if rc:
                verts.append((rc[1] * SPACING_W + x, rc[0] * SPACING_H + y))
        if not verts:
            continue
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        out.append((min(xs), min(ys), max(xs), max(ys), o.get("t", "")))
    return out


def tile_pos(matrix):
    return {t["id"]: (r, c)
            for r, row in enumerate(matrix["mat"])
            for c, t in enumerate(row)
            if isinstance(t, dict)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "verify", "still.png"))
    args = ap.parse_args()

    matrix = load("matrix.json")
    scene, got = build(matrix)
    print(f"composited {len(got)} tiles -> {scene.width}x{scene.height}")

    if args.boxes:
        pos = tile_pos(matrix)
        bs = boxes(load("changelog.json"), pos)
        draw = ImageDraw.Draw(scene, "RGBA")
        for x1, y1, x2, y2, _ in bs:
            draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 255), width=3)
        print(f"drew {len(bs)} boxes")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    scene.save(args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    sys.exit(main())
