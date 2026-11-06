#!/usr/bin/env python3
"""
Standalone verifier for floor796 changelog.json `p` field decoding.

Loads matrix.json to build tile_ref -> (row, col) lookup.
Then parses EVERY object's `p` field using a PURE Python reimplementation
of highlighter.py's _parse_position_field + load_objects coordinate math.

No kiosk imports — uses only Python 3 stdlib.

Usage:
    python3 decode_p.py [changelog_path]

Defaults to ./changelog.json relative to this script (which in the repo
should be found at vendor/floor796-kiosk/changelog.json).
"""

import json
import os
import sys
import urllib.request

# ── Constants (from highlighter.py / tile_manager.py) ────────────────────────

SPACING_W = 1016   # tile horizontal stride (includes 8px right overlap)
SPACING_H = 812    # tile vertical stride   (includes 4px bottom overlap)
TILE_W    = 1024   # actual painted tile width  (= stride + 8px right overlap)
TILE_H    = 820    # actual painted tile height (= stride + 8px bottom overlap)

MATRIX_URL = "https://floor796.com/data/matrix.json"
DEFAULT_CHANGELOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "vendor", "floor796-kiosk", "changelog.json"
)


# ── Matrix loading ───────────────────────────────────────────────────────────

def fetch_json(url, timeout=15):
    """Fetch and parse JSON from URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "verify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_tile_pos(matrix):
    """Build {tile_id: (row, col)} from matrix.json mat grid.

    matrix["mat"] is an 11×10 list of lists; each entry is either None or
    a dict with key "id" (the tile reference string used in changelog.p).
    """
    pos = {}
    for row_idx, row in enumerate(matrix["mat"]):
        for col_idx, tile in enumerate(row):
            if tile and isinstance(tile, dict) and tile.get("id"):
                pos[tile["id"]] = (row_idx, col_idx)
    return pos


# ── p-field parsing (independent reimplementation) ───────────────────────────

def parse_position_field(p_str):
    """Parse 'p' field → [(tile_ref, local_x, local_y), ...].

    Grammar per segment:  <tileRef>,<Y>,<X>
    Segments separated by ';'.

    The first numeric field is Y (fits in 0..811 ≈ tile height 820).
    The second numeric field is X  (fits in 0..1015 ≈ tile width  1024).

    Returns empty list for empty/whitespace input.  Silently skips
    segments with non-integer coordinates or missing fields.
    """
    segments = []
    if not p_str or not p_str.strip():
        return segments

    for part in p_str.split(";"):
        fields = part.split(",")
        if len(fields) < 3:
            continue  # malformed segment — skip
        tile_ref = fields[0]
        try:
            y_val = int(fields[1])  # first number = Y axis
            x_val = int(fields[2])  # second number = X axis
        except ValueError:
            continue              # non-integer coordinate — skip
        segments.append((tile_ref, x_val, y_val))

    return segments


def convert_to_absolute(segments, tile_pos):
    """Convert parsed segments → [(tile_ref, abs_x, abs_y)].

    Formula (highlighter.py lines 402–403):
        abs_x = col * SPACING_W + local_x
        abs_y = row * SPACING_H + local_y

    Only keeps vertices whose tile_ref exists in the known tile grid.
    """
    result = []
    for tile_ref, lx, ly in segments:
        rc = tile_pos.get(tile_ref)
        if rc is None:
            continue  # vertex on unknown tile — drop
        row, col = rc
        ax = col * SPACING_W + lx
        ay = row * SPACING_H + ly
        result.append((tile_ref, ax, ay))
    return result


def bbox_from_verts(verts):
    """Compute bounding box from list of (tile_ref, abs_x, abs_y).

    Returns (ax_min, ay_min, ax_max, ay_max) inclusive.
    Like highlighter.py lines 420–425.
    """
    xs = [v[1] for v in verts]
    ys = [v[2] for v in verts]
    return min(xs), min(ys), max(xs), max(ys)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    changelog_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CHANGELOG

    # ── 1. Load matrix ────────────────────────────────────────────────────
    print("=" * 70)
    print("FLOOR796 P-FIELD VERIFIER")
    print("=" * 70)
    print(f"\nChangelog : {changelog_path}")

    try:
        with open(changelog_path) as f:
            objects = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: cannot read {changelog_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    # Prefer a cached local copy so the verifier works offline; fall back to
    # the live URL only when vendor/matrix.json is absent.
    local_matrix = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "vendor", "matrix.json")
    if os.path.exists(local_matrix):
        with open(local_matrix) as f:
            matrix_data = json.load(f)
        print(f"Matrix file: {local_matrix} (cached)")
    else:
        print(f"Matrix URL : {MATRIX_URL}")
        matrix_data = fetch_json(MATRIX_URL)
    tile_pos = build_tile_pos(matrix_data)
    grid_rows = len(matrix_data["mat"])
    grid_cols = len(matrix_data["mat"][0]) if grid_rows else 0
    print(f"Matrix grid: {grid_rows} rows × {grid_cols} cols ({len(tile_pos)} tiles)")
    print()

    # ── 2. Parse every object ─────────────────────────────────────────────
    total_objects = len(objects)
    parsed_ok = 0
    parsed_fail = 0
    all_abs_x, all_abs_y = [], []
    fail_details = []

    print(f"Parsing {total_objects} changelog entries …\n")

    for obj in objects:
        oid = obj.get("id", "?")
        title = obj.get("t", "")
        p_str = obj.get("p", "")

        # Step A: parse position field grammar
        segs = parse_position_field(p_str)
        if not segs:
            parsed_fail += 1
            fail_details.append({
                "id": oid, "title": title,
                "reason": "empty or no p field",
            })
            continue

        # Step B: convert to absolute coordinates
        abs_verts = convert_to_absolute(segs, tile_pos)
        if not abs_verts:
            parsed_fail += 1
            refs_in_obj = {s[0] for s in segs}
            bad_refs = refs_in_obj - set(tile_pos.keys())
            fail_details.append({
                "id": oid, "title": title,
                "reason": f"no vertices mapped — bad refs {bad_refs}" if bad_refs
                          else "all refs dropped",
            })
            continue

        # Step C: bounding box
        bx1, by1, bx2, by2 = bbox_from_verts(abs_verts)
        w = bx2 - bx1
        h = by2 - by1

        if w < 2 and h < 2:
            parsed_fail += 1
            fail_details.append({
                "id": oid, "title": title,
                "reason": "degenerate bbox (<2px)",
            })
            continue

        all_abs_x.extend(v[1] for v in abs_verts)
        all_abs_y.extend(v[2] for v in abs_verts)
        parsed_ok += 1

        # Print sample: id, title, first bbox
        n_tiles = len(set(s[0] for s in abs_verts))
        if n_tiles <= 10:  # short print for small objects
            tile_list = ", ".join(sorted(set(s[0] for s in abs_verts)))
        else:
            tile_list = f"{n_tiles} tiles"
        print(f"  id={oid:<6d}  '{title[:50]}'  "
              f"bbox=[{bx1},{by1}]-[{bx2},{by2}]  "
              f"size={w}x{h}  tiles={tile_list}")

    # ── 3. Summary ────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total changelog entries : {total_objects}")
    print(f"  Successfully parsed     : {parsed_ok}")
    print(f"  Failed / skipped        : {parsed_fail}")
    print()

    if parsed_ok > 0:
        print(f"  Absolute X range : [{min(all_abs_x)} , {max(all_abs_x)}]")
        print(f"  Absolute Y range : [{min(all_abs_y)} , {max(all_abs_y)}]")
        print(f"  Implied content  : {max(all_abs_x)-min(all_abs_x)+1}px "
              f"wide × {max(all_abs_y)-min(all_abs_y)+1}px tall")
        print()

        # Tile extent info
        used_rcs = set()
        for o in objects:
            segs = parse_position_field(o.get("p", ""))
            for tid, _, _ in segs:
                rc = tile_pos.get(tid)
                if rc:
                    used_rcs.add(rc)
        ur = [r for r, c in used_rcs]
        uc = [c for r, c in used_rcs]
        print(f"  Tiles referenced : rows [{min(ur)}, {max(ur)}]  "
              f"cols [{min(uc)}, {max(uc)}]")

        # Per-tile local-range check (sanity: local coords must fit tile)
        out_of_range = 0
        for o in objects:
            segs = parse_position_field(o.get("p", ""))
            for tid, lx, ly in segs:
                if lx < 0 or lx >= TILE_W or ly < 0 or ly >= TILE_H:
                    out_of_range += 1
        print(f"  Local coords out-of-tile-range: {out_of_range}")

    if fail_details:
        print(f"\n  FAILURES ({parsed_fail}):")
        for fd in fail_details[:20]:
            print(f"    id={fd['id']:<6d} t='{fd['title'][:50]}': {fd['reason']}")
        if parsed_fail > 20:
            print(f"    … and {parsed_fail - 20} more")

    print()
    success_pct = parsed_ok / total_objects * 100 if total_objects else 0
    if parsed_fail == 0:
        print("✓ ALL OBJECTS PARSED SUCCESSFULLY")
    else:
        print(f"✗ {parsed_fail}/{total_objects} objects failed ({100-success_pct:.1f}% ok)")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
