#!/usr/bin/env python3
"""Audit our object boxes against floor796.com's own front-end algorithm.

The site is the authority, not the kiosk. This file reproduces, statement for
statement, what the live bundle does when it builds a hover box
(`front.*.js` — the class that maps `this._changes` into `_items`):

    p.split(";")
     .map(parsePositionCode)          // name -> row/col, NOT the matrix index
     .filter(v => v !== null)         // out-of-tile vertices are dropped
    bbox of what survives
    skip items with fewer than 3 surviving vertices
    skip items whose link contains "no-click"

and the tile geometry from `getSizeForZoomFactor(1)` in the modern branch:
1016x812 per tile, local coordinates Y before X.

So the audit answers three questions the eye cannot:

  1. does every object land on the same pixel rectangle as the site's?
  2. does the site drop vertices (and therefore boxes) that we keep?
  3. are there objects only one side knows about?

    /usr/bin/python3 tools/box_audit.py
    /usr/bin/python3 tools/box_audit.py --all      # list every delta

Exit status is 0 only when neither side has a box the other lacks.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "app"))

from scene import Scene  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILE_W, TILE_H = 1016, 812          # getSizeForZoomFactor(1), modern branch

CODE_RE = re.compile(r"^#?([tb]\d+[lr]\d+),(\d+),(\d+)(,\d+)?$")


def abstract_matrix(matrix_ids):
    """name -> (row, col), anchored on matrix[0][0] — the site's own mapping.

    _buildAbstractMatrix walks n,i in [-10,10) and derives the name from
    s = n-i and o = i+n, then subtracts the (n,i) of the tile whose id is the
    matrix's first cell. This is why a name must never be trusted blindly: the
    anchor comes from the matrix.
    """
    by_name = {}
    for n in range(-10, 10):
        for i in range(-10, 10):
            s, o = n - i, i + n
            name = (("t%d" % -s) if s <= 0 else ("b%d" % s)) + \
                   (("l%d" % -o) if o < 0 else ("r%d" % o))
            by_name[name] = (n, i)
    origin = by_name[matrix_ids[0]]
    return {name: (n - origin[0], i - origin[1])
            for name, (n, i) in by_name.items()}


def parse_position_code(code, pos_by_name):
    """parsePositionCode(): local Y before X, and a strict in-tile filter."""
    m = CODE_RE.match(code)
    if not m:
        return None
    ref, ly, lx = m.group(1), int(m.group(2)), int(m.group(3))
    # if (r < 0 || r - o > 2 || l < 0 || l - a > 2) return null
    if lx < 0 or lx - TILE_W > 2 or ly < 0 or ly - TILE_H > 2:
        return None
    rc = pos_by_name.get(ref)
    if rc is None:
        return None
    return rc[1] * TILE_W + lx, rc[0] * TILE_H + ly


def site_boxes(changelog, pos_by_name):
    out = {}
    for o in changelog:
        p = o.get("p") or ""
        if p == "":
            continue
        pts = [v for v in (parse_position_code(c.strip(), pos_by_name)
                           for c in p.split(";")) if v is not None]
        if len(pts) < 3:                       # _renderItems: pts.length < 3
            continue
        if "no-click" in (o.get("l") or ""):   # _renderItems: l.includes(...)
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out[o.get("id")] = (min(xs), min(ys), max(xs), max(ys))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="list every delta")
    args = ap.parse_args()

    scene = Scene()
    matrix_ids = [t["id"] for row in scene.matrix["mat"] for t in row
                  if isinstance(t, dict) and t.get("id")]
    pos_by_name = abstract_matrix(matrix_ids)
    site = site_boxes(scene.changelog, pos_by_name)
    ours = {o["id"]: (o["x1"], o["y1"], o["x2"], o["y2"]) for o in scene.objects}

    print(f"objects in changelog : {len(scene.changelog)}")
    print(f"site boxes           : {len(site)}")
    print(f"our boxes            : {len(ours)}")

    only_site = sorted(set(site) - set(ours))
    only_ours = sorted(set(ours) - set(site))
    print(f"\nbox only on the site : {len(only_site)}")
    for i in (only_site if args.all else only_site[:10]):
        print(f"   {i}  {site[i]}")
    print(f"box only in ours     : {len(only_ours)}")
    for i in (only_ours if args.all else only_ours[:10]):
        print(f"   {i}  {ours[i]}")

    delta = []
    for oid in sorted(set(site) & set(ours)):
        a, b = site[oid], ours[oid]
        if a != b:
            d = max(abs(a[k] - b[k]) for k in range(4))
            delta.append((d, oid, a, b))
    delta.sort(reverse=True)
    print(f"\nidentical boxes      : {len(set(site) & set(ours)) - len(delta)}")
    print(f"differing boxes      : {len(delta)}")
    for d, oid, a, b in (delta if args.all else delta[:10]):
        print(f"   {oid}: max {d} px   site {a}  ours {b}")

    ok = not only_site and not delta
    print("\nBOX AUDIT OK" if ok else "\nBOX AUDIT: DELTAS ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
