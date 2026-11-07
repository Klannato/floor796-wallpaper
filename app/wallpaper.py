#!/usr/bin/env python3
"""floor796 as a real wallpaper: one layer-shell surface per monitor.

layer-shell surfaces are per-output, so a single window can never span two
screens. Instead each monitor gets its own surface, and the shared camera is
offset per monitor so the map stays continuous across the arrangement —

    scene_x_on_monitor_i = base_x + monitor_i.x / zoom

The monitors are read from GDK at runtime (they are not the same as they were
yesterday: the second screen moved from y=554 to y=278), the list is rebuilt on
hotplug, and every geometry value is re-read per paint rather than captured —
a reposition sends no hotplug signal, so anything cached here goes stale.

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
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _set_process_name(name="floor796-wall"):
    """Make the process identifiable in task managers (comm is capped at 15)."""
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(15, name.encode()[:15], 0, 0, 0)   # PR_SET_NAME
    except Exception:
        pass

from scene import Camera, Scene  # noqa: E402


# ── monitor geometry ──────────────────────────────────────────────────────────
# Read, never keep. Re-arranging outputs in the compositor's display settings
# moves a monitor without adding or removing one, and GDK signals only the
# latter — so any geometry captured at build time silently goes stale and half
# the map jumps by the delta. Every consumer below re-reads these.

def mon_geom(mon):
    """Live (x, y, w, h) of one monitor in layout coordinates."""
    g = mon.get_geometry()
    return g.x, g.y, g.width, g.height


def layout_of(display):
    """[(monitor, x, y, w, h)] for every output, read fresh on every call."""
    return [(mon,) + mon_geom(mon)
            for mon in (display.get_monitor(i)
                        for i in range(display.get_n_monitors()))]


def layout_key(layout):
    """Hashable summary of an arrangement — what "the monitors moved" means."""
    return tuple(entry[1:] for entry in layout)


def layout_str(layout):
    parts = " + ".join(f"{w}x{h}@{x},{y}" for _m, x, y, w, h in layout)
    uw = max((x + w for _m, x, y, w, h in layout), default=0)
    uh = max((y + h for _m, x, y, w, h in layout), default=0)
    return f"{parts} (union {uw}x{uh})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoom", type=float, default=0.5)
    ap.add_argument("--scene-x", type=float, default=4900)
    ap.add_argument("--scene-y", type=float, default=3200)
    ap.add_argument("--layer", default="bottom",
                    choices=["background", "bottom", "top"])
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--no-animate", action="store_true")
    ap.add_argument("--background", default="assets/background.jpg",
                    help="desktop image behind the scene (empty to disable)")
    ap.add_argument("--mask", default=None,
                    help="silhouette PNG (white=keep, black=cut)")
    ap.add_argument("--debug-boxes", action="store_true",
                    help="outline every object (auditing against the site)")
    args = ap.parse_args()

    _set_process_name()

    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, Gdk, GLib, GtkLayerShell

    scene = Scene()
    # Logged because the object set silently depends on which changelog is in
    # vendor/: 804 (the stale bundled copy) vs 857 (live). 53 objects become
    # unhoverable and nothing else complains.
    print(f"scene: {len(scene.tiles)} tiles, {len(scene.objects)} objects, "
          f"{scene.width}x{scene.height}", flush=True)
    if args.mask:
        scene.load_mask(args.mask)
    bg = None
    if args.background:
        import gi as _gi
        _gi.require_version("GdkPixbuf", "2.0")
        _gi.require_version("Gdk", "3.0")
        from gi.repository import GdkPixbuf, Gdk as _Gdk
        import cairo as _cairo
        bg_path = args.background
        if not os.path.isabs(bg_path):
            bg_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), bg_path)
        if os.path.exists(bg_path):
            _pix = GdkPixbuf.Pixbuf.new_from_file(bg_path)
            bg = _cairo.ImageSurface(_cairo.FORMAT_ARGB32,
                                     _pix.get_width(), _pix.get_height())
            _cr = _cairo.Context(bg)
            _Gdk.cairo_set_source_pixbuf(_cr, _pix, 0, 0)
            _cr.paint()
            print(f"backdrop: {bg_path} ({_pix.get_width()}x{_pix.get_height()})",
                  flush=True)
        else:
            print(f"backdrop missing: {bg_path}", flush=True)

    anim = holo = addons = None
    if not args.no_animate:
        from addons import Addons
        from anim import AnimSheets
        from holo import Hologram
        anim = AnimSheets()
        holo = Hologram()
        addons = Addons()

    state = {
        "x": args.scene_x, "y": args.scene_y, "zoom": args.zoom,
        "interactive": args.interactive, "hover": None,
        "wins": [], "dirty": False, "drag": None, "press": None,
        "layout": None, "boxes": args.debug_boxes, "addon_sig": (),
    }
    display = Gdk.Display.get_default()

    def cam_for(mx, my):
        """Camera for a monitor whose top-left is at (mx,my) in layout coords."""
        return Camera(state["x"] + mx / state["zoom"],
                      state["y"] + my / state["zoom"],
                      state["zoom"])

    def set_interactive(on):
        import cairo as _c
        state["interactive"] = on
        for win, _mon in state["wins"]:
            if on:
                win.input_shape_combine_region(None)
            else:
                state["hover"] = None
                win.input_shape_combine_region(
                    _c.Region(_c.RectangleInt(0, 0, 0, 0)))
        if not on and state["boxes"]:
            # Leaving interactive mode ends the audit: the overlay must never
            # survive into the wallpaper state, which is chrome-free by design.
            state["boxes"] = False
            print("all boxes: False (interactive off)", flush=True)
        # Offsets are hand-tuned in app/align.py; re-read them whenever the
        # mode changes so a saved alignment applies without a restart.
        refresh_alignment()
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

    def pad_allowed(o):
        """A hologram pad only exists while its own scene is showing."""
        if holo is None:
            return True
        import links
        idx = links.hologram_pad_index(o.get("link"))
        if idx is None:
            return True
        return idx == holo.current_index()

    def refresh_alignment():
        """Re-read the hand-tuned hologram offsets and repaint."""
        got = holo.reload_offsets() if holo is not None else {}
        if scene.reload_mask():
            print("mask reloaded", flush=True)
        holo._cur.clear() if holo is not None else None
        print(f"alignment refreshed: {len(got)} scene offset(s)", flush=True)
        queue()

    def make_window(mon):
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

        def view_size():
            """What the surface actually is right now, not what it was at build."""
            w = area.get_allocated_width()
            h = area.get_allocated_height()
            if w <= 1 or h <= 1:          # not realised yet
                _mx, _my, w, h = mon_geom(mon)
            return w, h

        def on_draw(_w, cr):
            mx, my, _gw, _gh = mon_geom(mon)
            w, h = view_size()
            cam = cam_for(mx, my)
            hover = state["hover"] if state["interactive"] else None
            # The audit overlay is a debugging aid, so it is bound to the
            # interactive state: a wallpaper in wallpaper mode draws no chrome
            # at all, and even in interactive mode the normal case is one box
            # under the cursor, not 857.
            scene.draw(cr, cam, w, h, hover=hover, anim=anim, holo=holo,
                       addons=addons, background=bg,
                       all_boxes=state["boxes"] and state["interactive"])
            return False

        def on_motion(_w, ev):
            if not state["interactive"]:
                return True
            mx, my, _gw, _gh = mon_geom(mon)
            if state["drag"]:
                x0, y0, bx, by = state["drag"]
                state["x"] = bx - (ev.x - x0) / state["zoom"]
                state["y"] = by - (ev.y - y0) / state["zoom"]
                queue()
                return True
            cam = cam_for(mx, my)
            o = scene.object_at(cam, ev.x, ev.y, allow=pad_allowed)
            if (o or {}).get("id") != (state["hover"] or {}).get("id"):
                state["hover"] = o
                queue()
            return True

        def on_press(_w, ev):
            if not state["interactive"] or ev.button != 1:
                return True
            mx, my, _gw, _gh = mon_geom(mon)
            state["drag"] = (ev.x, ev.y, state["x"], state["y"])
            state["press"] = (ev.x, ev.y)
            state["hover"] = scene.object_at(
                cam_for(mx, my), ev.x, ev.y, allow=pad_allowed)
            return True

        def on_release(_w, ev):
            if ev.button != 1:
                return True
            state["drag"] = None
            p0 = state.get("press")
            state["press"] = None
            o = state.get("hover")
            if p0 and o and o.get("link") and (
                    abs(ev.x - p0[0]) + abs(ev.y - p0[1]) <= 4):
                import links
                # A click inside a multi-clip addon region (the teleporter)
                # advances to the next character, like the site's pad list.
                if addons is not None and addons.click(
                        cam_for(*mon_geom(mon)[:2]), ev.x, ev.y):
                    queue()
                links.resolve(o["link"], holo=holo, addons=addons,
                              title=o.get("title", ""))
                queue()
            return True

        def on_scroll(_w, ev):
            if not state["interactive"]:
                return True
            mx, my, _gw, _gh = mon_geom(mon)
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
        for win, _mon in state["wins"]:
            win.destroy()
        state["wins"] = []
        layout = layout_of(display)
        for mon, _mx, _my, _w, _h in layout:
            state["wins"].append((make_window(mon), mon))
        state["layout"] = layout_key(layout)
        print(f"{len(layout)} surface(s), layout {layout_str(layout)} "
              f"at zoom {state['zoom']}, "
              f"scene origin ({state['x']:.0f},{state['y']:.0f})", flush=True)
        set_interactive(state["interactive"])

    def check_layout():
        """Catch a rearranged arrangement that raised no add/remove signal.

        Surfaces are re-anchored by the compositor on its own; only the camera
        offsets and viewport sizes are derived here, and they are now read live
        — so a move needs a repaint and a log line, not a rebuild.
        """
        layout = layout_of(display)
        key = layout_key(layout)
        if key == state["layout"]:
            return
        old, state["layout"] = state["layout"], key
        print(f"layout changed: {layout_str(layout)}", flush=True)
        for (win, mon), was in zip(state["wins"], old or ()):
            g = mon_geom(mon)
            if g != was:
                print(f"  {(mon.get_model() or 'output')}: "
                      f"{was[2]}x{was[3]}@{was[0]},{was[1]}"
                      f" → {g[2]}x{g[3]}@{g[0]},{g[1]}", flush=True)
        queue()

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
            elif cmd == "refresh":
                refresh_alignment()
            elif cmd == "boxes":
                state["boxes"] = not state["boxes"]
                note = "" if state["interactive"] else \
                    " (only visible in interactive mode — Super+i)"
                print(f"all boxes: {state['boxes']}{note}", flush=True)
                queue()
            elif cmd == "quit":
                Gtk.main_quit()
            return True

        GLib.io_add_watch(ctl.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_ctl)
        print(f"control socket: {ctl_path}", flush=True)
    except OSError as e:
        print(f"control socket unavailable: {e}", flush=True)

    def tick():
        if addons is not None and addons.items:
            # Repaint only when an addon frame actually changed: queuing
            # unconditionally at 10 Hz costs a quarter of a core on a scene
            # where nothing moved.
            sig = addons.signature(time.monotonic())
            if sig != state["addon_sig"]:
                state["addon_sig"] = sig
                queue()
        if anim is not None and anim.live:
            queue()
            # Release frame mappings for tiles off screen. Safe here: this runs
            # between paints, not inside one. Every monitor contributes, since
            # each has its own camera offset.
            vis = set()
            for _win, mon in state["wins"]:
                mx, my, w, h = mon_geom(mon)
                vis.update(scene.visible_tiles(cam_for(mx, my), w, h))
            anim.prune(vis)
        check_layout()
        return True

    GLib.timeout_add(100, tick)
    Gtk.main()


if __name__ == "__main__":
    main()
