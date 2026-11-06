#!/usr/bin/env python3
"""Parity check: our standalone decoder vs the kiosk's own ObjectHighlighter.

Ground truth = vendor/floor796-kiosk/floor796_kiosk/highlighter.py:load_objects().
If every bbox matches to the pixel, our reimplementation is faithful.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import types
# highlighter.py imports pygame at module level but load_objects() never uses
# it; stub it so we can import the parsing logic without installing pygame.
class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return type(name, (), {"__init__": lambda self, *a, **k: None})
sys.modules.setdefault("pygame", _Stub("pygame"))
sys.path.insert(0, os.path.join(ROOT, "vendor", "floor796-kiosk"))
from floor796_kiosk.highlighter import load_objects  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools"))
import decode_p as dp  # noqa: E402

matrix = json.load(open(os.path.join(ROOT, "vendor", "matrix.json")))
tiles = {}
for r, row in enumerate(matrix["mat"]):
    for c, t in enumerate(row):
        if isinstance(t, dict) and t.get("id"):
            tiles[t["id"]] = {"row": r, "col": c}
tiles_meta = {"tiles": tiles, "grid_rows": len(matrix["mat"]),
              "grid_cols": len(matrix["mat"][0])}

CHANGELOG = os.path.join(ROOT, "vendor", "changelog.json")
ref = {s.obj_id: (s.abs_x1, s.abs_y1, s.abs_x2, s.abs_y2)
       for s in load_objects(tiles_meta, cache_path=CHANGELOG)}
live = {s.obj_id for s in load_objects(tiles_meta)}
print(f"bundled changelog objects : {len(set(o['id'] for o in json.load(open(CHANGELOG))))}")
print(f"live  changelog (floor796): {len(live)}  ({len(live - set(ref))} newer than bundled)")

objs = json.load(open(CHANGELOG))
pos = dp.build_tile_pos(matrix)
mine = {}
skipped = []
for o in objs:
    verts = dp.convert_to_absolute(dp.parse_position_field(o.get("p", "")), pos)
    if not verts:
        skipped.append((o["id"], "no verts")); continue
    bx1, by1, bx2, by2 = dp.bbox_from_verts(verts)
    if (bx2 - bx1) < 2 and (by2 - by1) < 2:
        skipped.append((o["id"], "degenerate")); continue
    mine[o["id"]] = (bx1, by1, bx2, by2)

missing = set(ref) - set(mine)
extra = set(mine) - set(ref)
diff = [(i, ref[i], mine[i]) for i in sorted(set(ref) & set(mine)) if ref[i] != mine[i]]

print(f"kiosk segments : {len(ref)}")
print(f"our bboxes     : {len(mine)}")
print(f"missing from us: {len(missing)}  extra: {len(extra)}")
print(f"bbox mismatches: {len(diff)}")
for i, a, b in diff[:10]:
    print(f"  id={i}  kiosk={a}  ours={b}")
print(f"degenerate skipped: {len(skipped)}")
print("RESULT:", "PARITY OK" if not (missing or extra or diff) else "MISMATCH")
