#!/usr/bin/env python3
"""Draw the site's addon clips over the scene.

Everything here comes from `vendor/addons/manifest.json`, written by
`tools/rip_addons.py` from the addon renderers' own constants. Three shapes:

  always   scenery that animates by itself (teleport room, cemetery fog) —
           the frame index follows the 12 fps scene clock, and a multi-clip
           addon (the teleporter's 8 characters) advances one clip per loop,
           so every character is visible without clicking anything
  event    a one-shot played when its region is clicked (waldo waves, meg,
           banksy), `duration` frames long at 12 fps

Positioning is the site's: the clip is drawn at the scene point the addon
declares, offset by its own OFFSET_X/OFFSET_Y, and clipped to the addon's
polygon (the teleporter's room contains its own walls, so the polygon is what
keeps it inside the pad area).

Cost is bounded on purpose: one clip's frames are resident at a time (~28 MB
for a 289x412 teleporter scene) and dropped when the clip changes, matching
the anim pack rule that nothing decodes during a paint.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "vendor", "addons", "manifest.json")
FPS = 12.0

# The changelog names an event; the addon is named for its region. Two of them
# disagree, and the mismatch is invisible until someone clicks and nothing
# happens (meg-family-guy -> meg, fog -> cemetery-fog).
ALIASES = {"meg-family-guy": "meg", "fog": "cemetery-fog"}


def _surface(path):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import GdkPixbuf, Gdk
    import cairo
    pix = GdkPixbuf.Pixbuf.new_from_file(path)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, pix.get_width(),
                              pix.get_height())
    cr = cairo.Context(surf)
    Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
    cr.paint()
    return surf


class Clip:
    """One decoded clip: a directory of 000.webp … frames."""

    def __init__(self, base, info):
        self.dir = os.path.join(base, info["dir"])
        self.frames = info["frames"]
        self.w = self.h = None
        self.title = info.get("title", "")
        self._cache = {}

    def frame(self, i):
        i %= self.frames
        surf = self._cache.get(i)
        if surf is None:
            path = os.path.join(self.dir, f"{i:03d}.webp")
            if not os.path.exists(path):
                return None
            surf = _surface(path)
            self._cache[i] = surf
            self.w, self.h = surf.get_width(), surf.get_height()
        return surf

    def drop(self):
        self._cache.clear()


class Addon:
    def __init__(self, base, entry):
        self.name = entry["name"]
        self.x = entry["x"]
        self.y = entry["y"]
        self.w = entry["width"]
        self.h = entry["height"]
        self.duration = max(1, entry["duration"])
        self.trigger = entry["trigger"]
        self.clip_pts = [tuple(p) for p in entry.get("clip") or []]
        self.clips = {k: Clip(base, v) for k, v in entry["clips"].items()}
        self.order = sorted(self.clips, key=lambda k: (len(k), k))
        self.current = self.order[0] if self.order else None
        self.started = None          # monotonic time of a one-shot
        # A multi-clip addon (the teleporter's 8 characters) cycles, but it must
        # not hard-cut: each clip is a full opaque recording of the room, so a
        # bare swap repaints the whole pad. Fading the edge frames in and out
        # reads as materialising, which is what the room is for.
        self.cycle = entry.get("cycle", len(self.clips) > 1)
        self.fade = entry.get("fade", 10) if self.cycle else 0

    def active(self):
        return self.trigger == "always" or self.started is not None

    def advance(self):
        """Next clip in the list (the teleporter's 8 characters)."""
        if len(self.order) > 1 and self.current is not None:
            i = self.order.index(self.current)
            self.current = self.order[(i + 1) % len(self.order)]
            return self.current
        return None

    def frame_index(self, now):
        if self.started is not None:
            el = int((now - self.started) * FPS)
            if el >= self.duration:      # one-shot finished
                self.started = None
                return None
            return el % self.clips[self.current].frames if self.current else None
        if self.trigger != "always":
            return None
        if self.current is None:
            return None
        t = int(now * FPS)
        frames = self.clips[self.current].frames
        if self.cycle:
            key = self.order[(t // frames) % len(self.order)]
            if key != self.current:
                self.clips[self.current].drop()
                self.current = key
        return t % frames

    def alpha(self, i):
        """Fade the first and last `fade` frames of a cycling clip."""
        if not self.fade or self.current is None:
            return 1.0
        n = self.clips[self.current].frames
        return max(0.0, min(1.0, i / self.fade, (n - 1 - i) / self.fade))


class Addons:
    def __init__(self, path=MANIFEST):
        self.items = []
        self.base = os.path.dirname(path)
        try:
            with open(path) as f:
                entries = json.load(f)
        except (OSError, ValueError):
            entries = []
        for e in entries:
            try:
                self.items.append(Addon(self.base, e))
            except KeyError:
                continue
        if self.items:
            print(f"addons: {len(self.items)} region(s), "
                  f"{sum(len(a.clips) for a in self.items)} clip(s)",
                  flush=True)

    def event_names(self):
        """Event names this manifest can answer, aliases included."""
        names = {a.name for a in self.items}
        names |= {k for k, v in ALIASES.items() if v in names}
        return names

    def signature(self, now):
        """Which (addon, frame) pairs are live right now.

        The tick uses this to repaint only when something actually changes: an
        unconditional `queue_draw` at 10 Hz burns a quarter of a core for scenes
        where nothing moved, and a wallpaper is idle most of the time.
        """
        sig = []
        for a in self.items:
            if not a.active() or a.current is None:
                continue
            i = a.frame_index(now)
            if i is not None:
                sig.append((a.name, a.current, i))
        return tuple(sig)

    def trigger_event(self, name):
        """React to a changelog event name. Returns True if an addon owns it."""
        target = ALIASES.get(name, name)
        for a in self.items:
            if a.name != target:
                continue
            if a.trigger == "event":
                a.started = _now()
            return True      # `always` addons are already running
        return False

    def click(self, cam, px, py):
        """Advance a multi-clip addon if the click lands in its region."""
        sx, sy = cam.to_scene(px, py)
        for a in self.items:
            if (len(a.clips) > 1 and a.x <= sx <= a.x + a.w
                    and a.y <= sy <= a.y + a.h):
                a.advance()
                return a.name
        return None

    def draw(self, cr, cam, view_w, view_h, now=None):
        import cairo
        if not self.items:
            return
        now = _now() if now is None else now
        z = cam.zoom
        for a in self.items:
            if not a.active():
                continue
            i = a.frame_index(now)
            if i is None or a.current is None:
                continue
            # cull cheaply against the viewport
            vx0, vy0 = cam.x, cam.y
            if (a.x > vx0 + view_w / z or a.x + a.w < vx0
                    or a.y > vy0 + view_h / z or a.y + a.h < vy0):
                continue
            surf = a.clips[a.current].frame(i)
            if surf is None:
                continue
            cr.save()
            if a.clip_pts:
                cr.new_path()
                for k, (sx, sy) in enumerate(a.clip_pts):
                    dx = (sx - cam.x) * z
                    dy = (sy - cam.y) * z
                    if k == 0:
                        cr.move_to(dx, dy)
                    else:
                        cr.line_to(dx, dy)
                cr.close_path()
                cr.clip()
            cr.translate((a.x - cam.x) * z, (a.y - cam.y) * z)
            cr.scale(z, z)
            cr.set_source_surface(surf, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            a_alpha = a.alpha(i)
            if a_alpha >= 0.999:
                cr.paint()
            else:
                cr.paint_with_alpha(a_alpha)
            cr.restore()


def _now():
    import time
    return time.monotonic()
