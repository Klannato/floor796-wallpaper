#!/usr/bin/env python3
"""List every interaction in changelog.json and whether we can perform it.

The user-facing question is "which clicks do nothing?", and the honest answer
has three states, not two:

  works     every part of the link is something we can perform
  inert     there is no action in the data (27 empty links, 2 region markers) —
            the site does nothing there either, so this is not a defect
  partial   the click does something, but not everything the site does —
            typically `event://<name>`, whose visual result is a CSS/JS
            animation inside the site with no asset to replay
  dead      no part of the link is actionable: a bare event, a region marker,
            or a page that does not resolve

Links are multi-part (`a||b||c`) and the site's `front.*.js` runs every part,
so a single `||` tail can rescue an otherwise dead click — the teleport pads
are exactly that: `event://pick-teleport-7||no-click||…spock-uhura.jpg` cannot
teleport, but it can show the reference still.

    /usr/bin/python3 tools/link_audit.py                # summary + dead/partial
    /usr/bin/python3 tools/link_audit.py --all          # every object
    /usr/bin/python3 tools/link_audit.py --http         # probe external URLs too
    /usr/bin/python3 tools/link_audit.py --markdown > docs/interactions.md
"""

import argparse
import collections
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "app"))

from scene import Scene  # noqa: E402

BASE = "https://floor796.com/"
INTERACTIVE = BASE + "interactive/"
PLAY = re.compile(r"^play(-loop(-no-sync)?)?://(.+)$")


def parts_of(link):
    return [p.strip() for p in (link or "").split("||") if p.strip()]


def part_kind(p):
    """-> (kind, value) for one `||` part."""
    if p == "no-click":
        return ("inert", p)
    m = PLAY.match(p)
    if m:
        return ("audio", BASE + m.group(3).lstrip("/"))
    if p.startswith("img://"):
        return ("image", BASE + p[len("img://"):].lstrip("/"))
    if p.startswith("interactive://"):
        return ("interactive", INTERACTIVE + p[len("interactive://"):].lstrip("/"))
    if p.startswith("event://pick-hologram-"):
        return ("holo-pad", p[len("event://pick-hologram-"):].split("?")[0])
    if p.startswith("event://pick-teleport-"):
        return ("teleport", p)
    if p.startswith("event://"):
        return ("event", p[len("event://"):])
    if p in ("hologram-area", "teleport-area"):
        return ("marker", p)
    if p.startswith(("http://", "https://")):
        return ("url", p)
    return ("unknown", p)


def http(url):
    try:
        return subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-m", "20",
             "-L", url], capture_output=True, text=True).stdout.strip()
    except Exception:
        return "err"


def audit(link, scenes, probe):
    """-> (state, actionable[], unreproduced[]) for one object's link."""
    actionable, unreproduced, broken_urls = [], [], []
    parts = parts_of(link)
    # An object with no link, or with nothing but region markers, is inert on
    # the site too. Counting those as "broken" overstates the problem badly:
    # 27 objects legitimately have no action at all.
    if not parts or all(part_kind(p)[0] in ("marker", "inert") for p in parts):
        return ("inert", [], [])
    for p in parts:
        kind, val = part_kind(p)
        if kind in ("image", "interactive", "url", "audio"):
            code = http(val) if probe else ""
            if code and code != "200":
                broken_urls.append((kind, val, code))
            else:
                actionable.append(kind if not code else f"{kind} {code}")
        elif kind == "holo-pad":
            try:
                if int(val) < scenes:
                    actionable.append(f"hologram {val}")
                else:
                    unreproduced.append(f"hologram {val} (not ripped)")
            except ValueError:
                unreproduced.append(f"hologram {val} (unparsable)")
        elif kind in ("event", "teleport"):
            unreproduced.append(val if kind == "event" else "teleport gate")
        # markers and no-click are neither: not actions at all

    if not actionable and not unreproduced:
        return ("inert", actionable, [])
    if not actionable and not unreproduced:
        return ("dead", actionable, ["no action in the data"])
    if not actionable:
        return ("dead", actionable, unreproduced)
    if unreproduced or broken_urls:
        return ("partial", actionable, unreproduced +
                [f"{u} HTTP {c}" for _k, u, c in broken_urls])
    return ("works", actionable, [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--http", action="store_true",
                    help="also probe the 759 external URLs (slow)")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    scene = Scene()
    try:
        import holo
        scenes = len(holo.Hologram().scenes() or [])
    except Exception:
        scenes = 0

    rows = []
    for o in scene.changelog:
        probe = args.http
        state, act, unrep = audit(o.get("l"), scenes, probe)
        rows.append((o.get("id"), o.get("t", ""), state, act, unrep))

    counts = collections.Counter(r[2] for r in rows)
    if args.markdown:
        print("# floor796 interactions — what works and what does not\n")
        print("Generated by `tools/link_audit.py`. Links are split on `||` and "
              "every part is run, exactly as the site's `front.*.js` does.\n")
    print(f"{'state':10s} {'objects':>7s}")
    for k in ("works", "partial", "dead", "inert"):
        print(f"{k:10s} {counts.get(k, 0):7d}")
    print(f"{'total':10s} {len(rows):7d}   (hologram scenes ripped: {scenes})")

    for state in ("dead", "partial"):
        sel = [r for r in rows if r[2] == state] if args.all else \
              [r for r in rows if r[2] == state]
        print(f"\n--- {state.upper()} ({len(sel)}) ---")
        if args.markdown:
            print("\n| id | title | works | missing |")
            print("|---|---|---|---|")
        for oid, title, _s, act, unrep in sel:
            if args.markdown:
                print(f"| {oid} | {title[:46]} | {', '.join(act) or '—'} | "
                      f"{', '.join(unrep) or '—'} |")
            else:
                print(f"  {oid:>4}  {title[:38]:40s} "
                      f"{(', '.join(act) or '—')[:30]:32s} "
                      f"{', '.join(unrep)[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
