#!/usr/bin/env python3
"""One interactive page in a GTK4 + WebKit 6 window.

A separate process on purpose: the wallpaper is GTK3 and WebKit 6 is a GTK4
namespace, and a process can load only one GTK. `app/pages.py` routes pages that
genuinely need a JS engine here — a canvas game, a quest panel, the synth — which
is still an order of magnitude lighter than a browser with tabs and extensions.

    app/webview.py <url> [title] [width height]

Escape closes the window.
"""

import hashlib
import sys

import gi

URL = sys.argv[1] if len(sys.argv) > 1 else "about:blank"
TITLE = sys.argv[2] if len(sys.argv) > 2 else "floor796"
try:
    W, H = int(sys.argv[3]), int(sys.argv[4])
except (IndexError, ValueError):
    W, H = 1100, 760

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import Gtk, WebKit  # noqa: E402


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=TITLE or "floor796")
        self.set_default_size(W, H)
        view = WebKit.WebView()
        view.load_uri(URL)
        self.set_child(view)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

    def _on_key(self, _c, keyval, _code, _state):
        if keyval == 65307:          # Escape
            self.close()
        return False


class App(Gtk.Application):
    def __init__(self):
        # Stable per URL: opening the same page twice focuses the window
        # instead of stacking duplicates. (str hash() is salted per process.)
        tag = hashlib.sha1(URL.encode()).hexdigest()[:10]
        super().__init__(application_id="com.floor796.viewer.%s" % tag)

    def do_activate(self):
        Window(self).present()


if __name__ == "__main__":
    App().run([])
