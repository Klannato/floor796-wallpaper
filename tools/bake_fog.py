#!/usr/bin/env python3
"""Bake the cemetery fog the way the site's addon actually draws it.

`cemetery-fog/render.js` never draws its `.f796.br` clip directly. The clip is an
85x73 fog *sprite*; the renderer tiles it — 6 diagonal lines of 5 sprites each,
~22/16 px apart, each line bobbing on a sine of `FOG_RADIUS` and offset 15
frames in phase — into a work canvas the size of `mask.webp`, then knocks the
result out with that plume mask (`destination-in`) and draws it at
`MASK_OFFSET_X/Y` with `fogOpacity`.

Drawing the clip as-is therefore puts a hard opaque rectangle over the FOG sign,
which is exactly what "missing particle effects" looked like. This composites
the same 60 frames offline into `vendor/addons/cemetery-fog/plume/`, so the
wallpaper just blits a soft plume.

    python3 tools/bake_fog.py            # writes the plume frames + manifest patch
"""

import json
import os
import sys
import types
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "floor796-kiosk"))
sys.path.insert(0, os.path.join(ROOT, "app"))

import brotli  # noqa: F401,E402
from PIL import Image, ImageChops  # noqa: E402

_pygame = types.ModuleType("pygame")


class _S:
    size = (1, 1)


_pygame.Surface = _S
_pygame.transform = types.SimpleNamespace(scale=lambda s, *a: s,
                                         smoothscale=lambda s, *a: s)
_pygame.image = types.SimpleNamespace(frombuffer=lambda *a: _S())
sys.modules["pygame"] = _pygame

from floor796_kiosk import hologram as holo  # noqa: E402

BASE = "https://floor796.com"
CLIP = "/interactive/cemetery-fog/1789666202.f796.br"
MASK = "/interactive/cemetery-fog/mask.webp"
FPS = 12

# Every number below is from cemetery-fog/render.js — not tuned by eye.
MASK_OFFSET_X, MASK_OFFSET_Y = 84, 45
LINES = 6
SPRITES_PER_LINE = 5
PADDING = 20
RADIUS = 8
LINE_PHASE = 15          # i * 15 in the addon
START_X, START_Y = 620, 70
DURATION = 60


def main():
    import math
    out = os.path.join(ROOT, "vendor", "addons", "cemetery-fog", "plume")
    os.makedirs(out, exist_ok=True)

    raw = urllib.request.urlopen(BASE + CLIP, timeout=60).read()
    with urllib.request.urlopen(BASE + MASK, timeout=60) as r:
        mask_path = os.path.join(ROOT, "vendor", "addons", "cemetery-fog",
                                 "mask.webp")
        open(mask_path, "wb").write(r.read())

    mask = Image.open(mask_path).convert("RGBA")
    mask_alpha = mask.split()[3]
    mw, mh = mask.size

    frames = None
    w = h = 0
    # locate the ripped clip: 85x73 was decoded with the addon's width/height
    d = os.path.join(ROOT, "vendor", "addons", "cemetery-fog", "fog")
    if os.path.isdir(d) and os.listdir(d):
        first = Image.open(os.path.join(d, "000.webp"))
        w, h = first.size
        frames = [Image.open(os.path.join(d, f"{i:03d}.webp")).convert("RGBA")
                  for i in range(DURATION)]
    else:
        fr = holo.decode_f796_br(raw, 85, 73)
        w, h = 85, 73
        frames = [Image.frombytes("RGBA", (w, h), b) for b in fr]

    fog_w = (w >> 1) - PADDING
    fog_h = (h >> 1) - PADDING
    print(f"sprite {w}x{h}, step {fog_w}x{fog_h}, canvas {mw}x{mh}")

    for f in range(DURATION):
        canvas = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
        for line in range(LINES):
            seq = (f + line * LINE_PHASE) % DURATION
            angle = seq / DURATION * math.pi * 2
            x = START_X + math.sin(angle) * RADIUS
            y = START_Y + line * fog_h - math.cos(angle) * RADIUS
            for _ in range(SPRITES_PER_LINE):
                canvas.alpha_composite(frames[seq], (int(math.ceil(x)),
                                                     int(math.ceil(y))))
                x += fog_w
                y += fog_h
        alpha = ImageChops.multiply(canvas.split()[3], mask_alpha)
        canvas.putalpha(alpha)
        canvas.save(os.path.join(out, f"{f:03d}.webp"), lossless=True, quality=100)

    # point the manifest at the plume instead of the raw clip
    mpath = os.path.join(ROOT, "vendor", "addons", "manifest.json")
    man = json.load(open(mpath))
    for entry in man:
        if entry["name"] != "cemetery-fog":
            continue
        entry["x"] += MASK_OFFSET_X
        entry["y"] += MASK_OFFSET_Y
        entry["width"], entry["height"] = mw, mh
        entry["clips"] = {"plume": {
            "dir": os.path.relpath(out, os.path.join(ROOT, "vendor", "addons")),
            "frames": DURATION, "title": "cemetery fog"}}
    json.dump(man, open(mpath, "w"), indent=1)
    print(f"baked {DURATION} plume frames -> {out}")
    print(f"manifest: cemetery-fog now {mw}x{mh} at "
          f"{[e for e in man if e['name']=='cemetery-fog'][0]['x']},"
          f"{[e for e in man if e['name']=='cemetery-fog'][0]['y']}")


if __name__ == "__main__":
    main()
