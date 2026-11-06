#!/usr/bin/env python3
"""Render-check: draw decoded object boxes onto a real floor796 tile image.

This is the pixel-level counterpart to decode_p.py. decode_p.py proves the
arithmetic is self-consistent; this script proves the arithmetic lands on the
right pixels, by fetching the actual tile preview from the CDN and drawing the
computed local bounding boxes over it.

Usage:
    python3 tools/render_check.py t3l1 [more tile ids ...] [--outdir DIR]

Requires ffmpeg on PATH (used for drawbox). Stdlib only otherwise.
"""

import json
import os
import subprocess
import sys

SPACING_W, SPACING_H = 1016, 812
CDN_BASE = "https://cdn.floor796.com/data/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX = os.path.join(ROOT, "vendor", "matrix.json")
CHANGELOG = os.path.join(ROOT, "vendor", "changelog.json")

COLORS = ["red", "lime", "yellow", "cyan", "magenta", "orange", "white"]


def load(mapping_path):
    with open(mapping_path) as f:
        return json.load(f)


def tile_positions(matrix):
    """{tile_id: (row, col)} from matrix.json's mat grid."""
    pos = {}
    for r, row in enumerate(matrix["mat"]):
        for c, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("id"):
                pos[tile["id"]] = (r, c)
    return pos


def tile_entry(matrix, tid):
    for row in matrix["mat"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("id") == tid:
                return tile
    return None


def parse_p(p_str):
    """'tileRef,Y,X;...' -> [(tile_ref, local_x, local_y)] (Y first)."""
    out = []
    for part in (p_str or "").split(";"):
        f = part.split(",")
        if len(f) >= 3:
            try:
                out.append((f[0], int(f[2]), int(f[1])))
            except ValueError:
                pass
    return out


def boxes_on_tile(objects, tid):
    """Local bboxes of every object with at least one vertex on `tid`."""
    boxes = []
    for o in objects:
        verts = parse_p(o.get("p", ""))
        local = [(x, y) for ref, x, y in verts if ref == tid]
        if not local:
            continue
        xs = [p[0] for p in local]
        ys = [p[1] for p in local]
        boxes.append((o.get("id"), o.get("t", ""),
                      min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return boxes


def main():
    args = [a for a in sys.argv[1:]]
    outdir = os.path.join(ROOT, "verify")
    if "--outdir" in args:
        i = args.index("--outdir")
        outdir = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit("usage: render_check.py <tile_id> [tile_id ...] [--outdir DIR]")

    matrix = load(MATRIX)
    objects = load(CHANGELOG)
    os.makedirs(outdir, exist_ok=True)

    for tid in args:
        entry = tile_entry(matrix, tid)
        if not entry or not entry.get("preview"):
            print(f"[skip] {tid}: no preview in matrix.json")
            continue
        url = CDN_BASE + entry["preview"]
        src = os.path.join(outdir, f"{tid}.webp")
        if not os.path.exists(src):
            subprocess.run(["curl", "-fsSL", url, "-o", src], check=True)

        boxes = boxes_on_tile(objects, tid)
        if not boxes:
            print(f"[skip] {tid}: no objects reference this tile")
            continue

        filters = [
            f"drawbox=x={x}:y={y}:w={max(w,2)}:h={max(h,2)}:"
            f"color={COLORS[i % len(COLORS)]}@1.0:t=4"
            for i, (_, _, x, y, w, h) in enumerate(boxes)
        ]
        dst = os.path.join(outdir, f"{tid}_boxes.png")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", src,
             "-vf", ",".join(filters), "-frames:v", "1", dst],
            check=True)

        print(f"{tid}: {len(boxes)} box(es) -> {dst}")
        for i, (oid, title, x, y, w, h) in enumerate(boxes):
            print(f"   {COLORS[i % len(COLORS)]:<8} id={oid:<5} "
                  f"x={x} y={y} w={w} h={h}  {title[:60]}")


if __name__ == "__main__":
    main()
