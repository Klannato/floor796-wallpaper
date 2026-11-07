#!/usr/bin/env python3
"""Watch whether a window covers the screen, so the wallpaper can idle.

Wayland offers a layer-shell client no way to ask "am I occluded", but COSMIC
publishes `zcosmic_toplevel_info_v1`: every toplevel with its state array. A
maximized or fullscreen toplevel means the wallpaper is behind a window, and a
wallpaper nobody can see does not need 12 frames per second.

`app/toplevel_probe.c` (built by `tools/build_probe.sh` into `vendor/bin/`) does
the protocol work and prints one line per change — `covered 1` / `covered 0`.
This module reads that line on a thread and exposes a plain boolean; if the
binary or the protocol is missing, it reports "not covered" forever, which is
the safe direction (the wallpaper simply keeps animating).
"""

import os
import subprocess
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "vendor", "bin", "toplevel_probe")


class CoverWatcher:
    def __init__(self, binary=PROBE):
        self.binary = binary
        self.covered = False
        self._proc = None
        self._thread = None
        self.ok = False

    def start(self):
        if not (os.path.isfile(self.binary) and os.access(self.binary, os.X_OK)):
            print("cover watcher: probe not built (skipping)", flush=True)
            return self
        try:
            self._proc = subprocess.Popen(
                [self.binary], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1)
        except OSError as e:
            print(f"cover watcher: {e}", flush=True)
            return self
        self.ok = True
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        print("cover watcher: watching toplevel states", flush=True)
        return self

    def _read(self):
        stream = self._proc.stdout if self._proc else None
        if stream is None:
            return
        for line in stream:
            line = line.strip()
            if line.startswith("covered "):
                was = self.covered
                self.covered = line.split()[1] == "1"
                if self.covered != was:
                    print(f"screen: {'covered' if self.covered else 'clear'}"
                          f" — {'throttling to 1 fps' if self.covered else 'full rate'}",
                          flush=True)
        # Probe died (compositor restart, crash): fall back to full rate rather
        # than staying throttled forever behind a window that may be gone.
        self.covered = False
        self.ok = False
        print("cover watcher: probe exited, full rate", flush=True)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
