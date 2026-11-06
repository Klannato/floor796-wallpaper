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

GAP, FADE_IN, NORMAL, FADE_OUT = 12, 24, 60, 24
CYCLE = GAP + FADE_IN + NORMAL + FADE_OUT      # 120 frames = 10 s


class Hologram:
    def __init__(self, holo_dir=None):
        self.dir = holo_dir or DIR
        self._maps = {}
        self._cur = {}
        self._names = None

    def scenes(self):
        if self._names is None:
            if not os.path.isdir(self.dir):
                self._names = []
            else:
                self._names = sorted(f for f in os.listdir(self.dir)
                                     if f.endswith(".raw"))
        return self._names

    def _map(self, name):
        mv = self._maps.get(name)
        if mv is not None:
            return mv
        path = os.path.join(self.dir, name)
        try:
            fd = open(path, "rb")
            m = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_COPY)
            fd.close()
        except OSError:
            return None
        mv = memoryview(m)
        self._maps[name] = mv
        return mv

    def _surface(self, name, idx):
        key = (name, idx)
        cur = self._cur.get(key)
        if cur is not None:
            return cur[1]
        mv = self._map(name)
        if mv is None:
            return None
        import cairo
        off = idx * FRAME_BYTES
        surf = cairo.ImageSurface.create_for_data(
            mv[off:off + FRAME_BYTES], cairo.FORMAT_ARGB32,
            SCENE_W, SCENE_H, SCENE_W * 4)
        self._cur = {key: (idx, surf)}     # one scene frame is enough
        return surf

    def state(self, now=None):
        """(scene name, frame index, alpha) for this instant."""
        names = self.scenes()
        if not names:
            return None, 0, 0.0
        t = int((now or time.time()) * FPS)
        scene_no = t // CYCLE
        phase = t % CYCLE
        name = names[scene_no % len(names)]
        if phase < GAP:
            return name, 0, 0.0
        phase -= GAP
        if phase < FADE_IN:
            return name, min(N_FRAMES - 1, int(phase / FADE_IN * N_FRAMES)), phase / FADE_IN
        phase -= FADE_IN
        if phase < NORMAL:
            return name, min(N_FRAMES - 1, phase), 1.0
        phase -= NORMAL
        return name, N_FRAMES - 1, max(0.0, 1 - phase / FADE_OUT)

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
        surf = self._surface(name, idx)
        if surf is None:
            return

        cr.save()
        cr.scale(cam.zoom, cam.zoom)
        cr.translate(-cam.x, -cam.y)
        # clip to the room's projection quad
        cr.move_to(*CLIP[0])
        for p in CLIP[1:]:
            cr.line_to(*p)
        cr.close_path()
        cr.clip()
        cr.set_source_surface(surf, HOLO_X, HOLO_Y)
        cr.get_source().set_filter(__import__("cairo").FILTER_NEAREST)
        cr.paint_with_alpha(alpha)
        cr.restore()
