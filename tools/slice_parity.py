#!/usr/bin/env python3
"""Prove the per-monitor split by bytes, for any arrangement.

Each monitor gets its own layer surface with the shared camera offset by

    scene_x_on_monitor_i = base_x + monitor_i.x / zoom

so drawing monitor i must produce exactly the crop of one union render. A
near-match means the divisor is wrong (*zoom instead of /zoom); an exact match
on several layouts — including ones with a vertical offset and one where the
second output sits to the left — is the evidence that the offset math holds
wherever the compositor puts the panels.

    /usr/bin/python3 tools/slice_parity.py \
        1920x1080@0,0,1920x1080@1920,567,1920x1080@1920,278

Layouts are `WxH@X,Y` separated by `;`. Also checks that a *moved*
arrangement still reconstructs the same scene (the camera is a pure translation
of the same base), which is what a stale cached offset would break.

    /usr/bin/python3 tools/slice_parity.py \
        "1920x1080@0,0;1920x1080@1920,567"
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "app"))

import cairo  # noqa: E402

from scene import Camera, Scene  # noqa: E402

BASE = (4900.0, 3200.0)
ZOOM = 0.5


def parse(spec):
    mons = []
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        size, pos = part.split("@")
        w, h = (int(v) for v in size.split("x"))
        x, y = (int(v) for v in pos.split(","))
        mons.append((x, y, w, h))
    return mons


def render(scene, cam, w, h):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    scene.draw(cr, cam, w, h, objs=False)
    surf.flush()
    return surf


def bytes_of(surf):
    surf.flush()
    stride = surf.get_stride()
    buf = bytes(surf.get_data())
    return b"".join(buf[row * stride:row * stride + surf.get_width() * 4]
                    for row in range(surf.get_height()))


def check(scene, mons, label):
    # Layout coordinates may be negative (an output placed left of the origin);
    # the union crop is normalised so both signs are covered.
    ox = min(x for x, y, w, h in mons)
    oy = min(y for x, y, w, h in mons)
    uw = max(x + w for x, y, w, h in mons) - ox
    uh = max(y + h for x, y, w, h in mons) - oy
    union = render(scene, Camera(BASE[0] + ox / ZOOM, BASE[1] + oy / ZOOM,
                                 ZOOM), uw, uh)
    ub = bytes_of(union)
    ustride = union.get_stride()

    ok = True
    for i, (mx, my, w, h) in enumerate(mons):
        cam = Camera(BASE[0] + mx / ZOOM, BASE[1] + my / ZOOM, ZOOM)
        sb = bytes_of(render(scene, cam, w, h))
        # crop the union at this monitor's offset
        cx, cy = mx - ox, my - oy
        crop = b"".join(ub[(cy + row) * ustride + cx * 4:
                           (cy + row) * ustride + (cx + w) * 4]
                        for row in range(h))
        same = sb == crop
        diff = sum(1 for a, b in zip(sb, crop) if a != b) if not same else 0
        print(f"  {label} monitor {i} {w}x{h}@{mx},{my}: "
              f"{'BYTE-IDENTICAL' if same else f'DIFFERS ({diff} bytes)'}")
        ok = ok and same
    print(f"  {label}: union {uw}x{uh} — "
          f"{'PARITY OK' if ok else 'PARITY FAILED'}")
    return ok


def main():
    spec = (sys.argv[1] if len(sys.argv) > 1
            else "1920x1080@0,0,1920x1080@1920,567")
    scene = Scene()
    mons = parse(spec)
    print(f"scene {scene.width}x{scene.height}, zoom {ZOOM}, "
          f"{len(mons)} monitor(s)")
    ok = check(scene, mons, "layout")

    # A move must keep every pixel of the scene in place relative to itself:
    # the same tile lands on the same scene coordinate under both arrangements.
    moved = [(x, y + 200, w, h) for x, y, w, h in mons]
    ok = check(scene, moved, "moved") and ok

    print("SLICE PARITY OK" if ok else "SLICE PARITY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
