#!/usr/bin/env python3
"""Route an `interactive://` page to the lightest thing that can show it.

Most of floor796's interactive pages are not apps. Measured payloads:

    mrbean/index_v1.html          one animated image  (0.7 MB webp)
    memorial1/index-v1.html       one image           (0.1 MB webp + props)
    change-my-mind/index-v6.html  one image           (0.3 MB jpg)
    shower-cam/index_v1.html      a bare <video loop muted> (0.6 MB mp4)

Those need no JS engine at all: an image opens in the app's own window, and the
video goes to `ffplay`, which is already installed and a tenth the weight of a
browser. Everything that really is a canvas app — Racer-796, the three quests,
the drawing screen, the synth — goes to one WebKit child process (`webview.py`),
because WebKit 6 is a GTK4 namespace and the wallpaper is GTK3; a process can
load only one GTK. The statistics page pulls the site's whole bundle and stays
with the browser.

Routing is a table, not a guess: if a page is not listed here it goes to the
fallback below, and `--list` prints what would happen.
"""

import os
import subprocess
import sys

BASE = "https://floor796.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# page path (without query) -> how to show it
PAGES = {
    "mrbean/index_v1.html": ("image", ["/data/misc/video/mrbean.webp"]),
    "memorial1/index-v1.html": ("image", ["/interactive/memorial1/plaque-en.webp"]),
    "change-my-mind/index-v6.html": ("image", ["/data/misc/change-my-mind.jpg"]),
    "shower-cam/index_v1.html": ("video", ["/data/misc/shower-cam/shower-cam.mp4"]),
    # canvas apps: a JS engine is genuinely required
    "racer796/index.html": ("webkit", None),
    "quest-tuner/index-v1.html": ("webkit", None),
    "quest-gems/index-v1.html": ("webkit", None),
    "fun-drawing-v9/index-v5.html": ("webkit", None),
    "melody/index-v3.html": ("webkit", None),
    "phone/index-v1.html": ("webkit", None),
    "quest-laboratory/index-v1.html": ("webkit", None),
    "quest-laboratory/pc-v1.html": ("webkit", None),
    "quest-laboratory/microscope-v1.html": ("webkit", None),
    # pulls the site's whole app bundle: a browser is the honest answer
    "stat/index-v4.html": ("browser", None),
}


def _open_browser(url):
    subprocess.Popen(["xdg-open", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"browser: {url}", flush=True)
    return "interactive page (browser)"


def _run_webkit(url, title, size=None):
    script = os.path.join(ROOT, "app", "webview.py")
    if not os.path.exists(script):
        return None
    cmd = ["/usr/bin/python3", script, url, title]
    if size:
        cmd += [str(size[0]), str(size[1])]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        print(f"webkit: {url}", flush=True)
        return "interactive page (webkit)"
    except OSError as e:
        print(f"webkit failed: {e}", flush=True)
        return None


def show(rel, title=""):
    """Show the page `rel` (path after interactive://). Returns a description."""
    key = rel.split("?")[0].lstrip("/")
    kind, assets = PAGES.get(key, (None, None))
    url = f"{BASE}/interactive/{rel}"

    if kind == "image" and assets:
        try:
            import show as _show
            win = _show.show_image(BASE + assets[0], title or key)
            if win is not None:
                print(f"page payload as image: {assets[0]}", flush=True)
                return "page image (in-app)"
        except Exception as e:
            print(f"image route failed ({e}); falling back", flush=True)
        return _open_browser(url)

    if kind == "video" and assets:
        try:
            import show as _show
            if _show.show_video(BASE + assets[0], title or key):
                return "page video (ffplay)"
        except Exception as e:
            print(f"video route failed ({e}); falling back", flush=True)
        return _open_browser(url)

    if kind == "webkit":
        got = _run_webkit(url, title or key)
        if got:
            return got
        return _open_browser(url)

    if kind == "browser":
        return _open_browser(url)

    # Unlisted page: WebKit first (cheap, closable), browser as the last resort.
    return _run_webkit(url, title or key) or _open_browser(url)


def table():
    print(f"{'page':34s} {'route':9s} payload")
    for k, (kind, assets) in sorted(PAGES.items()):
        print(f"{k:34s} {kind:9s} {(assets or ['—'])[0]}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        table()
    else:
        rel = sys.argv[1] if len(sys.argv) > 1 else ""
        print(show(rel, sys.argv[2] if len(sys.argv) > 2 else ""))
