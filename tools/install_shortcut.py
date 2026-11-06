#!/usr/bin/env python3
"""Bind the wallpaper toggle to a COSMIC global shortcut.

COSMIC keeps user shortcuts in a RON map at
    ~/.config/cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom
keyed by (modifiers, key) with a Spawn(...) action. cosmic-settings-daemon
watches that file, so writing it is enough — no restart, no clicking.

    python3 tools/install_shortcut.py                 # Super+Shift+I
    python3 tools/install_shortcut.py --key i --mods Super
    python3 tools/install_shortcut.py --remove

Re-running is safe: the entry is found by its description and replaced in place.
"""

import argparse
import os
import re
import subprocess
import sys

PATH = os.path.expanduser(
    "~/.config/cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom")
DESC = "floor796 toggle"
DEFAULT_CMD = (f"/usr/bin/python3 "
               f"{os.path.expanduser('~/code/floor796-wallpaper/tools/ctl.py')} "
               f"toggle")


def read():
    try:
        with open(PATH) as f:
            return f.read()
    except FileNotFoundError:
        return "{\n}\n"


def entry(mods, key, cmd):
    mods_s = "".join(f"            {m},\n" for m in mods)
    return (f"    (\n"
            f"        modifiers: [\n{mods_s}        ],\n"
            f"        key: \"{key}\",\n"
            f"        description: Some(\"{DESC}\"),\n"
            f"    ): Spawn(\"{cmd}\"),\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="I")
    ap.add_argument("--mods", default="Super,Shift")
    ap.add_argument("--cmd", default=DEFAULT_CMD)
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    mods = [m.strip() for m in args.mods.split(",") if m.strip()]
    # COSMIC keys the map by the character produced: "I" only matches with
    # Shift held. Without Shift the entry must be lowercase or it never fires.
    key = args.key
    if "Shift" not in mods and len(key) == 1 and key.isupper():
        key = key.lower()

    text = read()
    # Drop any previous entry for this description, then re-insert.
    text = re.sub(r"    \(\n(?:.*\n)*?    \): Spawn\(\"[^\"]*\"\),\n",
                  lambda m: "" if DESC in m.group(0) else m.group(0), text)

    if not args.remove:
        new = entry(mods, key, args.cmd)
        if text.rstrip().endswith("}"):
            text = text.rstrip()[:-1].rstrip("\n") + "\n" + new + "}\n"
        else:
            sys.exit(f"unexpected format in {PATH}")

    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, PATH)

    if args.remove:
        print(f"removed '{DESC}' from {PATH}")
    else:
        combo = "+".join(mods + [key])
        print(f"bound {combo} -> {args.cmd}")
        print(f"file: {PATH}")
    print("cosmic-settings-daemon watches this file; no restart needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
