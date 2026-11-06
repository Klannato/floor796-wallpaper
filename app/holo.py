#!/usr/bin/env python3
"""The teleporter room's hologram.

This is not part of the tile art — the site composites six 805x646 scene
recordings over the room at a fixed map position, clipped to a quad, on its own
10-second cycle. Constants below come from the kiosk's `hologram.py`, which is
the authoritative copy.

Cycle per scene (12 fps, 120 frames):
    12 f empty · 24 f materialise · 60 f play · 24 f dematerialise
"""

import mmap
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "vendor", "holo")

SCENE_W, SCENE_H = 805, 646
FPS = 12
N_FRAMES = 60
FRAME_BYTES = SCENE_W * SCENE_H * 4

# Map position (kiosk: anchor tile t4r0 at row 4, col 6, local 704,477)
HOLO_X = 6 * 1016 + 704 - 7
HOLO_Y = 4 * 812 + 477 + 29

# Clip quad, map coords (kiosk CLIP_POINTS is (x, y))
CLIP = [(7 * 1016 + 105, 4 * 812 + 507),
        (7 * 1016 + 486, 5 * 812 + 0),
        (7 * 1016 + 61, 5 * 812 + 339),
        (6 * 1016 + 696, 5 * 812 + 34)]

OFFSETS_PATH = os.path.join(ROOT, "config", "holo_offsets.json")

GAP, FADE_IN, NORMAL, FADE_OUT = 12, 24, 60, 24
CYCLE = GAP + FADE_IN + NORMAL + FADE_OUT      # 120 frames = 10 s


def _phase_frame(phase):
    if phase < GAP:
        return 0
    phase -= GAP
    if phase < FADE_IN:
        return min(N_FRAMES - 1, int(phase / FADE_IN * N_FRAMES))
    phase -= FADE_IN
    if phase < NORMAL:
        return min(N_FRAMES - 1, phase)
    return N_FRAMES - 1


def _phase_alpha(phase):
    if phase < GAP:
        return 0.0
    phase -= GAP
    if phase < FADE_IN:
        return phase / FADE_IN
    phase -= FADE_IN
    if phase < NORMAL:
        return 1.0
    phase -= NORMAL
    return max(0.0, 1 - phase / FADE_OUT)


class Hologram:
    def __init__(self, holo_dir=None):
        self.dir = holo_dir or DIR
        self._maps = {}
        self._cur = {}
        self._names = None
        self.offsets = self._load_offsets()
        # preview mode, used by the alignment tool
        self.preview_name = None
        self.preview_frame = None
        # scene forced by clicking a pick-hologram pad: (index, t0)
        self.forced = None

    # ── per-scene alignment offsets (hand-tuned in app/align.py) ────────────
    @staticmethod
    def _load_offsets():
        try:
            import json
            with open(OFFSETS_PATH) as f:
                return {k: tuple(v) for k, v in json.load(f).items()}
        except Exception:
            return {}

    def reload_offsets(self):
        """Re-read config/holo_offsets.json (after hand alignment)."""
        self.offsets = self._load_offsets()
        return self.offsets

    def save_offsets(self):
        import json
        os.makedirs(os.path.dirname(OFFSETS_PATH), exist_ok=True)
        with open(OFFSETS_PATH, "w") as f:
            json.dump({k: list(v) for k, v in sorted(self.offsets.items())},
                      f, indent=2)

    def offset_for(self, name):
        return self.offsets.get(name, (0, 0))

    def tier(self, zoom):
        """0 = half-res pack, 1 = full. Part of every cache key."""
        lo = self.dir.rstrip("/") + "_lo"
        return 0 if (zoom < 0.7 and os.path.isdir(lo)) else 1

    def dir_for(self, zoom):
        """Half-res scenes when zoomed out: each full one is 125 MB of frames."""
        if zoom < 0.7:
            lo = self.dir.rstrip("/") + "_lo"
            if os.path.isdir(lo):
                return lo
        return self.dir

    def scenes(self, zoom=None):
        if zoom is not None:
            d = self.dir_for(zoom)
        else:
            d = self.dir
        if not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.endswith(".raw"))

    def _map(self, name, zoom=None):
        key = (name, self.tier(zoom if zoom is not None else 1.0))
        mv = self._maps.get(key)
        if mv is not None:
            return mv
        path = os.path.join(self.dir_for(zoom if zoom is not None else 1.0), name)
        try:
            fd = open(path, "rb")
            m = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_COPY)
            fd.close()
        except OSError:
            return None
        mv = memoryview(m)
        # One scene at a time: each is 125 MB of frames, and only one is shown.
        self._maps = {key: mv}
        self._cur = {}
        return mv

    def _surface(self, name, idx, zoom=None):
        key = (name, idx, self.tier(zoom if zoom is not None else 1.0))
        cur = self._cur.get(key)
        if cur is not None:
            return cur[1]
        mv = self._map(name, zoom)
        if mv is None:
            return None
        import cairo
        # Always 60 frames; the frame size differs between the full and half
        # packs, so it is inferred per file rather than from FRAME_BYTES.
        n = N_FRAMES
        fb = len(mv) // n
        est = int(round((fb / 4 * SCENE_W / SCENE_H) ** 0.5))
        w = h = 0
        for cand in (est, est - 1, est + 1, est - 2, est + 2):
            if cand > 0 and fb % (cand * 4) == 0:
                hh = fb // (cand * 4)
                if hh > 0:
                    w, h = cand, hh
                    break
        if not w:
            return None
        off = idx * fb
        surf = cairo.ImageSurface.create_for_data(
            mv[off:off + fb], cairo.FORMAT_ARGB32, w, h, w * 4)
        self._cur = {key: (idx, surf)}     # one scene frame is enough
        return surf

    def select(self, index, now=None):
        """Select a hologram scene, as clicking a pad on the site does."""
        names = self.scenes()
        if not names:
            return None
        if not 0 <= index < len(names):
            # changelog has pads 0..13 but only a handful of scenes are public
            print(f"hologram scene {index} not available "
                  f"({len(names)} ripped)", flush=True)
            return None
        self.forced = (index, now or time.time())
        return names[index]

    def clear_selection(self):
        self.forced = None

    def state(self, now=None):
        if self.forced is not None:
            idx, t0 = self.forced
            names = self.scenes()
            phase = int(((now or time.time()) - t0) * FPS) % CYCLE
            return names[idx % len(names)], _phase_frame(phase), _phase_alpha(phase)
        if self.preview_name is not None:
            idx = 0 if self.preview_frame is None else self.preview_frame
            return self.preview_name, idx, 1.0
        """(scene name, frame index, alpha) for this instant."""
        names = self.scenes()
        if not names:
            return None, 0, 0.0
        t = int((now or time.time()) * FPS)
        phase = t % CYCLE
        name = names[(t // CYCLE) % len(names)]
        return name, _phase_frame(phase), _phase_alpha(phase)

    def current_index(self, now=None):
        name = self.state(now)[0]
        names = self.scenes()
        try:
            return names.index(name)
        except ValueError:
            return None

    def visible(self, cam, w, h):
        sx1, sy1 = cam.x + w / cam.zoom, cam.y + h / cam.zoom
        return not (HOLO_X > sx1 or HOLO_X + SCENE_W < cam.x
                    or HOLO_Y > sy1 or HOLO_Y + SCENE_H < cam.y)

    def draw(self, cr, cam, w, h, now=None):
        if not self.visible(cam, w, h):
            return
        name, idx, alpha = self.state(now)
        if not name or alpha <= 0.01:
            return
        surf = self._surface(name, idx, cam.zoom)
        if surf is None:
            return

        cr.save()
        cr.scale(cam.zoom, cam.zoom)
        cr.translate(-cam.x, -cam.y)
        dx, dy = self.offset_for(name)
        # clip to the room's projection quad (moves with the scene)
        cr.move_to(CLIP[0][0] + dx, CLIP[0][1] + dy)
        for p in CLIP[1:]:
            cr.line_to(p[0] + dx, p[1] + dy)
        cr.close_path()
        cr.clip()
        # A half-res pack must be scaled back over the same footprint, or the
        # projection covers half the room while the clip quad still fits the
        # whole floor.
        scale = SCENE_W / surf.get_width()
        cr.translate(HOLO_X + dx, HOLO_Y + dy)
        cr.scale(scale, scale)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(__import__("cairo").FILTER_NEAREST)
        cr.paint_with_alpha(alpha)
        cr.restore()
