# Interactions — what works and what does not

Generated from the live data by `tools/link_audit.py` (857 objects). Links are
multi-part: `l` is split on `||` and **every** part runs, exactly as the site's
own click handler does. A `||` tail can rescue an otherwise dead click, which is
why the teleport pads below count as partial rather than dead.

```
works    803   every part of the link is something the wallpaper performs
partial    8   the click does something, but not everything the site does
dead      17   nothing happens at all
inert     29   there is no action in the data — the site does nothing either
```

## Dead (17)

| id | title | link | what the site does / why we can't |
|---|---|---|---|
| 314 | Chuck Norris | `event://chuck-norris` | FAQ: "Click on the Chunk Norris in the park zone." The effect is a DOM `CustomEvent` handled by the site's own JS — no asset to replay. |
| 361 | Where's Waldo | `event://where-is-waldo` | FAQ: "if you click on him, he will appear in full and wave at you." Site-side animation, same problem. |
| 564 | Jaws 19 (Back to the Future 2) | `event://jaws19` | Ad screen plays a site-side animation. |
| 708 | Naruto Uzumaki | `event://naruto` | Site-side animation ("Click on Naruto near the pirate ship"). |
| 728 | cable | `event://cable` | Not described in the site's FAQ. |
| 895 | Fog Generator | `event://fog` | Not described in the site's FAQ. |
| 668 | Wishing Black Hole | `event://popcorn` | Not described in the site's FAQ. |
| 829 | Meg (Family Guy) | `event://meg-family-guy` | Not described in the site's FAQ. |
| 922 | Girl with Balloon (Banksy, 2002) | `event://banksy` | Not described in the site's FAQ. |
| 406–413 | Hologram #7 … #14 | `event://pick-hologram-6…13` | The site has 14 scenes; only 6 have public `.f796.br` recordings, and `tools/rip_hologram.py` refuses the rest rather than modulo-ing into the wrong scene. |

The nine `event://` easter eggs all reduce to one missing capability: the site
dispatches a named `CustomEvent` and its own CSS/JS draws the result. Nothing in
`changelog.json` describes that visual, so reproducing them means hand-rebuilding
each effect against the tile art — a per-object art job, not a data fix.
Everything else about those objects works: they get a box, a panel with
title/date/link, and the log names the event.

## Partial (8) — teleport pads

`event://pick-teleport-N||no-click||https://…jpg` — the reference still opens,
but the teleport itself needs the kiosk's pad gating (scene state we don't model).

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

## Fixed in v1.0.3

- **`interactive://` pages 404'd without exception.** The site serves them from
  `/interactive/`, and `links.py` opened `floor796.com/<path>`. All 15 pages —
  the shower cam, Racer-796, the four quests, the statistics board, Melody,
  Fun Drawing, Mr. Bean, Free Ads, Payphone, Memorial, Change My Mind,
  Microscope, PC — returned 404. All 15 now return 200 (probed in the audit).
- **Only the first `||` part was ever run.** `play://x.mp3||https://…jpg` lost
  both halves, and the six audio objects (Half-Life health charger, H.E.V, Duke
  Nukem, Lapin-ivre, Zodiac) did nothing at all. `play://`, `play-loop://` and
  `play-loop-no-sync://` now play through `ffplay` at volume 0.5 like the site,
  and a second part opens alongside.

## Reproducing the numbers

```bash
python3 tools/link_audit.py            # summary + dead/partial lists
python3 tools/link_audit.py --all      # every object with its parts
python3 tools/link_audit.py --http     # also probe the 759 external URLs
python3 tools/link_audit.py --markdown > docs/interactions.md
```

Only the site's own schemes are probed by default — they are the ones that
break silently, and 759 external links make a full run minutes long.
