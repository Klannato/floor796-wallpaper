#!/usr/bin/env python3
"""Send a command to the running floor796 wallpaper.

Bind this to a global shortcut in COSMIC settings:

    /usr/bin/python3 ~/code/floor796-wallpaper/tools/ctl.py toggle

Commands: toggle | interactive | wallpaper | refresh | boxes | quit

Why this exists: in wallpaper mode the window has an empty input region, so the
compositor never gives it focus and in-app hotkeys can never fire. The app
listens on a datagram socket at $XDG_RUNTIME_DIR/floor796.sock instead.
"""

import os
import socket
import sys

PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "floor796.sock")


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "toggle").strip().lower()
    if cmd not in ("toggle", "interactive", "wallpaper", "refresh", "boxes",
                   "quit"):
        sys.exit(f"unknown command {cmd!r} "
                 f"(toggle|interactive|wallpaper|refresh|boxes|quit)")
    if not os.path.exists(PATH):
        sys.exit(f"no wallpaper listening on {PATH}")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.sendto(cmd.encode(), PATH)
    except OSError as e:
        sys.exit(f"send failed: {e}")
    print(f"sent {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
