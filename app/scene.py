#!/usr/bin/env python3
"""Scene model for the floor796 wallpaper: tiles, camera, objects.

No GTK here beyond GdkPixbuf for WebP decoding — this module is importable by
both the headless renderer and the interactive viewer.
"""

import json
import os

SPACING_W, SPACING_H = 1016, 812
TILE_W, TILE_H = 1024, 820
ANIM_FRAME_W, ANIM_FRAME_H = 512, 410   # must match app/anim.py
ANIM_COLS = 8

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    with open(os.path.join(ROOT, "vendor", name)) as f:
        return json.load(f)


class Camera:
    """Viewport over the scene. x/y = scene pixel at the viewport's top-left."""

    def __init__(self, x=4900.0, y=3200.0, zoom=0.5):
        self.x = float(x)
        self.y = float(y)
        self.zoom = float(zoom)

    def to_scene(self, sx, sy):
        return self.x + sx / self.zoom, self.y + sy / self.zoom

    def clamp(self, scene_w, scene_h, view_w, view_h):
        span_x = view_w / self.zoom
        span_y = view_h / self.zoom
        self.x = min(max(self.x, 0), max(0, scene_w - span_x))
        self.y = min(max(self.y, 0), max(0, scene_h - span_y))

    def __repr__(self):
        return f"Camera({self.x:.0f},{self.y:.0f} @ {self.zoom:g}x)"


class Scene:
    def __init__(self, tiles_dir=None, rips_dir=None):
        self.matrix = _load("matrix.json")
        self.changelog = _load("changelog.json")
        self.tiles_dir = tiles_dir or os.path.join(ROOT, "vendor", "tiles")
        self.rips_dir = rips_dir or os.path.join(ROOT, "vendor", "rips")
        self.tiles = {}          # id -> (row, col, preview_path)
        self.width = 0
        self.height = 0
        for r, row in enumerate(self.matrix["mat"]):
            for c, tile in enumerate(row):
                if not isinstance(tile, dict) or not tile.get("id"):
                    continue
                self.tiles[tile["id"]] = (r, c, tile.get("preview", ""))
                self.width = max(self.width, c * SPACING_W + TILE_W)
                self.height = max(self.height, r * SPACING_H + TILE_H)
        self.objects = self._objects()
        self._surfaces = {}      # tid -> cairo surface (LRU, see surface())
        self._surface_order = []
        self.surface_budget = 40  # ~3.4 MB per tile => ~136 MB cap

    # ── geometry ────────────────────────────────────────────────────────────
    def tile_rect(self, tid):
        r, c, _ = self.tiles[tid]
        return c * SPACING_W, r * SPACING_H, TILE_W, TILE_H

    def _objects(self):
        pos = {tid: (r, c) for tid, (r, c, _) in self.tiles.items()}
        out = []
        for o in self.changelog:
            verts = []
            for part in (o.get("p") or "").split(";"):
                f = part.split(",")
                if len(f) < 3:
                    continue
                try:
                    ly, lx = int(f[1]), int(f[2])      # Y before X
                except ValueError:
                    continue
                rc = pos.get(f[0])
                if rc:
                    verts.append((rc[1] * SPACING_W + lx, rc[0] * SPACING_H + ly))
            if not verts:
                continue
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            if x2 - x1 < 2 and y2 - y1 < 2:
                continue
            out.append({"id": o.get("id"), "title": o.get("t", ""),
                        "date": o.get("d", ""), "link": o.get("l", ""),
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return out

    # ── assets ──────────────────────────────────────────────────────────────
    def surface(self, tid):
        """Lazily decoded tile image as a cairo surface (cached).

        Prefers the lossless rip from vendor/rips/ — the preview WebPs are
        low-quality thumbnails and are visibly blurry when displayed.
        """
        if tid in self._surfaces:
            self._surface_order.remove(tid)
            self._surface_order.append(tid)
            return self._surfaces[tid]
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        import cairo
        import gi as _gi
        _gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk

        for path in (os.path.join(self.rips_dir, f"{tid}.webp"),
                     os.path.join(self.tiles_dir, f"{tid}.webp")):
            if os.path.exists(path) and os.path.getsize(path) > 1024:
                break
        else:
            self._surfaces[tid] = None
            return None
        pix = GdkPixbuf.Pixbuf.new_from_file(path)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                  pix.get_width(), pix.get_height())
        cr = cairo.Context(surf)
        Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
        cr.paint()
        self._surfaces[tid] = surf
        self._surface_order.append(tid)
        while len(self._surface_order) > self.surface_budget:
            old = self._surface_order.pop(0)
            self._surfaces.pop(old, None)
        return surf

    # ── drawing ─────────────────────────────────────────────────────────────
    def visible_tiles(self, cam, view_w, view_h):
        sx0, sy0 = cam.x, cam.y
        sx1, sy1 = cam.x + view_w / cam.zoom, cam.y + view_h / cam.zoom
        for tid in self.tiles:
            tx, ty, tw, th = self.tile_rect(tid)
            if tx < sx1 and tx + tw > sx0 and ty < sy1 and ty + th > sy0:
                yield tid

    def draw(self, cr, cam, view_w, view_h, objs=True, hover=None, smooth=False,
             anim=None, holo=None):
        import cairo
        cr.set_source_rgb(0.02, 0.02, 0.03)
        cr.paint()
        cr.save()
        cr.scale(cam.zoom, cam.zoom)
        cr.translate(-cam.x, -cam.y)
        for tid in self.visible_tiles(cam, view_w, view_h):
            frame = anim.frame_for(tid, cam.zoom) if anim is not None else None
            surf = frame if frame is not None else self.surface(tid)
            if surf is None:
                continue
            tx, ty, _, _ = self.tile_rect(tid)
            cr.save()
            cr.rectangle(tx, ty, TILE_W, TILE_H)
            cr.clip()
            if frame is not None:
                # Frames are 512x410 (1:1 at 0.5 zoom); stretch over the tile.
                cr.translate(tx, ty)
                cr.scale(TILE_W / frame.get_width(), TILE_H / frame.get_height())
                cr.set_source_surface(frame, 0, 0)
            else:
                cr.set_source_surface(surf, tx, ty)
            # Pixel art: nearest-neighbour by default. Bilinear smears the
            # sprite edges and costs far more per pixel.
            cr.get_source().set_filter(
                cairo.FILTER_GOOD if smooth else cairo.FILTER_NEAREST)
            cr.paint()
            cr.restore()
        cr.restore()

        if holo is not None:
            holo.draw(cr, cam, view_w, view_h)

        if objs:
            self._draw_boxes(cr, cam, view_w, view_h, hover)

    def _draw_boxes(self, cr, cam, view_w, view_h, hover):
        """Only the hovered object is ever drawn.

        Everything else is invisible: this is a wallpaper, not a debug view.
        """
        if not hover:
            return
        o = hover
        z = cam.zoom
        x = (o["x1"] - cam.x) * z
        y = (o["y1"] - cam.y) * z
        w = (o["x2"] - o["x1"]) * z
        h = (o["y2"] - o["y1"]) * z
        cr.set_source_rgba(1.0, 0.85, 0.2, 0.20)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_source_rgba(1.0, 0.85, 0.2, 1.0)
        cr.set_line_width(max(2, 2 * z))
        cr.rectangle(x, y, w, h)
        cr.stroke()
        self._panel(cr, o)

    def _panel(self, cr, o):
        import cairo as _c
        pad, lh = 12, 18
        lines = [o["title"] or f"object {o['id']}"]
        if o["date"]:
            lines.append(o["date"])
        if o["link"]:
            lines.append(o["link"][:70])
        cr.select_font_face("Sans", _c.FONT_SLANT_NORMAL, _c.FONT_WEIGHT_NORMAL)
        cr.set_font_size(13)
        w = max(cr.text_extents(t)[2] for t in lines) + pad * 2
        h = lh * len(lines) + pad * 2
        x, y = 24, 24
        cr.set_source_rgba(0.05, 0.05, 0.07, 0.9)
        cr.rectangle(x, y, w, h)
        cr.fill_preserve()
        cr.set_source_rgba(1.0, 0.85, 0.2, 0.9)
        cr.set_line_width(1.5)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 1)
        for i, t in enumerate(lines):
            cr.move_to(x + pad, y + pad + lh * (i + 0.8))
            cr.show_text(t)

    def object_at(self, cam, px, py, radius=0, allow=None):
        """Smallest object under the cursor, optionally limited to `allow`.

        The filter is applied *before* picking, not afterwards: a rejected
        object that happened to be smallest would otherwise win and then be
        discarded, blocking whatever sits underneath it.
        """
        sx, sy = cam.to_scene(px, py)
        best = None
        for o in self.objects:
            if o["x1"] <= sx <= o["x2"] and o["y1"] <= sy <= o["y2"]:
                if allow is not None and not allow(o):
                    continue
                area = (o["x2"] - o["x1"]) * (o["y2"] - o["y1"])
                if best is None or area < best[0]:
                    best = (area, o)
        return best[1] if best else None


def headless(scene, cam, w, h, out, objs=True):
    import cairo
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    scene.draw(cr, cam, w, h, objs=objs)
    surf.write_to_png(out)
    return out
