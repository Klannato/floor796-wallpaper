#!/usr/bin/env python3
"""Interactive whole-scene viewer / wallpaper for floor796.

The entire 10168x8940 map is pannable and zoomable; object boxes from
changelog.json are drawn on top. Run with the SYSTEM python (needs gi):

    /usr/bin/python3 app/viewer.py                     # windowed explorer
    /usr/bin/python3 app/viewer.py --fullscreen
    /usr/bin/python3 app/viewer.py --layer bottom      # wallpaper mode
    /usr/bin/python3 app/viewer.py --shot 4900,3200,0.5 --out shot.png

Controls: drag = pan, wheel = zoom at cursor, arrows/WASD = pan,
+/- = zoom, 0 = fit whole map, f = fullscreen, q/Esc = quit.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scene import Camera, Scene, headless, SPACING_W, SPACING_H  # noqa: E402


def run(args):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gtk, Gdk, GLib

    scene = Scene()
    cam = Camera(*[float(v) for v in args.camera.split(",")]) \
        if args.camera else Camera()
    state = {"hover": None, "drag": None, "size": (args.width, args.height),
             "dirty": False, "anim": None, "holo": None}
    if not args.no_animate:
        from anim import AnimSheets
        from holo import Hologram
        state["anim"] = AnimSheets()
        state["holo"] = Hologram()

    win = Gtk.Window()
    win.set_title("floor796")
    win.set_default_size(args.width, args.height)
    win.set_app_paintable(True)
    vis = win.get_screen().get_rgba_visual()
    if vis:
        win.set_visual(vis)

    area = Gtk.DrawingArea()
    win.add(area)

    if args.layer:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "floor796-viewer")
        GtkLayerShell.set_layer(win, {
            "background": GtkLayerShell.Layer.BACKGROUND,
            "bottom": GtkLayerShell.Layer.BOTTOM,
            "top": GtkLayerShell.Layer.TOP}[args.layer])
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(win, edge, True)
        GtkLayerShell.set_exclusive_zone(win, -1)
        GtkLayerShell.set_keyboard_interactivity(win, GtkLayerShell.KeyboardMode.NONE)
        win.set_accept_focus(False)
    elif args.fullscreen:
        win.fullscreen()

    def on_draw(_w, cr):
        w, h = state["size"]
        scene.draw(cr, cam, w, h, hover=state["hover"], smooth=args.smooth,
                   anim=state["anim"], holo=state["holo"])
        hud(cr, w, h, cam, scene)
        return False

    def hud(cr, w, h, cam, scene):
        txt = (f"{cam.x:.0f},{cam.y:.0f}  zoom {cam.zoom:.2f}  "
               f"map {scene.width}x{scene.height}  "
               f"[drag pan · wheel zoom · 0 fit · f fullscreen · q quit]")
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(12)
        ext = cr.text_extents(txt)
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.rectangle(12, h - ext[3] - 22, ext[2] + 20, ext[3] + 14)
        cr.fill()
        cr.set_source_rgba(0.85, 0.85, 0.85, 1)
        cr.move_to(22, h - 14)
        cr.show_text(txt)

    def tick():
        """Prefetch neighbour sheets, then repaint animated tiles."""
        pool = state["anim"]
        if pool is None:
            return True
        if pool.live or state["holo"] is not None:
            request_redraw()
        return True

    def request_redraw():
        if state["dirty"]:
            return
        state["dirty"] = True
        GLib.idle_add(_flush)

    def _flush():
        state["dirty"] = False
        area.queue_draw()
        return False

    def on_size(_w, alloc):
        state["size"] = (alloc.width, alloc.height)
        cam.clamp(scene.width, scene.height, alloc.width, alloc.height)

    def on_press(_w, ev):
        if ev.button == 1:
            state["drag"] = (ev.x, ev.y, cam.x, cam.y)
        return True

    def on_release(_w, ev):
        state["drag"] = None
        return True

    def on_motion(_w, ev):
        if state["drag"]:
            x0, y0, cx, cy = state["drag"]
            cam.x = cx - (ev.x - x0) / cam.zoom
            cam.y = cy - (ev.y - y0) / cam.zoom
            cam.clamp(scene.width, scene.height, *state["size"])
            request_redraw()
        else:
            o = scene.object_at(cam, ev.x, ev.y)
            if (o or {}).get("id") != (state["hover"] or {}).get("id"):
                state["hover"] = o
                request_redraw()
        return True

    def on_scroll(_w, ev):
        factor = 1.15 if ev.direction == Gdk.ScrollDirection.UP else 1 / 1.15
        zoom_at(ev.x, ev.y, factor)
        return True

    def zoom_at(px, py, factor):
        before = cam.to_scene(px, py)
        cam.zoom = min(max(cam.zoom * factor, 0.12), 3.0)
        after = cam.to_scene(px, py)
        cam.x += before[0] - after[0]
        cam.y += before[1] - after[1]
        cam.clamp(scene.width, scene.height, *state["size"])
        request_redraw()

    def on_key(_w, ev):
        from gi.repository import Gdk as G
        step = 180 / cam.zoom if cam.zoom < 1 else 180
        k = ev.keyval
        moved = True
        if k in (G.KEY_Left, G.KEY_a):
            cam.x -= step
        elif k in (G.KEY_Right, G.KEY_d):
            cam.x += step
        elif k in (G.KEY_Up, G.KEY_w):
            cam.y -= step
        elif k in (G.KEY_Down, G.KEY_s):
            cam.y += step
        elif k in (G.KEY_plus, G.KEY_equal):
            zoom_at(state["size"][0] / 2, state["size"][1] / 2, 1.2)
            return True
        elif k == G.KEY_minus:
            zoom_at(state["size"][0] / 2, state["size"][1] / 2, 1 / 1.2)
            return True
        elif k == G.KEY_0:
            cam.zoom = min(state["size"][0] / scene.width,
                           state["size"][1] / scene.height)
            cam.x = cam.y = 0
        elif k == G.KEY_f:
            if win.get_window() and win.get_window().get_state() & G.WindowState.FULLSCREEN:
                win.unfullscreen()
            else:
                win.fullscreen()
            return True
        elif k in (G.KEY_q, G.KEY_Escape):
            Gtk.main_quit()
            return True
        else:
            moved = False
        if moved:
            cam.clamp(scene.width, scene.height, *state["size"])
            request_redraw()
        return True

    area.set_can_focus(True)
    area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                    Gdk.EventMask.BUTTON_RELEASE_MASK |
                    Gdk.EventMask.POINTER_MOTION_MASK |
                    Gdk.EventMask.SCROLL_MASK)
    area.connect("draw", on_draw)
    area.connect("size-allocate", on_size)
    area.connect("button-press-event", on_press)
    area.connect("button-release-event", on_release)
    area.connect("motion-notify-event", on_motion)
    area.connect("scroll-event", on_scroll)
    win.connect("key-press-event", on_key)
    win.connect("destroy", Gtk.main_quit)

    win.show_all()
    GLib.timeout_add(80, tick)
    area.grab_focus()
    print(f"scene {scene.width}x{scene.height}, {len(scene.objects)} objects, "
          f"{len(scene.tiles)} tiles — {cam}")
    Gtk.main()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", help="x,y,zoom")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--layer", choices=["background", "bottom", "top"],
                    help="map as a layer-shell wallpaper instead of a window")
    ap.add_argument("--shot", metavar="x,y,zoom",
                    help="headless render at this camera")
    ap.add_argument("--out", default="shot.png")
    ap.add_argument("--no-boxes", action="store_true")
    ap.add_argument("--smooth", action="store_true",
                    help="bilinear tile scaling (blurry — off by default)")
    ap.add_argument("--no-animate", action="store_true",
                    help="static tiles only, no mp4 playback")
    ap.add_argument("--bench", type=int, metavar="N",
                    help="time N headless frames at --shot's camera and exit")
    args = ap.parse_args()

    if args.shot:
        scene = Scene()
        cam = Camera(*[float(v) for v in args.shot.split(",")])
        if args.bench:
            import time
            import cairo
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                      args.width, args.height)
            cr = cairo.Context(surf)
            for smooth in ((True, False) if not args.smooth else (True,)):
                t0 = time.perf_counter()
                for _ in range(args.bench):
                    scene.draw(cr, cam, args.width, args.height,
                               objs=not args.no_boxes, smooth=smooth)
                dt = (time.perf_counter() - t0) / args.bench * 1000
                label = "bilinear" if smooth else "nearest "
                print(f"{label}: {dt:6.1f} ms/frame  "
                      f"({1000/dt:5.1f} fps)  {args.width}x{args.height} @ {cam.zoom:g}x")
            return
        headless(scene, cam, args.width, args.height, args.out,
                 objs=not args.no_boxes)
        print(f"wrote {args.out} ({args.width}x{args.height}) at {cam}")
        return

    run(args)


if __name__ == "__main__":
    main()
