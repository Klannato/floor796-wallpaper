#!/usr/bin/env python3
"""Resolve the non-http link schemes in changelog.json.

floor796 mixes ordinary URLs with its own schemes, and treating them all as
"open in browser" silently breaks them:

    img://data/misc/x.png        an image the site shows in its own overlay
    interactive://pages/foo      an HTML page on floor796.com
    event://pick-hologram-N      select hologram scene N (a pad in the room)
    event://pick-teleport-N      teleport pad gating (kiosk only)
    event://chuck-norris         a site-side easter-egg animation — nothing we
                                 can drive from the wallpaper
"""

import subprocess

BASE = "https://floor796.com/"


def _open(url):
    subprocess.Popen(["xdg-open", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"opened {url}", flush=True)


def hologram_pad_index(link):
    """Scene number for an `event://pick-hologram-N` pad, else None."""
    link = (link or "")
    if not link.startswith("event://pick-hologram-"):
        return None
    num = link[len("event://pick-hologram-"):].split("||")[0].strip()
    try:
        return int(num)
    except ValueError:
        return None


def resolve(link, holo=None):
    """Act on a changelog link. Returns a short description of what happened."""
    link = (link or "").strip()
    if not link:
        return "no link"

    if link.startswith("img://"):
        _open(BASE + link[len("img://"):])
        return "image"

    if link.startswith("interactive://"):
        _open(BASE + link[len("interactive://"):].lstrip("/"))
        return "interactive page"

    if link.startswith("event://pick-hologram-"):
        tail = link[len("event://pick-hologram-"):]
        num = tail.split("||")[0].strip()
        try:
            idx = int(num)
        except ValueError:
            return "bad hologram index"
        if holo is not None and holo.scenes():
            name = holo.select(idx)
            print(f"hologram -> scene {idx}: {name}", flush=True)
            return f"hologram {idx}"
        return "hologram (no scenes)"

    if link.startswith("event://"):
        print(f"event {link} — site-side effect, not reproduced", flush=True)
        return "event (not reproduced)"

    if link.startswith(("http://", "https://")):
        _open(link)
        return "url"

    print(f"unhandled link {link!r}", flush=True)
    return "unhandled"
