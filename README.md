# floor796 wallpaper

An animated, pannable wallpaper of [floor796.com](https://floor796.com) — a huge
pixel-art "wimmelbilder" scene — with the site's interactive object references
working as hover panels and links.

Runs as one `zwlr_layer_shell` surface per monitor over a static backdrop image,
with the scene drawn on top and masked to its own silhouette.

```
┌────────────── monitor 0 ──────────────┐  ┌────────────── monitor 1 ──────────────┐
│  backdrop image + masked scene render │  │  backdrop image + masked scene render │
└───────────────────────────────────────┘  └───────────────────────────────────────┘
        both driven by one shared camera, offset per monitor
```

## Requirements

- A Wayland compositor implementing `zwlr_layer_shell_v1`
  (cosmic-comp, wlroots-based, KDE). Tested on COSMIC.
- System Python 3 with `python3-gi`, GTK 3, `gir1.2-gtklayershell-0.1`,
  `pycairo`, `pillow`, and `brotli` (for the hologram decoder).
- `ffmpeg` and `curl` for the asset pipeline.

```bash
sudo apt install python3-gi gir1.2-gtklayershell-0.1 python3-cairo \
                 python3-pil ffmpeg curl
pip install brotli
```

## Build the assets

`vendor/` is not tracked (several GB of frames). Rebuild it once:

```bash
python3 tools/fetch_meta.py              # matrix.json + changelog.json
python3 tools/rip_tiles.py               # per-tile mp4 -> lossless frame (110)
python3 tools/pack_frames.py --size 256  # animation LODs
python3 tools/pack_frames.py --size 512
python3 tools/rip_hologram.py            # teleporter room scenes (.f796.br)
python3 tools/downsample_holo.py         # half-res hologram pack
python3 tools/build_keyed.py             # void-transparent tiles
python3 tools/build_mask.py              # silhouette mask starter
```

The 1024 LOD is generated on demand when you zoom past 1.05.

`tools/rip_hologram.py` needs `brotli` and the kiosk decoder, so run it with the
interpreter that has brotli installed.

## Run

```bash
# wallpaper (one surface per monitor, click-through by default)
/usr/bin/python3 app/wallpaper.py

# with a hand-edited silhouette mask
/usr/bin/python3 app/wallpaper.py --mask vendor/mask_base.png
```

Or install the user service, which restarts on failure and starts at login:

```bash
cp config/floor796-wallpaper.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now floor796-wallpaper
```

### Controls

Wallpaper mode has an **empty input region**, so it receives no pointer or
keyboard events at all. That is deliberate — clicks fall through to the desktop.
Control it from outside:

```bash
tools/ctl.py toggle        # wallpaper <-> interactive
tools/ctl.py refresh       # re-read hologram offsets and the mask
tools/ctl.py quit
```

Bind `tools/ctl.py toggle` to a global shortcut with
`tools/install_shortcut.py` (COSMIC stores shortcuts in a config file, so it
writes it directly rather than asking you to click through settings).

In interactive mode:

| input | action |
|---|---|
| move | hover a character → box + title/date/link panel |
| click | open the reference (images, pages, hologram scene select) |
| drag | pan the scene |
| wheel | zoom at the cursor |

## Other entry points

```bash
app/viewer.py                 # windowed explorer, same renderer, always interactive
app/align.py                  # GUI to hand-align the six hologram scenes
python3 tools/decode_p.py     # verify p-field decoding (all 857 objects)
python3 tools/parity_check.py # diff our boxes against the kiosk reference
python3 tools/render_check.py t3l1   # draw boxes on real tile art
python3 tools/slice_parity.py "1920x1080@0,0;1920x1080@1920,567"
                              # per-monitor slice must be byte-identical
python3 tools/box_audit.py    # our boxes vs the site's own front-end algorithm
python3 tools/link_audit.py   # which interactions work, which are dead
```

## How it works

**Coordinates.** `changelog.json` stores positions as
`<tileRef>,<localY>,<localX>` — Y before X. Tile identity maps to a grid cell via
`matrix.json`, and

```
abs_x = col * 1016 + localX
abs_y = row *  812 + localY
```

Tiles are painted 1024×820 on a 1016×812 stride. See `docs/p-field-decoding.md`;
`docs/verification.md` shows the decode is byte-identical to the kiosk's own
implementation for all 804 objects.

**Scene and animation.** `app/scene.py` streams only the tiles intersecting the
viewport. Animated tiles play pre-packed raw frames (`app/anim.py`) — 60 frames
of BGRX per tile, `mmap`ed so a frame is a pointer into page cache rather than a
decoded image. Frame size follows zoom (256 / 512 / 1024). Static tiles use the
lossless rip directly.

**Backdrop and mask.** `app/scene.py` paints the backdrop with object-fit cover,
then draws the scene through a silhouette mask (`vendor/mask_base.png`, white =
keep). The mask is hand-editable: paint it in GIMP and `ctl.py refresh`.

**Hologram room.** The projection is not tile art — it is six separate 805×646
scene recordings the site composites in, replayed on a 10-second cycle
(`app/holo.py`), positioned and clipped with constants taken from the kiosk.

**Links.** `app/links.py` resolves floor796's own schemes instead of handing
everything to a browser: `img://` and `interactive://` resolve against
floor796.com, `event://pick-hologram-N` selects a scene, and other `event://`
links are site-side animations that are logged rather than faked.

## Layout

```
app/     scene.py      tiles, camera, mask, object boxes
         anim.py       mmap'd frame packs, LOD
         holo.py       teleporter room projection
         links.py      link-scheme resolution
         wallpaper.py  multi-monitor layer-shell host (the product)
         viewer.py     windowed explorer
         align.py      hologram alignment GUI
         addons.py     ripped addon clips (teleporter, fog, one-shots)
         pages.py      interactive:// page routing (image / ffplay / webkit / browser)
         show.py       in-app image window; ffplay video window
         webview.py    GTK4+WebKit child used by pages.py
tools/   fetch_meta, rip_tiles, pack_frames, rip_hologram, downsample_holo,
         build_keyed, build_mask, ctl, install_shortcut,
         decode_p, parity_check, render_check, slice_parity,
         box_audit, link_audit  (verification)
docs/    p-field-decoding.md, verification.md, interactions.md
config/  holo_offsets.json (per-scene alignment), systemd unit
```

## Known limitations

- 13 of the 20 hologram pads in the data have no public scene recording; clicking
  one logs "scene N not available" rather than doing something wrong.
- Boxes are the bounding hull of the site's own polygon points, so they can be
  loose around a sprite. That is the source data, not the decode.
- Memory is dominated by page cache for the frame packs (~0.4–0.9 GB depending
  on zoom). It is reclaimable, but halving the packs to 30 frames would halve it.
