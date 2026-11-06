#!/usr/bin/env python3
"""floor796 as a real wallpaper: one layer-shell surface per monitor.

layer-shell surfaces are per-output, so a single window can never span two
screens. Instead each monitor gets its own surface, and the shared camera is
offset per monitor so the map stays continuous across the arrangement —

    scene_x_on_monitor_i = base_x + monitor_i.x / zoom

The monitors are read from GDK at runtime (they are not the same as they were
yesterday: the second screen moved from y=554 to y=278), and the list is rebuilt
on hotplug.

    /usr/bin/python3 app/wallpaper.py                 # wallpaper, no input
    /usr/bin/python3 app/wallpaper.py --interactive    # hover + click enabled
    python3 tools/ctl.py toggle                        # switch at runtime

Click-through is the default: an empty input region means the cursor falls
through to the desktop. Turn interactivity on with the control socket
(Super+i via tools/install_shortcut.py) to get hover panels and links.
"""

import argparse
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scene import Camera, Scene  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoom", type=float, default=0.5)
    ap.add_argument("--scene-x", type=float, default=4900)
    ap.add_argument("--scene-y", type=float, default=3200)
    ap.add_argument("--layer", default="bottom",
                    choices=["background", "bottom", "top"])
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--no-animate", action="store_true")
    args = ap.parse_args()

    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, Gdk, GLib, GtkLayerShell

    scene = Scene()
    anim = holo = None
    if not args.no_animate:
        from anim import AnimSheets
        from holo import Hologram
        anim = AnimSheets()
        holo = Hologram()

    state = {
        "x": args.scene_x, "y": args.scene_y, "zoom": args.zoom,
        "interactive": args.interactive, "hover": None,
        "wins": [], "dirty": False, "drag": None, "press": None,
    }
    display = Gdk.Display.get_default()

    def monitors():
        out = []
        for i in range(display.get_n_monitors()):
            m = display.get_monitor(i)
            g = m.get_geometry()
            out.append((m, g.x, g.y, g.width, g.height))
        return out

    def cam_for(mx, my):
        """Camera for a monitor whose top-left is at (mx,my) in layout coords."""
        return Camera(state["x"] + mx / state["zoom"],
                      state["y"] + my / state["zoom"],
                      state["zoom"])

    def set_interactive(on):
        import cairo as _c
        state["interactive"] = on
        for win, _mon, _mx, _my, _w, _h in state["wins"]:
            if on:
                win.input_shape_combine_region(None)
            else:
                state["hover"] = None
                win.input_shape_combine_region(
                    _c.Region(_c.RectangleInt(0, 0, 0, 0)))
        print(f"interactive: {on}", flush=True)
        queue()

    def queue():
        if state["dirty"]:
            return
        state["dirty"] = True
        GLib.idle_add(_flush)

    def _flush():
        state["dirty"] = False
        for win, *_ in state["wins"]:
            area = win.get_child()
            if area is not None:
                area.queue_draw()
        return False

    def make_window(mon, mx, my, w, h):
        win = Gtk.Window()
        win.set_app_paintable(True)
        vis = win.get_screen().get_rgba_visual()
        if vis:
            win.set_visual(vis)
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "floor796-wallpaper")
        GtkLayerShell.set_monitor(win, mon)
        GtkLayerShell.set_layer(win, {
            "background": GtkLayerShell.Layer.BACKGROUND,
            "bottom": GtkLayerShell.Layer.BOTTOM,
            "top": GtkLayerShell.Layer.TOP}[args.layer])
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(win, edge, True)
        GtkLayerShell.set_exclusive_zone(win, -1)
        GtkLayerShell.set_keyboard_interactivity(
            win, GtkLayerShell.KeyboardMode.NONE)

        area = Gtk.DrawingArea()
        win.add(area)

        def on_draw(_w, cr, mx=mx, my=my, w=w, h=h):
            cam = cam_for(mx, my)
            hover = state["hover"] if state["interactive"] else None
            scene.draw(cr, cam, w, h, hover=hover, anim=anim, holo=holo)
            return False

        def on_motion(_w, ev, mx=mx, my=my):
            if not state["interactive"]:
                return True
            if state["drag"]:
                x0, y0, bx, by = state["drag"]
                state["x"] = bx - (ev.x - x0) / state["zoom"]
                state["y"] = by - (ev.y - y0) / state["zoom"]
                queue()
                return True
            cam = cam_for(mx, my)
            o = scene.object_at(cam, ev.x, ev.y)
            if (o or {}).get("id") != (state["hover"] or {}).get("id"):
                state["hover"] = o
                queue()
            return True

        def on_press(_w, ev, mx=mx, my=my):
            if not state["interactive"] or ev.button != 1:
                return True
            state["drag"] = (ev.x, ev.y, state["x"], state["y"])
            state["press"] = (ev.x, ev.y)
            state["hover"] = scene.object_at(cam_for(mx, my), ev.x, ev.y)
            return True

        def on_release(_w, ev, mx=mx, my=my):
            if ev.button != 1:
                return True
            state["drag"] = None
            p0 = state.get("press")
            state["press"] = None
            o = state.get("hover")
            if p0 and o and o.get("link") and (
                    abs(ev.x - p0[0]) + abs(ev.y - p0[1]) <= 4):
                import subprocess
                subprocess.Popen(["xdg-open", o["link"]],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                print(f"opened {o['link']}", flush=True)
            return True

        def on_scroll(_w, ev, mx=mx, my=my):
            if not state["interactive"]:
                return True
            g = ev.direction
            factor = (1.15 if g == Gdk.ScrollDirection.UP
                      else 1 / 1.15)
            # keep the point under the cursor fixed
            sx = state["x"] + (mx + ev.x) / state["zoom"]
            sy = state["y"] + (my + ev.y) / state["zoom"]
            z = min(max(state["zoom"] * factor, 0.12), 3.0)
            state["zoom"] = z
            state["x"] = sx - (mx + ev.x) / z
            state["y"] = sy - (my + ev.y) / z
            queue()
            return True

        area.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.SCROLL_MASK)
        area.connect("draw", on_draw)
        area.connect("motion-notify-event", on_motion)
        area.connect("button-press-event", on_press)
        area.connect("button-release-event", on_release)
        area.connect("scroll-event", on_scroll)
        win.show_all()
        return win

    def rebuild(*_):
        for win, *_ in state["wins"]:
            win.destroy()
        state["wins"] = []
        mons = monitors()
        for mon, mx, my, w, h in mons:
            win = make_window(mon, mx, my, w, h)
            state["wins"].append((win, mon, mx, my, w, h))
        xs = [m[1] + m[3] for m in mons]
        ys = [m[2] + m[4] for m in mons]
        print(f"{len(mons)} surface(s), layout "
              f"{max(xs)}x{max(ys)} at zoom {state['zoom']}, "
              f"scene origin ({state['x']:.0f},{state['y']:.0f})", flush=True)
        set_interactive(state["interactive"])

    display.connect("monitor-added", rebuild)
    display.connect("monitor-removed", rebuild)
    rebuild()

    # ── control socket ─────────────────────────────────────────────────────
    ctl_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                            "floor796.sock")
    try:
        if os.path.exists(ctl_path):
            os.unlink(ctl_path)
        ctl = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        ctl.bind(ctl_path)
        ctl.setblocking(False)

        def on_ctl(_fd, _cond):
            try:
                cmd = ctl.recvfrom(128)[0].decode().strip().lower()
            except OSError:
                return True
            print(f"ctl: {cmd}", flush=True)
            if cmd == "toggle":
                set_interactive(not state["interactive"])
            elif cmd == "interactive":
                set_interactive(True)
            elif cmd == "wallpaper":
                set_interactive(False)
            elif cmd == "quit":
                Gtk.main_quit()
            return True

        GLib.io_add_watch(ctl.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_ctl)
        print(f"control socket: {ctl_path}", flush=True)
    except OSError as e:
        print(f"control socket unavailable: {e}", flush=True)

    def tick():
        if anim is not None and anim.live:
            queue()
        return True

    GLib.timeout_add(100, tick)
    Gtk.main()


if __name__ == "__main__":
    main()
