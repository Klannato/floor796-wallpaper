# Verification: `p`-field decode is correct

**Date:** 2026-11-06
**Status:** blocker closed — the decode is verified two independent ways.

The HANDOFF listed "Need to decode p-field format into screen coords" as the
project's main blocker. It is solved.

## The mapping

```
p segment grammar :  <tileRef>,<localY>,<localX>      (note: Y before X)
tile grid         :  matrix.json["mat"][row][col]["id"] == tileRef
absolute pixel    :  abs_x = col * 1016 + localX
                     abs_y = row *  812 + localY
```

Constants: tiles are painted 1024×820 but laid on a 1016×812 stride, so
neighbours overlap by 8 px in both axes. The stride is what the coordinate
math uses; the overlap only matters when compositing tile images.

Ground truth: `vendor/floor796-kiosk/floor796_kiosk/highlighter.py`
`_parse_position_field()` (lines 226–249) and `load_objects()` (lines 322–438,
the arithmetic is lines 402–403). The Y/X order is stated in the docstring at
line 229 and is confirmed empirically: first numeric field maxes at 811 (fits
tile height 820), second maxes at 1015 (fits tile width 1024).

## Test 1 — code parity (decisive)

`tools/parity_check.py` imports the kiosk's own `load_objects()` and diffs its
bounding boxes against our standalone reimplementation in `tools/decode_p.py`.

```
bundled changelog objects : 804
live  changelog (floor796): 857  (53 newer than bundled)
kiosk segments : 804
our bboxes     : 804
missing from us: 0  extra: 0
bbox mismatches: 0
RESULT: PARITY OK
```

804 of 804 objects produce pixel-identical boxes to the reference
implementation. Zero mismatches.

## Test 2 — pixels (validates the convention itself)

`tools/render_check.py` downloads a real tile preview from
`cdn.floor796.com/data/<preview path>` and draws the computed local boxes on
it with ffmpeg.

Spot check on tile `t3l1`:

- `id=1 "Half-life 1 - Tentacle"` → a green multi-limbed tentacle creature sits
  inside the box.
- `id=2 "Soviet cartoon - Seven-leaf flower"` → a red/pink flower sprite sits
  inside the box.

Both subjects are visibly the right thing in the right place, so the kiosk's
convention does line up with the actual artwork, not just with itself.

Caveat: a box is the hull of the **polygon vertices only**, so it can be loose
around the art (the Tentacle's stalk pokes a few px above its box) and it will
happily enclose a neighbouring sprite. That is the source convention, not a
decode bug — do not "fix" it by shrinking boxes.

## Data facts corrected

| Claim in HANDOFF | Reality |
|---|---|
| 855 objects | **804** in the kiosk's bundled `changelog.json`; **857** live from floor796.com |
| `p` is `b{block}r{row},x,y` | Four prefixes (`bl`, `br`, `tl`, `tr`), all 3-digit-free ids, and the numerics are **Y,X** |
| one grammar | 68 distinct segment-type compositions, 4,225 segments, 0 malformed |
| 855 objects with `l` | 26 objects have no usable link |

Prefer the **live** changelog: the bundled copy is 53 objects stale.

## Reproduce

```bash
python3 tools/decode_p.py                       # parse all, print summary
python3 tools/parity_check.py                   # diff vs kiosk reference code
python3 tools/render_check.py t3l1 t1r1         # draw boxes on real tile art
python3 tools/slice_parity.py "1920x1080@0,0;1920x1080@1920,567"
```

`parity_check.py` needs no pygame: the kiosk's module-level `import pygame`
is stubbed out because `load_objects()` never touches it.

## Test 3 — tile compositing

The renderer pastes tiles at `col*1016, row*812`. The 8 px overlap strips are
*not* pixel-identical between neighbouring tiles (mean luma disagreement 3–11 out
of 255 on those 8 columns). That is a hand-authoring artifact in the source art,
not a compositing bug: at 1:1 zoom the join is invisible, and paste order (later
tile wins, i.e. the painter's order a browser uses) matches both the site and the
kiosk.

**Do not "fix" the overlap** by cropping tiles to 1016×812 — that would shift
every object by up to 8 px per tile and destroy the 804/804 parity above.

## Test 4 — the multi-monitor split

Layer surfaces are per-output, so the map is drawn once per monitor with the
shared camera offset by `monitor.x / zoom` (`/zoom`, not `*zoom`). The evidence
that the divisor is right is byte equality, not a glance: render the union once,
render each monitor's slice with its offset camera, and compare bytes.

```bash
python3 tools/slice_parity.py "1920x1080@0,0;1920x1080@1920,567"
python3 tools/slice_parity.py "1920x1080@-1920,0;1920x1080@0,300"
python3 tools/slice_parity.py "2560x1440@0,-200;1080x1920@2560,240"
```

Each run also re-checks the same arrangement shifted by 200 px, because a
cached offset is exactly what breaks a move. Expected: every slice
`BYTE-IDENTICAL` and `SLICE PARITY OK`.

**Geometry is read, never cached.** GDK signals only `monitor-added` /
`monitor-removed`; dragging a panel to a new position in the compositor's
display settings sends neither, so any geometry captured when the window was
built goes stale and half the map jumps by the delta. `app/wallpaper.py`
therefore re-reads `Gdk.Monitor.get_geometry()` in every draw/input handler and
viewport size from the area allocation, and the 100 ms tick compares the
arrangement against the one it last drew — a move logs

```
layout changed: 1920x1080@1921,567 + 1920x1080@0,0 (union 3841x1647)
  Acer H236HL: 1920x1080@1920,567 → 1920x1080@1921,567
```

and repaints. No rebuild is needed: the compositor re-anchors the surfaces
itself, only the derived offsets were ever stale. Verified live by nudging an
output 1 px with `cosmic-randr position` and restoring it — both directions
logged, no `surface(s)` rebuild line in between.
