#!/usr/bin/env python3
"""Fetch the two metadata files everything else depends on.

    vendor/matrix.json     tile grid: which tile sits at which (row, col)
    vendor/changelog.json  the 800+ interactive objects and their links

Both come from floor796.com. The kiosk repo also bundles a copy of
changelog.json, but it is usually 50+ objects stale, so we always take the live
one.

    python3 tools/fetch_meta.py
"""

import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = {
    "matrix.json": "https://floor796.com/data/matrix.json",
    "changelog.json": "https://floor796.com/data/changelog.json",
}


def main():
    out = os.path.join(ROOT, "vendor")
    os.makedirs(out, exist_ok=True)
    for name, url in SOURCES.items():
        req = urllib.request.Request(url, headers={"User-Agent": "floor796/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except Exception as e:
            sys.exit(f"failed to fetch {url}: {e}")
        payload = json.loads(data)          # fail loudly on a bad response
        with open(os.path.join(out, name), "wb") as f:
            f.write(data)
        if name == "matrix.json":
            n = sum(1 for row in payload["mat"] for t in row if isinstance(t, dict))
            print(f"  matrix.json    {n} tiles")
        else:
            print(f"  changelog.json {len(payload)} objects")


if __name__ == "__main__":
    main()
