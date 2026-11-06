#!/usr/bin/env python3
"""Resolve the non-http link schemes in changelog.json.

floor796 mixes ordinary URLs with its own schemes, and treating them all as
"open in browser" silently breaks them. The rules below mirror the site's own
click handler (`front.*.js`), which splits `l` on `||` and runs **every** part:

    img://data/misc/x.png        an image the site shows in its own overlay
    interactive://pages/foo      an HTML page, served from /interactive/
    play://data/misc/x.mp3       play audio (plus loop / loop-no-sync variants)
    event://pick-hologram-N      select hologram scene N (a pad in the room)
    event://pick-teleport-N      teleport pad gating (kiosk only)
    event://chuck-norris         site-side DOM event: a CSS/JS animation, so it
                                 is not reproducible from the data alone
    no-click                     the site makes the whole item inert

Two bugs lived here before this file matched the site: `interactive://` was
resolved without the `/interactive/` prefix — every one of the 15 pages 404'd,
the shower cam included — and only the first `||` part was ever acted on, so
`play://x.mp3||https://…jpg` lost both halves.
"""

import subprocess

BASE = "https://floor796.com/"
INTERACTIVE = BASE + "interactive/"
PLAY_SCHEMES = ("play-loop-no-sync://", "play-loop://", "play://")

_playing = {}          # url -> Popen, so a second click does not stack audio


def _open(url):
    subprocess.Popen(["xdg-open", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"opened {url}", flush=True)


def _play(url, loop=False):
    """Play an audio file; the site plays these at volume 0.5."""
    if url in _playing and _playing[url].poll() is None:
        return False
    cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
           "-volume", "50"]
    if loop:
        cmd += ["-loop", "0"]
    cmd.append(url)
    _playing[url] = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"audio {url}{' (loop)' if loop else ''}", flush=True)
    return True


def hologram_pad_index(link):
    """Scene number for an `event://pick-hologram-N` pad, else None."""
    for part in (link or "").split("||"):
        part = part.strip()
        if part.startswith("event://pick-hologram-"):
            num = part[len("event://pick-hologram-"):].split("?")[0].strip()
            try:
                return int(num)
            except ValueError:
                return None
    return None


def _part(part, holo, addons=None):
    """Act on one `||`-separated part; returns its description or None."""
    if part == "no-click":
        return None

    for scheme in PLAY_SCHEMES:
        if part.startswith(scheme):
            rel = part[len(scheme):].split("?")[0]
            url = rel if rel.startswith("http") else BASE + rel.lstrip("/")
            _play(url, loop=(scheme != "play://"))
            return "audio"

    if part.startswith("img://"):
        _open(BASE + part[len("img://"):].lstrip("/"))
        return "image"

    if part.startswith("interactive://"):
        # Served under /interactive/; without the prefix every page 404s,
        # which looks exactly like "the shower cam is broken".
        _open(INTERACTIVE + part[len("interactive://"):].lstrip("/"))
        return "interactive page"

    if part.startswith("event://pick-hologram-"):
        num = part[len("event://pick-hologram-"):].split("?")[0].strip()
        try:
            idx = int(num)
        except ValueError:
            return "bad hologram index"
        if holo is not None and holo.scenes():
            name = holo.select(idx)
            print(f"hologram -> scene {idx}: {name}", flush=True)
            return f"hologram {idx}"
        return "hologram (no scenes)"

    if part.startswith("event://"):
        name = part[len("event://"):].split("?")[0]
        # An addon clip can reproduce some of these: the site dispatches the
        # same event name, and the addon's own render.js plays its frames.
        if addons is not None and addons.trigger_event(name):
            print(f"event {name} -> addon clip", flush=True)
            return f"event {name} (clip)"
        print(f"event {part} — site-side effect, not reproduced", flush=True)
        return "event (not reproduced)"

    if part in ("hologram-area", "teleport-area"):
        return None          # region marker, not an action

    if part.startswith(("http://", "https://")):
        _open(part)
        return "url"

    print(f"unhandled link {part!r}", flush=True)
    return "unhandled"


def resolve(link, holo=None, addons=None):
    """Act on a changelog link. Returns a short description of what happened."""
    parts = [p.strip() for p in (link or "").split("||") if p.strip()]
    if not parts:
        return "no link"
    done = [_part(p, holo, addons) for p in parts]
    done = [d for d in done if d]
    return ", ".join(done) if done else "inert"
