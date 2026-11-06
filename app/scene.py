#!/usr/bin/env python3
"""Scene model for the floor796 wallpaper: tiles, camera, objects.

No GTK here beyond GdkPixbuf for WebP decoding — this module is importable by
both the headless renderer and the interactive viewer.
"""

import json
import os

SPACING_W, SPACING_H = 1016, 812
TILE_W, TILE_H = 1024, 820
# Links that name a region rather than an action. `hologram-area` is the only
# one in the data; it must never produce a box or swallow a click.
MARKER_LINKS = {"hologram-area"}

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
        self.keyed_dir = os.path.join(ROOT, "vendor", "keyed")
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
        self.mask_path_set = False
        self.empty, self.content_bbox = self._content_index()
        # how much of each tile is flat backing; a mostly-empty tile loses its
        # animation so its opaque frames don't repaint the slab we keyed out
        try:
            with open(os.path.join(ROOT, "vendor", "keyed_index.json")) as f:
                self.keyed_pct = json.load(f)
        except Exception:
            self.keyed_pct = {}
        self.anim_max_backing = 40
        self.objects = self._objects()
        self._surfaces = {}      # tid -> cairo surface (LRU, see surface())
        self._surface_order = []
        self.surface_budget = 16  # ~3.4 MB per tile => ~55 MB cap; a
                                  # viewport covers ~12 tiles at 0.5 zoom

    def _content_index(self):
        """Tiles that are pure background, plus the bounding box of real art.

        59 of the 110 tiles are literally flat (stddev 0.0): the scene is a
        jagged complex on a void. Drawing those paints a grey slab over any
        wallpaper behind it, so they are skipped and the art bbox is what the
        render is cropped to.
        """
        cache = os.path.join(ROOT, "vendor", "content_index.json")
        try:
            with open(cache) as f:
                d = json.load(f)
            return set(d["empty"]), tuple(d["bbox"])
        except Exception:
            pass

        from PIL import Image, ImageStat
        empty, drawn = [], []
        for tid, (r, c, _) in self.tiles.items():
            path = os.path.join(self.rips_dir, f"{tid}.webp")
            if not os.path.exists(path):
                path = os.path.join(self.tiles_dir, f"{tid}.webp")
            try:
                st = ImageStat.Stat(Image.open(path).convert("RGB"))
                flat = max(st.stddev) < 3.0
            except Exception:
                flat = True
            (empty if flat else drawn).append(tid)
        if drawn:
            rects = [self.tile_rect(t) for t in drawn]
            bbox = (min(r[0] for r in rects), min(r[1] for r in rects),
                    max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects))
        else:
            bbox = (0, 0, self.width, self.height)
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w") as f:
                json.dump({"empty": sorted(empty), "bbox": list(bbox)}, f)
        except OSError:
            pass
        return set(empty), bbox

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

        # With a silhouette mask loaded, the mask alone decides what is art:
        # the colour key cannot tell void from dark artwork that touches it, and
        # keys pixels out of the art edge (stray black dots). Without a mask the
        # key is the only edge treatment we have.
        candidates = ([os.path.join(self.rips_dir, f"{tid}.webp"),
                       os.path.join(self.tiles_dir, f"{tid}.webp")]
                      if self.mask_path_set else
                      [os.path.join(self.keyed_dir, f"{tid}.png"),
                       os.path.join(self.rips_dir, f"{tid}.webp"),
                       os.path.join(self.tiles_dir, f"{tid}.webp")])
        for path in candidates:
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

    def reload_mask(self):
        """Re-read the mask from disk (after editing it in GIMP)."""
        path = getattr(self, "mask_path", None)
        if path:
            self.mask_surf = None
            self._mask_cache_key = None
            self.load_mask(path)
            return True
        return False

    def load_mask(self, path):
        """Load a hand-drawn silhouette: white = keep, black = cut."""
        import cairo
        self.mask_path = path
        self.mask_path_set = True
        from PIL import Image
        im = Image.open(path).convert("L")
        # Full-res A8 is 66 MB of anonymous memory for a silhouette whose only
        # detail is an outline; editing stays at full size on disk.
        self.mask_scale = 1.0
        if im.width > 4096:
            self.mask_scale = im.width / 4096
            im = im.resize((4096, int(im.height / self.mask_scale)),
                           Image.NEAREST)
        self.mask_size = im.size
        self.mask_origin = (self.content_bbox[0], self.content_bbox[1])
        buf = bytearray(im.tobytes())
        self.mask_surf = cairo.ImageSurface.create_for_data(
            buf, cairo.FORMAT_A8, im.width, im.height, im.width)
        self._mask_buf = buf          # cairo reads straight from this buffer
        print(f"mask: {path} {im.width}x{im.height} "
              f"(scale {self.mask_scale:g})", flush=True)

    def _mask_device(self, cam, view_w, view_h):
        """Mask rendered into device space at the current zoom/pan.

        A SurfacePattern with a hand-built matrix produced a blank mask; drawing
        the mask into a viewport-sized A8 surface has no matrix ambiguity, at the
        cost of one blit (cached until the camera moves).
        """
        import cairo
        if not getattr(self, "mask_surf", None):
            return None
        key = (round(cam.zoom, 4), round(cam.x, 1), round(cam.y, 1),
               view_w, view_h)
        if getattr(self, "_mask_cache_key", None) == key:
            return self._mask_cache
        surf = cairo.ImageSurface(cairo.FORMAT_A8, view_w, view_h)
        mcr = cairo.Context(surf)
        mcr.scale(cam.zoom, cam.zoom)
        mcr.translate(-(cam.x - self.mask_origin[0]),
                      -(cam.y - self.mask_origin[1]))
        mcr.scale(self.mask_scale, self.mask_scale)
        mcr.set_source_surface(self.mask_surf, 0, 0)
        mcr.get_source().set_filter(cairo.FILTER_NEAREST)
        mcr.paint()
        self._mask_cache, self._mask_cache_key = surf, key
        return surf

    def draw(self, cr, cam, view_w, view_h, objs=True, hover=None, smooth=False,
             anim=None, holo=None, background=None, all_boxes=False,
             addons=None):
        import cairo
        if background is not None:
            paint_cover(cr, background, view_w, view_h)
        else:
            cr.set_source_rgb(0.02, 0.02, 0.03)
            cr.paint()

        mask = self._mask_device(cam, view_w, view_h)
        if mask is not None:
            # Draw the scene offscreen, then composite it through the mask so a
            # hand-drawn boundary is exact rather than guessed at per tile.
            tmp = cairo.ImageSurface(cairo.FORMAT_ARGB32, view_w, view_h)
            tcr = cairo.Context(tmp)
            self._paint_tiles(tcr, cam, view_w, view_h, smooth, anim)
            cr.set_source_surface(tmp, 0, 0)
            cr.mask_surface(mask, 0, 0)
        else:
            self._paint_tiles(cr, cam, view_w, view_h, smooth, anim)

        if holo is not None:
            holo.draw(cr, cam, view_w, view_h)

        if addons is not None:
            # The site's own addon clips: the teleporter characters, fog, the
            # click-triggered one-shots. Drawn after the tiles so they sit on
            # the art, before the boxes so the hover outline stays on top.
            addons.draw(cr, cam, view_w, view_h)

        if objs:
            self._draw_boxes(cr, cam, view_w, view_h, hover,
                             all_boxes=all_boxes)

    def _paint_tiles(self, cr, cam, view_w, view_h, smooth, anim):
        import cairo
        cr.save()
        cr.scale(cam.zoom, cam.zoom)
        cr.translate(-cam.x, -cam.y)
        for tid in self.visible_tiles(cam, view_w, view_h):
            if tid in self.empty:
                continue          # void tile: let the wallpaper show through
            # With a silhouette mask the void is cut globally, so a mostly-void
            # tile can animate too — without one, its frames would repaint the
            # slab the colour key removed.
            animated = anim is not None and (
                self.mask_path_set
                or self.keyed_pct.get(tid, 0) < self.anim_max_backing)
            frame = anim.frame_for(tid, cam.zoom) if animated else None
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

    def _draw_boxes(self, cr, cam, view_w, view_h, hover, all_boxes=False):
        """Only the hovered object is ever drawn.

        Everything else is invisible: this is a wallpaper, not a debug view.
        `all_boxes` is the exception, for auditing against the site — a faint
        outline on every object, opt-in through the `boxes` control command and
        never on by default.
        """
        if all_boxes:
            z = cam.zoom
            cr.save()
            cr.set_line_width(1.0)
            cr.set_source_rgba(1.0, 0.85, 0.2, 0.55)
            for o in self.objects:
                if o["link"] in MARKER_LINKS:
                    continue
                cr.rectangle((o["x1"] - cam.x) * z, (o["y1"] - cam.y) * z,
                             (o["x2"] - o["x1"]) * z, (o["y2"] - o["y1"]) * z)
                cr.stroke()
            cr.restore()
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
            if o.get("link") in MARKER_LINKS:
                continue
            if o["x1"] <= sx <= o["x2"] and o["y1"] <= sy <= o["y2"]:
                if allow is not None and not allow(o):
                    continue
                area = (o["x2"] - o["x1"]) * (o["y2"] - o["y1"])
                if best is None or area < best[0]:
                    best = (area, o)
        return best[1] if best else None


def paint_cover(cr, surf, w, h):
    """Scale an image to cover w x h, centred (like CSS object-fit: cover)."""
    iw, ih = surf.get_width(), surf.get_height()
    scale = max(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    cr.save()
    cr.translate((w - dw) / 2, (h - dh) / 2)
    cr.scale(scale, scale)
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(__import__("cairo").FILTER_GOOD)
    cr.paint()
    cr.restore()


def headless(scene, cam, w, h, out, objs=True):
    import cairo
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    scene.draw(cr, cam, w, h, objs=objs)
    surf.write_to_png(out)
    return out
