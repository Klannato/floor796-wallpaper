#!/usr/bin/env python3
"""floor796 wallpaper overlay — prototype.

A GTK3 + gtk-layer-shell window that shows a region of the floor796 scene and
draws the interactive object boxes on top of it. Two modes:

  --headless out.png   render the same drawing to a PNG (no compositor needed)
  (default)            map a real layer-surface window on the current output

Run it with the SYSTEM python — the Hermes venv is 3.14 and has no gi:

    /usr/bin/python3 app/overlay.py --headless verify/overlay.png
    /usr/bin/python3 app/overlay.py --zoom 0.5
"""

import argparse
import json
import os
import sys

import cairo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPACING_W, SPACING_H = 1016, 812
TILE_W, TILE_H = 1024, 820

# Default scene origin: the busiest area of the map, roughly the teleporter room.
DEFAULT_SX, DEFAULT_SY = 4900, 3200


# ── scene data ──────────────────────────────────────────────────────────────

def load_json(name):
    with open(os.path.join(ROOT, "vendor", name)) as f:
        return json.load(f)


def tile_positions(matrix):
    return {t["id"]: (r, c)
            for r, row in enumerate(matrix["mat"])
            for c, t in enumerate(row)
            if isinstance(t, dict)}


def objects(matrix, changelog):
    """[{id,title,date,link,x1,y1,x2,y2}] in absolute scene pixels."""
    pos = tile_positions(matrix)
    out = []
    for o in changelog:
        verts = []
        for part in (o.get("p") or "").split(";"):
            f = part.split(",")
            if len(f) < 3:
                continue
            try:
                ly, lx = int(f[1]), int(f[2])   # Y first!
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


class View:
    """Scene → window transform."""

    def __init__(self, sx, sy, zoom, width, height):
        self.sx, self.sy, self.zoom = sx, sy, zoom
        self.w, self.h = width, height

    def rect(self, x1, y1, x2, y2):
        z = self.zoom
        return ((x1 - self.sx) * z, (y1 - self.sy) * z,
                (x2 - x1) * z, (y2 - y1) * z)

    def visible(self, o):
        return not (o["x2"] < self.sx or o["x1"] > self.sx + self.w / self.zoom
                    or o["y2"] < self.sy or o["y1"] > self.sy + self.h / self.zoom)


# ── drawing ─────────────────────────────────────────────────────────────────

def draw(cr, view, scene_surface, objs, hover=None, show_scene=True):
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0 if not show_scene else 1)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)

    if show_scene and scene_surface is not None:
        cr.save()
        cr.scale(view.zoom, view.zoom)
        cr.translate(-view.sx, -view.sy)
        cr.set_source_surface(scene_surface, 0, 0)
        cr.paint()
        cr.restore()

    for o in objs:
        if not view.visible(o):
            continue
        x, y, w, h = view.rect(o["x1"], o["y1"], o["x2"], o["y2"])
        is_hover = hover is not None and o["id"] == hover["id"]
        if is_hover:
            cr.set_source_rgba(1.0, 0.85, 0.2, 0.18)
            cr.rectangle(x, y, w, h)
            cr.fill()
            cr.set_source_rgba(1.0, 0.85, 0.2, 1.0)
            cr.set_line_width(3)
        else:
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.22)
            cr.set_line_width(1)
        cr.rectangle(x, y, w, h)
        cr.stroke()

    if hover:
        draw_panel(cr, view, hover)


def draw_panel(cr, view, o):
    pad, line_h = 12, 18
    lines = [o["title"] or f"object {o['id']}"]
    if o["date"]:
        lines.append(o["date"])
    if o["link"]:
        lines.append(o["link"][:70])

    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(13)
    width = max(cr.text_extents(t)[2] for t in lines) + pad * 2
    height = line_h * len(lines) + pad * 2

    x, y = 24, 24
    cr.set_source_rgba(0.05, 0.05, 0.07, 0.88)
    cr.rectangle(x, y, width, height)
    cr.fill_preserve()
    cr.set_source_rgba(1.0, 0.85, 0.2, 0.9)
    cr.set_line_width(1.5)
    cr.stroke()

    cr.set_source_rgba(1, 1, 1, 1)
    for i, text in enumerate(lines):
        cr.move_to(x + pad, y + pad + line_h * (i + 0.8))
        cr.show_text(text)


def load_scene_surface(still_path):
    """Cairo surface from the composited still (1 scene px = 1 surface px)."""
    if not still_path or not os.path.exists(still_path):
        return None
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    pix = GdkPixbuf.Pixbuf.new_from_file(still_path)
    w, h = pix.get_width(), pix.get_height()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    import gi as _gi
    _gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
    cr.paint()
    return surf


# ── headless render ─────────────────────────────────────────────────────────

def headless(args, view, scene, objs):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, view.w, view.h)
    cr = cairo.Context(surf)
    draw(cr, view, scene, objs, hover=None, show_scene=not args.transparent)
    surf.write_to_png(args.headless)
    print(f"wrote {args.headless} ({view.w}x{view.h}, "
          f"{sum(1 for o in objs if view.visible(o))} objects visible)")


# ── layer shell window ──────────────────────────────────────────────────────

def run_window(args, view, scene, objs):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, Gdk, GtkLayerShell

    win = Gtk.Window()
    win.set_app_paintable(True)
    screen = win.get_screen()
    visual = screen.get_rgba_visual()
    if visual is None:
        sys.exit("no RGBA visual — cannot draw a transparent overlay")
    win.set_visual(visual)

    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, "floor796-wallpaper")
    layer = {"background": GtkLayerShell.Layer.BACKGROUND,
             "bottom": GtkLayerShell.Layer.BOTTOM,
             "top": GtkLayerShell.Layer.TOP}[args.layer]
    GtkLayerShell.set_layer(win, layer)
    GtkLayerShell.set_exclusive_zone(win, -1)
    if args.windowed:
        # Small anchored probe: only top+right anchors, natural size + margins.
        GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, 60)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, 60)
        win.set_size_request(view.w, view.h)
    else:
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(win, edge, True)

    state = {"hover": None, "last": None}

    def pick(x, y):
        sx = x / view.zoom + view.sx
        sy = y / view.zoom + view.sy
        best = None
        for o in objs:
            if o["x1"] <= sx <= o["x2"] and o["y1"] <= sy <= o["y2"]:
                area = (o["x2"] - o["x1"]) * (o["y2"] - o["y1"])
                if best is None or area < best[0]:
                    best = (area, o)
        return best[1] if best else None

    def on_draw(_w, cr):
        draw(cr, view, scene, objs, hover=state["hover"],
             show_scene=not args.transparent)
        return False

    def on_motion(_w, ev):
        o = pick(ev.x, ev.y)
        if (o or {}).get("id") != (state["hover"] or {}).get("id"):
            state["hover"] = o
            win.queue_draw()
        return False

    win.connect("draw", on_draw)
    win.connect("motion-notify-event", on_motion)
    win.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    if args.click_through:
        # Empty input region = every click falls through to whatever is below.
        # Prototype-grade: GTK3's input-shape API is deprecated and its Wayland
        # behaviour must be verified by hand before relying on it.
        empty = cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
        win.input_shape_combine_region(empty)
        print("click-through requested (empty input region)")
        win.set_accept_focus(False)

    print(f"mapped {args.layer} layer surface, {view.w}x{view.h} at zoom "
          f"{view.zoom}, scene origin ({view.sx},{view.sy})")
    Gtk.main()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--still", default=os.path.join(ROOT, "verify", "still_clean.png"))
    ap.add_argument("--zoom", type=float, default=0.5)
    ap.add_argument("--scene-x", type=int, default=DEFAULT_SX)
    ap.add_argument("--scene-y", type=int, default=DEFAULT_SY)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--layer", default="bottom",
                    choices=["background", "bottom", "top"])
    ap.add_argument("--transparent", action="store_true",
                    help="draw boxes only, no scene image (matches the real "
                         "overlay, which sits above mpvpaper)")
    ap.add_argument("--click-through", action="store_true")
    ap.add_argument("--windowed", action="store_true",
                    help="small anchored probe window instead of full-screen")
    ap.add_argument("--headless", metavar="PNG")
    args = ap.parse_args()

    matrix = load_json("matrix.json")
    objs = objects(matrix, load_json("changelog.json"))
    view = View(args.scene_x, args.scene_y, args.zoom, args.width, args.height)

    if args.headless:
        # cairo-only path: no gi needed
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, view.w, view.h)
        cr = cairo.Context(surf)
        draw(cr, view, load_scene_surface(args.still), objs,
             show_scene=not args.transparent)
        surf.write_to_png(args.headless)
        print(f"wrote {args.headless} ({view.w}x{view.h}, "
              f"{sum(1 for o in objs if view.visible(o))} visible objects)")
        return

    run_window(args, view, load_scene_surface(args.still), objs)


if __name__ == "__main__":
    main()
