#!/usr/bin/env python3
"""Fetch the kiosk repo that carries the `.f796.br` decoder.

Several tools (rip_hologram, rip_addons, bake_fog) decode floor796's own scene
container with `floor796_kiosk.hologram.decode_f796_br` — the reference
implementation, cloned into `vendor/floor796-kiosk`. It is not vendored in this
repo (it is someone else's GPL code), so a fresh clone has to fetch it once.

Calling `ensure()` is idempotent and prints what it is doing, so a first run on a
new machine just works instead of failing with `No module named floor796_kiosk`.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIOSK = os.path.join(ROOT, "vendor", "floor796-kiosk")
URL = "https://github.com/arionl/floor796-kiosk"


def ensure():
    """Return the kiosk path, cloning it on first use."""
    if os.path.isdir(os.path.join(KIOSK, "floor796_kiosk")):
        return KIOSK
    os.makedirs(os.path.dirname(KIOSK), exist_ok=True)
    print(f"fetching kiosk decoder -> {KIOSK}", flush=True)
    subprocess.run(["git", "clone", "-q", "--depth", "1", URL, KIOSK],
                   check=True)
    return KIOSK


if __name__ == "__main__":
    p = ensure()
    sys.path.insert(0, p)
    import brotli  # noqa: F401
    from floor796_kiosk import hologram  # noqa: F401
    print(f"ok: decoder available at {p}")
