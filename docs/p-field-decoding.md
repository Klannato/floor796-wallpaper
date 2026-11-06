# Decode floor796 `p` Field → Absolute Scene Pixel Coordinates

**Generated:** 2026-11-06  
**Source reference:** `/home/geo/code/floor796-wallpaper/vendor/floor796-kiosk/` (cloned from https://github.com/arionl/floor796-kiosk)

---

## 1. Grammar of the `p` field

### Format string
```
<tileRef>,<Y>,<X>[;<tileRef>,<Y>,<X>][;…]
```

| Component | Description | Example |
|-----------|-------------|---------|
| `<tileRef>` | Tile identifier matching an `"id"` value in `matrix.json`. Two families: `b<grp><pos>` (blue interior tiles) and `t<num><pos>` (tan perimeter tiles). | `b1r5`, `t4r2` |
| `<Y>` | **Y axis**, integer 0 .. ≤811 (must fit within painted tile height 820). This is the *first* numeric field. | `244` |
| `<X>` | **X axis**, integer 0 .. ≤1015 (must fit within painted tile width 1024). This is the *second* numeric field. | `35` |
| `;` | Semicolon separates multiple vertex segments belonging to the same polygon/object. | — |

### Key notes

- **Y comes before X** in every segment. Confirmed by two independent checks:
  1. Highlighter.py docstring (line 229): *"NOTE: The floor796.com data format is tileRef,Y,X"*
  2. Range analysis: first number max ≈ 811 fits tile height 820; second number max ≈ 1015 fits tile width 1024. Swapping would fail.
- Multiple `;`-delimited segments are parsed independently. Each segment becomes one point `(tile_ref, x, y)` in the polygon vertex list.
- An object spanning multiple tiles produces segments with different tileRefs, forming a multi-tile polygon.

### Concrete example

`p = "b1r5,244,35;b2r4,158,913;b2r4,66,1011;b1r5,165,107"`

Parsed into 4 points:
1. `(b1r5, 244, 35)`  — X=244, Y=35 on tile b1r5
2. `(b2r4, 158, 913)` — X=158, Y=913 on tile b2r4
3. `(b2r4, 66, 1011)` — X=66,  Y=1011 on tile b2r4
4. `(b1r5, 165, 107)` — X=165, Y=107 on tile b1r5

---

## 2. Tile grid geometry

### Matrix layout

| Property | Value | Source |
|----------|-------|--------|
| Grid rows | 11 | `matrix.json["mat"]` — 11 inner arrays |
| Grid cols | 10 | `matrix.json["mat"][0]` — 10 entries per row |
| Total tiles | 110 | |
| Painted size per tile | 1024 × 820 px | `tile_manager.py` line 368: `"tile_size": [1024, 820]` |
| Stride per tile | 1016 × 812 px | `highlighter.py` lines 322–323 default args |
| Overlap | 8 px horizontal, 8 px vertical | Computed as (painted − stride) = (1024−1016, 820−812) = (8, 8) |

The 8px overlap means adjacent tiles share a narrow strip: each tile paints its rightmost 8px and bottommost 8px overlapping onto the neighbour. In the kiosk's coordinate space each tile occupies exactly `stride` pixels; the painter only cares about painted extents.

### Tile naming convention (nomenclature only — not used programmatically)

Tiles start either `t` (tan/border) or `b` (blue/interior). A suffix letter (`l` or `r`) and a number indicate author-specified grouping. **Importantly: the code never parses the name.** The authoritative mapping is purely `tiles_meta.json["tiles"][tileId]["row"]` / `["col"]` (generated from `matrix.json`).

### Grid positions (tile_id → row,col in matrix.json)

Relevant tiles (those referenced by any changelog entry):

| Tile | Row | Col | Tile | Row | Col |
|------|-----|-----|------|-----|-----|
| `b1l1` | 6 | 3 | `t0l2` | 5 | 3 |
| `b1l3` | 5 | 2 | `t0l4` | 4 | 2 |
| `b1r1` | 7 | 4 | `t0r0` | 6 | 4 |
| `b1r3` | 8 | 5 | `t0r2` | 7 | 5 |
| `b1r5` | 9 | 6 | `t0r4` | 8 | 6 |
| `b2l2` | 6 | 2 | `t1l1` | 5 | 4 |
| `b2l4` | 5 | 1 | `t1l3` | 4 | 3 |
| `b2r0` | 7 | 3 | `t1r1` | 6 | 5 |
| `b2r2` | 8 | 4 | `t1r3` | 7 | 6 |
| `b2r4` | 9 | 5 | `t2l2` | 4 | 4 |
| `b3l1` | 7 | 2 | `t2l4` | 3 | 3 |
| `b3l3` | 6 | 1 | `t2l6` | 2 | 2 |
| `b3r1` | 8 | 3 | `t2r0` | 5 | 5 |
| `b3r3` | 9 | 4 | `t2r2` | 6 | 6 |
| `b3r5` | 10 | 5 | `t2r4` | 7 | 7 |
| `t0r4` | 8 | 6 | `t3l1` | 4 | 5 |
| `t0l2` | 5 | 3 | `t3l3` | 3 | 4 |
| *(and 20 more — full map available via matrix.json)* | | | `t3l5` | 2 | 3 |

All 48 tile refs referenced in changelog exist in the matrix. No unknown refs found.

---

## 3. Mapping formula

### Pseudocode

```
# Given changelog entry with p-field string:
segments = []
for part in p_str.split(";"):
    fields = part.split(",")
    tileRef = fields[0]           # e.g. "b1r5"
    local_y = int(fields[1])      # FIRST numeric field = Y axis
    local_x = int(fields[2])      # SECOND numeric field = X axis
    segments.append((tileRef, local_x, local_y))

# Convert to absolute scene coordinates:
abs_points = []
for (tileRef, lx, ly) in segments:
    (row, col) = tile_pos[tileRef]   # lookup from matrix.json
    abs_x = col * 1016 + lx
    abs_y = row *  812 + ly
    abs_points.append((tileRef, abs_x, abs_y))

# Bounding box for rendering / hit-testing:
ax_min = min(v.abs_x for v in abs_points)
ay_min = min(v.abs_y for v in abs_points)
ax_max = max(v.abs_x for v in abs_points)
ay_max = max(v.abs_y for v in abs_points)
```

### Exact constants

| Constant | Value | Source |
|----------|-------|--------|
| `SPACING_W` (stride) | **1016** | `highlighter.py` line 322, `load_objects()` default |
| `SPACING_H` (stride) | **812** | same |
| `TILE_WIDTH` | **1024** | `tile_manager.py` line 368, `tile_size[0]` |
| `TILE_HEIGHT` | **820** | same, `tile_size[1]` |

### Where the 8px overlap matters

The overlap is already accounted for in the stride choice:
- Tile painted at 1024 × 820, but placed on a grid with spacing 1016 × 812.
- The formula `col * 1016 + lx` implicitly handles the overlap because the painter knows each tile covers `[col*1016 .. col*1016+1024]` with neighbours filling the gap at `col*1016+1016 .. col*1016+1024` (= next tile's left edge).
- There is **no explicit "subtract 4" or "add half-overlap" correction**. The overlap is baked into the tile painting itself, not the coordinate system.

### Multi-tile objects

An object on N tiles produces N groups of vertices (or more, if each tile contributes a dense polygon). All vertices from all tiles are collected into a single bounding box in the current highlighter version (see §5 Caveats).

---

## 4. Scene extent (from real data)

From parsing all 804 changelog entries:

| Metric | Value |
|--------|-------|
| Min absolute X | **1572** (tile b3l3, row 6, col 1, local_x=556) |
| Max absolute X | **8522** (tile t4r4, row 6, col 8, local_x=394) |
| Min absolute Y | **1719** (tile t3l5, row 2, col 3, local_y=95) |
| Max absolute Y | **8160** (tile b3r5, row 10, col 5, local_y=40) |
| Content bounding box | **[1572, 1719, 8522, 8160]** → **6951 px wide × 6442 px tall** |
| Tiles used (rows) | 2 – 10 (9 rows out of 11) |
| Tiles used (cols) | 1 – 8 (8 columns out of 10) |

### Implied full scene dimensions

If you render ALL 110 tiles contiguously:

| Dimension | Calculation | Extent |
|-----------|-------------|--------|
| Width | row 0 tiles col 0..9 × 1016 + tile_width | 9 × 1016 + 1024 = **10,168 px** |
| Height | row 0 × 812 + tile_height | 10 × 812 + 820 = **8,940 px** |

But the changelog objects only occupy the subset of tiles in rows 2–10 and cols 1–8. Tiles in rows 0–1, col 0, and col 9 appear to be decorative borders with no interactive highlights.

---

## 5. Kiosk code behaviour (surprising details)

### What surprised the decoder

1. **No per-object zoom anchors.** The `ObjectHighlighter` class does not compute or store per-object zoom/pan targets. Zoom-to-fit would require the consumer to derive it from `seg.cx, seg.cy, seg.width, seg.height` (lines 220–223 of ObjectSegment).

2. **Single bbox for multi-tile objects.** While `load_objects()` initially had multi-segment support (`_trace_polygon_per_tile`), the current version collapses all vertices into one bbox per object (lines 414–434). Comment says fragments were removed because large objects like Pocahontas showed only a fragment previously.

3. **Bounding box values are inclusive (not exclusive-end).** The kiosk uses `max(xs)` directly as the right/bottom edge. For rendering purposes, treat these as the pixel of the rightmost/bottommost sample point. To get exclusive-end, add 1.

4. **No y-flip or coordinate-system inversion.** The scene uses standard Cartesian coords (origin top-left, y increases downward).

5. **Tile-ref naming is cosmetic.** The code uses `tiles_meta.json["tiles"][tileId]` for the actual row/col lookup. Nothing in the codebase derives geometry from parsing the tileRef string itself.

### Verification against handoff-note assumptions

- ✅ 1024×820 painted, 1016×812 stride (8px overlap confirmed).
- ✅ Formula `abs = (col * 1016, row * 812) + (local_x, local_y)` matches exactly.
- ⚠️ Handoff note might have assumed `p` was `tileRef,X,Y` — it is actually `tileRef,Y,X`. The swap is documented in highlighter.py line 244–245.

---

## 6. Verifier results

File: `tools/decode_p.py`

| Metric | Result |
|--------|--------|
| Total changelog entries | **804** |
| Successfully parsed | **804** |
| Failed | **0** |
| Parse success rate | **100%** |
| Local coords out-of-tile-range | **0 violations** |
| Unknown tile refs | **0** |

---

## 7. Files produced

| Path | Description |
|------|-------------|
| `/home/geo/code/floor796-wallpaper/tools/decode_p.py` | Standalone verifier (Python 3 stdlib only, no kiosk imports) |
| `/home/geo/code/floor796-wallpaper/docs/p-field-decoding.md` | This document |

---

## 8. Unresolved ambiguity

**None identified.** Every changelog entry in the current dataset (804 objects) parses cleanly with the discovered formula. All tile references resolve to matrix grid positions. No coordinate is outside tile bounds. The grammar, coordinate order, and conversion math are fully explained by highlighter.py source code.
