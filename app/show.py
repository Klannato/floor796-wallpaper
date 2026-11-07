#!/usr/bin/env python3
"""Show a link's payload inside the app instead of throwing it at a browser.

`img://` and the `||https://…jpg` tails are pictures — opening a browser tab for
each one is a detour that loses the wallpaper's context, and on a kiosk-like
wallpaper it is simply wrong. They are downloaded (cached under
`vendor/links/`) and shown in a normal GTK window scaled to fit, so the panel
title still tells you what you clicked.

Interactive pages (`interactive://`) are real web apps — the shower cam plays
video, Racer-796 is a game — so they keep going to an external program
(`xdg-open`); an in-app WebKit view would mean a second GTK version in a
GTK3 process, which is not worth it for a page that is itself a whole app.

Nothing here blocks: the window is created on the GTK main loop and dismissed
with Escape, a click, or the close button.
"""

import hashlib
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "vendor", "links")
_win_refs = []          # keep windows alive; GTK does not own them for us
_video_refs = []        # ffplay children, reaped on the next open


def _cached(url):
    os.makedirs(CACHE, exist_ok=True)
    ext = os.path.splitext(url.split("?")[0])[1] or ".png"
    name = hashlib.sha1(url.encode()).hexdigest()[:16] + ext
    return os.path.join(CACHE, name)


def fetch(url, timeout=30):
    """Download to the cache (once). Returns the local path."""
    path = _cached(url)
    if os.path.exists(path) and os.path.getsize(path) > 512:
        return path
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "floor796-wallpaper"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def show_image(url, title="", max_frac=0.8):
    """Open `url` in a window, scaled to fit. Returns the window or None."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import Gtk, GdkPixbuf, GLib
    except Exception:
        return None

    win = Gtk.Window()
    win.set_title(title or "floor796")
    win.set_position(Gtk.WindowPosition.CENTER)
    win.set_keep_above(True)

    def load_and_show(path):
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception as e:            # not an image after all
            print(f"show_image: {e}", flush=True)
            win.destroy()
            return False
        screen = win.get_screen()
        mw = int(screen.get_width() * max_frac)
        mh = int(screen.get_height() * max_frac)
        scale = min(mw / pix.get_width(), mh / pix.get_height(), 3.0)
        if scale < 1.0 or pix.get_width() > mw or pix.get_height() > mh:
            pix = pix.scale_simple(int(pix.get_width() * scale),
                                   int(pix.get_height() * scale),
                                   GdkPixbuf.InterpType.NEAREST if scale >= 1
                                   else GdkPixbuf.InterpType.BILINEAR)
        img = Gtk.Image.new_from_pixbuf(pix)
        win.add(img)
        win.show_all()
        return False

    def worker():
        try:
            path = fetch(url)
        except Exception as e:
            print(f"show_image: fetch failed {e}", flush=True)
            return
        GLib.idle_add(load_and_show, path)

    win.connect("destroy", lambda *_: _win_refs.remove(win)
                if win in _win_refs else None)
    win.connect("key-press-event", lambda w, e: (
        w.destroy() if e.keyval == 65307 else None) and None)   # Escape
    win.add_events(0)
    _win_refs.append(win)
    threading.Thread(target=worker, daemon=True).start()
    return win


def show_video(url, title=""):
    """Play a short video in ffplay (already installed; ~40 MB while open)."""
    if not _which("ffplay"):
        return False
    cmd = ["ffplay", "-loop", "0", "-an", "-loglevel", "quiet",
           "-window_title", title or "floor796", url]
    _video_refs[:] = [p for p in _video_refs if p.poll() is None]
    try:
        _video_refs.append(subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    except OSError as e:
        print(f"show_video: {e}", flush=True)
        return False
    print(f"video window: {url}", flush=True)
    return True


def _which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


if __name__ == "__main__":
    # manual check: app/show.py <url-or-file> [title]
    arg = sys.argv[1]
    url = arg if "://" in arg else "file://" + os.path.abspath(arg)
    gi_win = show_image(url, sys.argv[2] if len(sys.argv) > 2 else "")
    if gi_win is None:
        sys.exit("no GTK")
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    Gtk.main()
