#!/usr/bin/env python3
"""Rip the teleporter room's hologram scenes.

The hologram is NOT in the tile art. The site composites six separate scene
files over the room at a fixed map position: 805x646, 60 frames each, in
floor796's custom `.f796.br` container (brotli + RLE). The kiosk ships the
decoder, so we reuse it rather than re-deriving the format.

Output: vendor/holo/<name>.raw — 60 frames of RGBA back to back, mmap-able,
same convention as the tile animation packs.

Run with the interpreter that has `brotli` (the Hermes venv), not system python:

    python3 tools/rip_hologram.py
"""

import os
import sys

import brotli  # noqa: F401  (imported for the kiosk decoder)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIOSK = os.path.join(ROOT, "vendor", "floor796-kiosk")
sys.path.insert(0, KIOSK)

# hologram.py imports pygame at module level but the decoder path never uses it.
import types


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return type(name, (), {"__init__": lambda self, *a, **k: None})


sys.modules.setdefault("pygame", _Stub("pygame"))

from floor796_kiosk import hologram as holo  # noqa: E402

OUT = os.path.join(ROOT, "vendor", "holo")


def rip(name):
    dst = os.path.join(OUT, name.replace(".f796.br", ".raw"))
    if os.path.exists(dst) and os.path.getsize(dst) > 1024:
        return name, "exists", os.path.getsize(dst)
    url = holo.CDN_BASE + name
    raw_path = os.path.join(OUT, name)
    if not os.path.exists(raw_path):
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "floor796/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        with open(raw_path, "wb") as f:
            f.write(data)
    with open(raw_path, "rb") as f:
        packed = f.read()
    frames = holo.decode_f796_br(packed)
    with open(dst, "wb") as f:
        for fr in frames:
            f.write(fr)
    os.remove(raw_path)        # keep only the raw frames
    return name, f"{len(frames)}f", os.path.getsize(dst)


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f"{len(holo.HOLOGRAM_FILES)} hologram scenes, "
          f"{holo.SCENE_WIDTH}x{holo.SCENE_HEIGHT}")
    for name in holo.HOLOGRAM_FILES:
        try:
            n, what, size = rip(name)
            print(f"  {n}: {what} {size/1e6:.1f} MB")
        except Exception as e:
            print(f"  {name} FAILED: {e}")
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"vendor/holo: {total/1e6:.1f} MB")


if __name__ == "__main__":
    main()
