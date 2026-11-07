#!/usr/bin/env python3
"""Rip the site's addon clips into lossless frames the wallpaper can draw.

floor796's interactive effects are **addons**: `matrix.json["addons"]` lists 24
of them, each a `render.js` scoped to a region. Many of them do not draw at all
— they dispatch `add-render-slot` with a `.f796.br` clip, a screen point, an
offset and (sometimes) a clip polygon, and the site's render engine plays it
there. Those clips are ordinary files over HTTP, so they can be ripped exactly:

    /interactive/<addon>/<hash>.f796.br      the clip   (60 frames, brotli)
    /interactive/<addon>/*.png               sprites, for canvas addons
    /addon/<name>/list                       data, e.g. the 8 teleport scenes

Decoding uses the kiosk's own `decode_f796_br` (the same one
`tools/rip_hologram.py` uses), so the pixels are the site's, not a re-render.
Frames land as lossless WebP: pixel art, so any lossy codec re-creates the
smearing the whole project exists to avoid.

    python3 tools/rip_addons.py                 # everything in ADAPTERS
    python3 tools/rip_addons.py teleport-room   # one addon
    python3 tools/rip_addons.py --preview       # also write a PNG contact sheet

The manifest is `vendor/addons/manifest.json`, read by `app/addons.py`.
"""

import json
import os
import sys
import types
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "floor796-kiosk"))
sys.path.insert(0, os.path.join(ROOT, "app"))

import brotli  # noqa: F401,E402  (the kiosk decoder needs it)

# The kiosk imports pygame at module level but the decode path never touches it.
_pygame = types.ModuleType("pygame")


class _FakeSurface:
    size = (1, 1)


_pygame.Surface = _FakeSurface
_pygame.transform = types.SimpleNamespace(scale=lambda s, *a: s,
                                         smoothscale=lambda s, *a: s)
_pygame.image = types.SimpleNamespace(frombuffer=lambda *a: _FakeSurface())
sys.modules["pygame"] = _pygame

from floor796_kiosk import hologram as holo  # noqa: E402

from scene import Scene  # noqa: E402

BASE = "https://floor796.com"
OUT = os.path.join(ROOT, "vendor", "addons")

# Every value below is copied from the addon's own render.js — the point, the
# offset, the size and the duration are the site's, not estimates. `trigger`
# is `always` for scenery that animates by itself (teleport room, fog) and
# `event` for a one-shot played when its region is clicked.
ADAPTERS = {
    "teleport-room": {
        "width": 289, "height": 412, "duration": 60, "trigger": "always",
        "point": "t2r4,618,15", "offset": (-4, 1),
        "clip": ["t2r4,629,62", "t2r4,599,173", "t2r4,618,246", "t2r4,689,322",
                 "t2r4,756,334", "t2r4,793,321", "t1r5,5,300", "t1r5,149,300",
                 "t1r5,264,157", "t0r4,131,1005", "t2r4,628,19"],
        "list": "/addon/teleport-room/list",
        "dir": "/interactive/teleport-room/scenes/",
    },
    "cemetery-fog": {
        "width": 85, "height": 73, "duration": 60, "trigger": "always",
        "point": "t0r4,555,144", "offset": (-4, -4), "clip": [],
        "files": {"fog": "/interactive/cemetery-fog/1789666202.f796.br"},
    },
    "where-is-waldo": {
        "width": 89, "height": 77, "duration": 26, "trigger": "event",
        "isolate": True,
        "point": "t5l1,376,80", "offset": (13, 15), "clip": [],
        "files": {"waldo": "/interactive/where-is-waldo/1675617723.f796.br"},
    },
    "meg": {
        "width": 143, "height": 111, "duration": 47, "trigger": "event",
        "isolate": True,
        "point": "b2r2,764,295", "offset": (0, 0), "clip": [],
        "files": {"meg": "/interactive/meg/1773767566.f796.br"},
    },
    "banksy": {
        "width": 53, "height": 128, "duration": 47, "trigger": "event",
        "isolate": True,
        "point": "t2r4,423,10", "offset": (0, 0), "clip": [],
        "files": {"banksy": "/interactive/banksy/1793467437.f796.br"},
    },
}


def get(url, binary=True):
    with urllib.request.urlopen(BASE + url, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def scene_xy(scene, point):
    """'t2r4,618,15' -> scene pixel of that local point (Y before X)."""
    ref, ly, lx = point.split(",")
    r, c, _ = scene.tiles[ref]
    return c * 1016 + int(lx), r * 812 + int(ly)


def isolate(frames, w, h, thresh=8):
    """Turn a recorded rectangle into a sprite by knocking out its background.

    An event clip is a recording of its region *including* the background, so
    pasting it over the map shows a rectangular seam wherever the clip's art
    differs from the current tiles by even a shade. The static background is the
    per-pixel median across the whole clip; anything within `thresh` of it turns
    transparent, so only what actually animates survives.
    """
    import statistics
    n = len(frames)
    px = w * h
    median = bytearray(px * 4)
    for p in range(px):
        base = p * 4
        for c in range(4):
            median[base + c] = int(statistics.median(
                [frames[i][base + c] for i in range(n)]))
    out = []
    for fr in frames:
        buf = bytearray(fr)
        for p in range(px):
            base = p * 4
            if (abs(fr[base] - median[base]) <= thresh
                    and abs(fr[base + 1] - median[base + 1]) <= thresh
                    and abs(fr[base + 2] - median[base + 2]) <= thresh):
                buf[base + 3] = 0
            else:
                buf[base + 3] = 255
        out.append(bytes(buf))
    return out


def rip_clip(scene, name, key, url, spec, out_root):
    from PIL import Image
    w, h = spec["width"], spec["height"]
    raw = get(url)
    frames = holo.decode_f796_br(raw, w, h)
    if spec.get("isolate"):
        frames = isolate(frames, w, h)
    if len(frames[0]) != w * h * 4:
        raise RuntimeError(f"{name}/{key}: frame size {len(frames[0])} "
                           f"!= {w}x{h}x4")
    d = os.path.join(out_root, name, key)
    os.makedirs(d, exist_ok=True)
    for i, fr in enumerate(frames):
        Image.frombytes("RGBA", (w, h), fr).save(
            os.path.join(d, f"{i:03d}.webp"), lossless=True, quality=100)
    return {"dir": os.path.relpath(d, out_root), "frames": len(frames),
            "compressed_bytes": len(raw)}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want = args or list(ADAPTERS)
    scene = Scene()
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for name in want:
        spec = ADAPTERS.get(name)
        if spec is None:
            sys.exit(f"unknown addon {name!r} (have: {', '.join(ADAPTERS)})")
        x, y = scene_xy(scene, spec["point"])
        x += spec["offset"][0]
        y += spec["offset"][1]
        entry = {"name": name, "x": x, "y": y,
                 "width": spec["width"], "height": spec["height"],
                 "duration": spec["duration"], "trigger": spec["trigger"],
                 "clip": [scene_xy(scene, p) for p in spec["clip"]],
                 "clips": {}}
        print(f"{name}: point -> scene ({x},{y})  {spec['width']}x"
              f"{spec['height']}  {spec['duration']}f")

        if "list" in spec:
            # the teleport room keeps its scenes in a JSON list; the file name
            # is the clip, resolved against the addon's scenes directory
            listing = json.loads(get(spec["list"]))
            for i, item in enumerate(listing):
                info = rip_clip(scene, name, str(i), spec["dir"] + item["file"],
                                spec, OUT)
                info["title"] = item.get("titleEn", "")
                info["still"] = item.get("src", "")
                entry["clips"][str(i)] = info
                print(f"   {i}: {info['title'][:34]:36s} "
                      f"{info['frames']}f  {info['compressed_bytes']:>8d}B")
        else:
            for key, url in spec["files"].items():
                info = rip_clip(scene, name, key, url, spec, OUT)
                entry["clips"][key] = info
                print(f"   {key}: {info['frames']}f  "
                      f"{info['compressed_bytes']:>8d}B compressed")
        manifest.append(entry)

    path = os.path.join(OUT, "manifest.json")
    old = {}
    if os.path.exists(path):
        old = {e["name"]: e for e in json.load(open(path))}
    old.update({e["name"]: e for e in manifest})
    with open(path, "w") as f:
        json.dump(sorted(old.values(), key=lambda e: e["name"]), f, indent=1)
    print(f"\nmanifest: {path} ({len(old)} addon(s))")


if __name__ == "__main__":
    main()
