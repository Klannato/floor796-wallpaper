#!/usr/bin/env python3
"""Hand-align each hologram scene inside the teleporter room.

Drag the projection with the mouse, or nudge with the arrow keys. Offsets are
per scene and saved to config/holo_offsets.json, which the viewer and the
wallpaper both read.

    /usr/bin/python3 app/align.py

Controls
    drag                 move the projection
    arrows               nudge 1 px        (shift = 10 px)
    Tab / Shift+Tab      next / previous scene
    1..6                 jump to scene
    [ / ]                step back / forward one frame (to check the edges)
    space                play / pause the loop
    0                    reset this scene's offset
    s                    save all offsets
    r                    reload the backdrop (drops tile caches)
    q / Esc              quit
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scene import Camera, Scene  # noqa: E402
from holo import Hologram, HOLO_X, HOLO_Y, SCENE_W, SCENE_H, FPS, N_FRAMES  # noqa: E402


def run():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gtk, Gdk, GLib

    scene = Scene()
    holo = Hologram()
    names = holo.scenes()
    if not names:
        sys.exit("no hologram scenes in vendor/holo — run tools/rip_hologram.py")

    # Frame the room: hologram occupies (HOLO_X, HOLO_Y, SCENE_W, SCENE_H)
    state = {
        "i": 0, "size": (1200, 760), "drag": None, "pan": None, "frame": 0,
        "playing": True, "dirty": False,
        "zoom": 0.85,
        "cam": Camera(HOLO_X - 120, HOLO_Y - 90, 0.85),
    }

    win = Gtk.Window(title="hologram alignment")
    win.set_default_size(*state["size"])
    area = Gtk.DrawingArea()
    win.add(area)

    def cur():
        return names[state["i"] % len(names)]

    def redraw():
        if state["dirty"]:
            return
        state["dirty"] = True
        GLib.idle_add(_flush)

    def _flush():
        state["dirty"] = False
        area.queue_draw()
        return False

    def on_draw(_w, cr):
        w, h = state["size"]
        scene.draw(cr, state["cam"], w, h, objs=False)
        holo.preview_name = cur()
        holo.preview_frame = state["frame"] if not state["playing"] else None
        holo.draw(cr, state["cam"], w, h)
        hud(cr, w, h)
        return False

    def hud(cr, w, h):
        dx, dy = holo.offset_for(cur())
        mode = "playing" if state["playing"] else f"frame {state['frame']}"
        label = (f"{state['i'] + 1}/{len(names)}  {cur()[:-4]}   "
                 f"offset {dx:+d},{dy:+d}   {mode}   zoom {state['cam'].zoom:.2f}")
        hint = ("drag/arrows align · wheel zoom · right-drag pan · "
                "Tab scene · [ ] frame · space play · 0 reset · s save · q quit")
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(13)
        e1 = cr.text_extents(label)
        cr.set_font_size(11)
        e2 = cr.text_extents(hint)
        bw = max(e1[2], e2[2]) + 24
        cr.set_source_rgba(0, 0, 0, 0.65)
        cr.rectangle(14, 14, bw, 52)
        cr.fill()
        cr.set_source_rgba(0.9, 0.9, 2.0, 1)
        cr.set_font_size(13)
        cr.move_to(26, 36)
        cr.show_text(label)
        cr.set_source_rgba(0.65, 0.65, 0.7, 1)
        cr.set_font_size(11)
        cr.move_to(26, 54)
        cr.show_text(hint)

    def bump(dx, dy):
        name = cur()
        ox, oy = holo.offset_for(name)
        holo.offsets[name] = (ox + dx, oy + dy)
        redraw()

    def on_press(_w, ev):
        if ev.button == 1:
            state["drag"] = (ev.x, ev.y, *holo.offset_for(cur()),
                             state["cam"].zoom)
        elif ev.button == 3:
            state["pan"] = (ev.x, ev.y, state["cam"].x, state["cam"].y)
        return True

    def on_release(_w, ev):
        if ev.button == 1:
            state["drag"] = None
        elif ev.button == 3:
            state["pan"] = None
        return True

    def on_motion(_w, ev):
        pan = state["pan"]
        if pan:
            x0, y0, cx, cy = pan
            cam = state["cam"]
            cam.x = cx - (ev.x - x0) / cam.zoom
            cam.y = cy - (ev.y - y0) / cam.zoom
            redraw()
            return True
        d = state["drag"]
        if not d:
            return True
        x0, y0, ox, oy, z = d
        holo.offsets[cur()] = (int(ox + (ev.x - x0) / z),
                               int(oy + (ev.y - y0) / z))
        redraw()
        return True

    def zoom_at(px, py, factor):
        cam = state["cam"]
        wx = cam.x + px / cam.zoom
        wy = cam.y + py / cam.zoom
        cam.zoom = min(max(cam.zoom * factor, 0.2), 4.0)
        cam.x = wx - px / cam.zoom
        cam.y = wy - py / cam.zoom
        redraw()

    def on_scroll(_w, ev):
        from gi.repository import Gdk as G
        factor = 1.15 if ev.direction == G.ScrollDirection.UP else 1 / 1.15
        zoom_at(ev.x, ev.y, factor)
        return True

    def on_size(_w, alloc):
        state["size"] = (alloc.width, alloc.height)

    def on_key(_w, ev):
        from gi.repository import Gdk as G
        k, st = ev.keyval, ev.state
        step = 10 if st & G.ModifierType.SHIFT_MASK else 1
        if k in (G.KEY_Left,):
            bump(-step, 0)
        elif k in (G.KEY_Right,):
            bump(step, 0)
        elif k in (G.KEY_Up,):
            bump(0, -step)
        elif k in (G.KEY_Down,):
            bump(0, step)
        elif k == G.KEY_Tab:
            state["i"] = (state["i"] + (1 if not (st & G.ModifierType.SHIFT_MASK)
                                        else -1)) % len(names)
            state["frame"] = 0
            redraw()
        elif G.KEY_1 <= k <= G.KEY_6:
            idx = k - G.KEY_1
            if idx < len(names):
                state["i"] = idx
                state["frame"] = 0
                redraw()
        elif k in (G.KEY_bracketleft,):
            state["playing"] = False
            state["frame"] = (state["frame"] - 1) % N_FRAMES
            redraw()
        elif k in (G.KEY_bracketright,):
            state["playing"] = False
            state["frame"] = (state["frame"] + 1) % N_FRAMES
            redraw()
        elif k in (G.KEY_plus, G.KEY_equal):
            zoom_at(state["size"][0] / 2, state["size"][1] / 2, 1.2)
        elif k == G.KEY_minus:
            zoom_at(state["size"][0] / 2, state["size"][1] / 2, 1 / 1.2)
        elif k == G.KEY_space:
            state["playing"] = not state["playing"]
            redraw()
        elif k == G.KEY_0:
            holo.offsets[cur()] = (0, 0)
            redraw()
        elif k == G.KEY_s:
            holo.save_offsets()
            print("saved → config/holo_offsets.json")
            for n in names:
                print(f"   {n[:-4]}: {holo.offset_for(n)}")
            redraw()
        elif k == G.KEY_r:
            scene._surfaces.clear()
            scene._surface_order.clear()
            redraw()
        elif k in (G.KEY_q, G.KEY_Escape):
            Gtk.main_quit()
        else:
            return False
        return True

    def tick():
        if state["playing"]:
            state["frame"] = int(time.time() * FPS) % N_FRAMES
            redraw()
        return True

    area.connect("draw", on_draw)
    area.connect("size-allocate", on_size)
    area.connect("button-press-event", on_press)
    area.connect("button-release-event", on_release)
    area.connect("motion-notify-event", on_motion)
    area.connect("scroll-event", on_scroll)
    area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                    Gdk.EventMask.BUTTON_RELEASE_MASK |
                    Gdk.EventMask.POINTER_MOTION_MASK |
                    Gdk.EventMask.SCROLL_MASK)
    win.connect("key-press-event", on_key)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    area.grab_focus()
    GLib.timeout_add(80, tick)
    print(f"aligning {len(names)} scenes at map ({HOLO_X},{HOLO_Y}) "
          f"{SCENE_W}x{SCENE_H}; saved offsets: "
          f"{json.dumps({k: list(v) for k, v in holo.offsets.items()})}")
    Gtk.main()


if __name__ == "__main__":
    run()
