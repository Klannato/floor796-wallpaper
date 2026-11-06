# Interactions — what works and what does not

Generated from the live data by `tools/link_audit.py` (857 objects). Links are
multi-part: `l` is split on `||` and **every** part runs, exactly as the site's
own click handler does. A `||` tail can rescue an otherwise dead click, which is
why the teleport pads below count as partial rather than dead.

```
works    807   every part of the link is something the wallpaper performs
partial    8   the click does something, but not everything the site does
dead      13   nothing happens at all
inert     29   there is no action in the data — the site does nothing either
```

## The addon layer

Most of the site's animated effects are neither in the tile art nor in
`changelog.json`. `matrix.json["addons"]` lists **24 addons**, each a
`render.js` scoped to a region; most only dispatch `add-render-slot` with a
`.f796.br` clip, a screen point and an offset. Those clips are ordinary files
over HTTP, so they are ripped verbatim with the kiosk's decoder:

```bash
python3 tools/rip_addons.py            # clips -> vendor/addons/**/*.webp + manifest
```

Ripped so far (`vendor/addons/manifest.json` — 12 clips, 26 MB, lossless WebP):

| addon | clips | behaviour |
|---|---|---|
| teleport-room | 8 × 60f @ 289×412 | the eight characters dance on the pad; one character per 5 s loop, a click advances now |
| cemetery-fog | 1 × 60f @ 85×73 | loops in the cemetery, always on |
| where-is-waldo | 1 × 60f @ 89×77 | one shot on click — Waldo appears in full and waves |
| meg | 1 × 60f @ 143×111 | one shot on click |
| banksy | 1 × 60f @ 53×128 | one shot on click |

Placement is the site's own: the manifest stores the scene point from each
addon's `render.js`, its `OFFSET_X/OFFSET_Y`, its size and — for the teleporter —
its clip polygon. Verified by rendering the pad headlessly: the couple
composites seamlessly, no offset, no rectangular patch.

## Dead (13)

| id | title | link | why |
|---|---|---|---|
| 728 | cable | `event://cable` | addon `render-cable.js` exists, not ripped yet |
| 708 | Naruto Uzumaki | `event://naruto` | addon clip exists upstream, not ripped yet |
| 668 | Wishing Black Hole | `event://popcorn` | no addon in `matrix.json`; effect unknown |
| 564 | Jaws 19 (Back to the Future 2) | `event://jaws19` | addon clip exists upstream, not ripped yet |
| 406–413 | Hologram #7 … #14 | `event://pick-hologram-6…13` | only 6 of 14 scenes have public recordings |

## Not yet ripped — the other 19 addons

`tools/rip_addons.py` takes one declarative row per addon (point, offset, size,
duration, clip URL). The remaining clip-based ones — `jaws19`, `naruto`,
`quest-tuner`, `quest-gems`, `free-ads`, `twin-pines-mall`, `interstellar`,
`change-my-mind` — extract the same way: pull those constants out of each
`render.js` and add a row. The canvas ones (`chuck`, `stat`, `melody`,
`fun-drawing`, `power-station-stat`, `memorial1`, `quest-laboratory`) draw with
their own JS: chuck needs `hand.png` + `cracks.png` + `punch.mp3` (all public)
and a small reimplementation; the rest are better opened as pages.

## Partial (8) — teleport pads

`event://pick-teleport-N||no-click||https://…jpg` — the reference still opens and
the pad now animates the matching character, but the teleport itself needs the
kiosk's pad gating (materialise/dematerialise state we don't model).

| id | title | opens |
|---|---|---|
| 907 | Sexy Sax Man (The Lost Boys, 1987) | sax-guy-from-the-lost-boys.jpg |
| 908 | Cast Away (2000) | cast-away.jpg |
| 909 | Guest from the Future (1984) | guest-from-the-future-1.jpg |
| 911 | Squidward (SpongeBob SquarePants) | squidward.jpg |
| 912 | Jack & Rose (Titanic 1997) | titanic.jpg |
| 914 | Ashka (Spellbinder, 1995) | ashka-spellbinder.jpg |
| 915 | Little Shop of Horrors (1986) | a-little-shop-of-horror.jpg |
| 921 | Spock & Uhura (Star Trek) | spock-uhura.jpg |

## Inert (29) — not a defect

27 objects have an empty `l` (Homer, Donald Duck, Windows 98, Quake 3 Logo, the
My Hero Academia group, both crowds…) and 2 are region markers
(`hologram-area`, `teleport-area`). The site does nothing on click for these
either; they are hover info only.

## Fixed along the way

- **`interactive://` pages 404'd without exception** (v1.0.3). The site serves
  them from `/interactive/`, and `links.py` opened `floor796.com/<path>`; all 15
  now return 200 (probed in the audit).
- **Only the first `||` part was ever run** (v1.0.3) — `play://x.mp3||https://…jpg`
  lost both halves and the six audio objects were silent. They now play through
  `ffplay` at volume 0.5 like the site.
- **The addon layer was missing entirely** (v1.0.4): the teleporter characters,
  the cemetery fog, Waldo's wave, meg and banksy are now the site's own frames.

## Reproducing the numbers

```bash
python3 tools/link_audit.py            # summary + dead/partial lists
python3 tools/link_audit.py --all      # every object with its parts
python3 tools/link_audit.py --http     # also probe the 759 external URLs
python3 tools/link_audit.py --markdown > docs/interactions.md
```

Only the site's own schemes are probed by default — they are the ones that
break silently, and 759 external links make a full run minutes long.
