# Runtime Environment — COSMIC / Wayland

**Date:** 2026-11-06  
**Host kernel:** 7.2.6-generic (Ubuntu 24.04 base, Pop!\_OS)  
**User:** geo (UID 1000)

---

## 1. Session & Compositor Facts

| Key | Value |
|-----|-------|
| `XDG_SESSION_TYPE` | `wayland` |
| `XDG_SESSION_ID` | `4` |
| `XDG_CURRENT_DESKTOP` | `COSMIC` |
| `XDG_SESSION_DESKTOP` | `COSMIC` |
| `WAYLAND_DISPLAY` | `wayland-1` |
| `DISPLAY` (XWayland) | `:1` |
| `loginctl` session type | `Type=wayland` |
| Compositor binary | `/usr/bin/cosmic-comp` (PID 3344, ~2 GB RSS) |
| Compositor framework | Smithay (Rust), implements `zwlr_layer_shell_v1` natively |
| Wallpaper daemon | `/usr/bin/cosmic-bg` v1.11.0 (`cosmic-bg` package) |
| D-Bus portals | `org.freedesktop.impl.portal.desktop.cosmic` active |

**Summary:** This is a **COSMIC desktop** (System76's Rust-native desktop) running on a **pure Wayland session**. The compositor is `cosmic-comp`, built on **Smithay**, which fully implements the `wlr-layer-shell-v1` protocol. XWayland runs at `DISPLAY=:1` for legacy applications only. There is no X11 session.

### Confirmed running COSMIC processes

```
cosmic-session          (session manager)
cosmic-comp             (compositor)
cosmic-bg               (wallpaper/background engine)
cosmic-panel            (top/bottom panel)
cosmic-app-library      (dock/app drawer)
cosmic-launcher         (app launcher)
cosmic-workspaces       (workspace switcher)
cosmic-notifications    (notification daemon)
cosmic-settings-daemon  (system settings service)
cosmic-osd              (on-screen display)
xdg-desktop-portal-cosmic (desktop portal impl)
```

---

## 2. Monitor Layout

Monitors discovered via both `xrandr --query` (on DISPLAY=:1) and Python3 GDK monitor API — results are consistent.

| Index | Model | Connection | Position | Resolution | Scale | Primary? |
|-------|-------|------------|----------|------------|-------|----------|
| 0 | Acer H236HL | HDMI-A-1 | (1920, 554) | 1920 × 1080 | 1× | yes |
| 1 | SAMSUNG | DP-2 | (0, 0) | 1920 × 1080 | 1× | no |

**Union bounding box:** Width = **3840 px**, Height = **1634 px**, Origin = **(0, 0)**

> Corrected 2026-11-06 by verification: `xrandr --query` reports `Screen 0: current 3840 x 1634`.
> The union height is `max(1080, 554 + 1080) = 1634`, not 2674. An earlier draft of this
> document mis-added the vertical offset. DP-2 is driven at 1920×1080 even though the panel
> advertises a 4096×2160 native mode in sysfs.

The two monitors form an asymmetric layout: the Samsung (DP-2) is flush left at y=0, while the Acer (HDMI-A-1) is shifted right by 1920 px and down by 554 px.

### Reliable tool for this session

| Tool | Works? | Notes |
|------|--------|-------|
| `xrandr --query` (DISPLAY=:1) | ✅ Yes | Reports both monitors; requires XWayway connection |
| Python3 `Gdk.Display.get_monitors()` | ✅ Yes | Native Wayland; returns same geometry + scale factors |
| `wlr-randr` | ❌ Not installed | wlroots-only tool; not needed (cosmic-comp has its own APIs) |
| `gnome-monitor-config` | ❌ Wrong DE | GNOME-specific; irrelevant |
| `hyprctl monitors` | ❌ Not installed | Hyprland-specific |
| `kscreen-doctor` | ❌ Not installed | KDE-specific |
| `xdg-output` | ❌ Not installed | Would work on wlroots but not available |

**Recommendation:** Use `xdotool`-style screen parsing via the system python3's GDK API (`/usr/bin/python3`) or keep `xrandr --query` (on DISPLAY=:1) as a fallback shell command. Both give identical results.

---

## 3. Tool Availability Matrix

| Tool / Library | Installed? | Version | Path / Package |
|----------------|------------|---------|----------------|
| **ffmpeg** | ✅ Yes | 6.1.1-3ubuntu5 | `/usr/bin/ffmpeg` |
| mpv | ❌ No | — | `apt install mpv` needed (sudo) |
| mpvpaper | ❌ No | — | Not in any apt repo; not flatpak'd |
| cosmic-bg | ✅ Yes | 1.11.0 | `/usr/bin/cosmic-bg` (wallpaper daemon) |
| swaybg | ❌ No | — | sway-specific; irrelevant |
| xwinwrap | ❌ No | — | X11-only; irrelevant for Wayland |
| feh / nitrogen / picom | ❌ No | — | X11 wallpaper tools |
| **Python 3 (hermes env)** | ✅ Yes | 3.14.7 | venv path (isolated) |
| **Python 3 (system)** | ✅ Yes | 3.12.3 | `/usr/bin/python3` |
| **PySDL2 C library** | ✅ Yes | 2.30.0 | `libsdl2-2.0-0` (ABI present) |
| GTK 3 (Python bindings) | ✅ (system only) | 3.24.41 | gir1.2-gtk-3.0 present, but **NOT in hermes venv** (no `_gi.cpython-314.so`) |
| GTK 4 (Python bindings) | ✅ (system only) | 4.14.5 | Same — system-available, hermes-unavailable |
| gtk-layer-shell (C) | ❌ No | — | `libgtk-layer-shell0` **available in apt** |
| gtk-layer-shell (GIR) | ❌ No | — | `gir1.2-gtklayershell-0.1` **available in apt** |
| pygame | ❌ No | — | Not pip-installed |
| PySide6 / PyQt6 | ❌ No | — | Neither available |
| cairo (Python) | ❌ No | — | gi-based; not importable from hermes env |
| dbus-python | ❌ No | — | Not importable from hermes env |
| notify-send | ❌ No | — | Minor concern |
| dpkg/dconf/gsettings | ✅ Yes | — | System tools available |

### Critical observation: GTK + gi module mismatch

The Hermes agent runs under **Python 3.14.7 in an isolated venv**. The system provides **Python 3.12.3** with `python3-gi` (PyGObject 3.48.2). The HERMES venv cannot import `gi` because the `_gi` C extension is compiled for Python 3.12, not 3.14.

**Workaround:** Any code requiring GTK/GI must either:
1. Run via `/usr/bin/python3` (system interpreter) launched as a subprocess, OR
2. Be written in another language (Rust, C++, Go) without GI dependencies, OR
3. Use SDL2 directly (C library already present) rather than GTK+GI

---

## 4. Overlay Approach Evaluation

### 4a. GTK3 + gtk-layer-shell (Layer Shell Protocol)

**Feasibility:** ✅ Viable, but requires installation.

- `cosmic-comp` (Smithay-based) fully implements `zwlr_layer_shell_v1`.
- The official [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell) library explicitly lists "Smithay based compositors (such as **COSMIC**)" as supported.
- Layer shell supports layered rendering (BACKGROUND/BOTTOM/TOP/OVERLAY).

**To make it work for THIS project:**

```bash
# Would need sudo:
sudo apt install -y libgtk-layer-shell0 gir1.2-gtklayershell-0.1
```

**Architecture:**
- Create a GTK3 window using `GtkLayerShell.init_for_window(window)`
- Set layer to `BACKGROUND` or `BOTTOM` so it sits below COSMIC panel/top-bar
- Make the window full-screen across the union bbox (3840×1634)
- Set `window.set_app_paintable(True)` + Cairo drawing for bboxes
- Use `wl_input_region` (via `gtk-layer-shell` or raw Wayland client) to define click-through zones where there are NO bounding boxes, and clickable regions for objects that have bboxes

**Key pitfall for COSMIC specifically:**
- BACKGROUND layer surfaces are rendered behind everything, including panels and docks. If we use `layer=BACKGROUND`, the overlay will appear BELOW the COSMIC panel, which may be acceptable since bboxes should avoid those areas.
- **Click-passthrough is well-supported**: An empty `wl_input_region` means pointer events pass through entirely. To add interactive regions per object, call `wl_surface_add_input_region()` for each bounding box.
- Transparency: Background layer surfaces can support ARGB transparency via EGL/Wayland buffer protocols. COSMIC does NOT strip alpha from layer-surface backgrounds.

**Python integration issue:** Cannot run from the Hermes venv (Python 3.14). Must spawn via `/usr/bin/python3`.

### 4b. pygame / SDL2 Borderless Transparent Window

**Feasibility:** ⚠️ Possible but limited — SDL2 C library is present, pygame is not.

```bash
pip install pygame   # user-level install, no sudo needed
```

**Architecture:**
- Create an SDL2 surface covering the union bbox
- Set window flags: `SDL_WINDOW_BORDERLESS | SDL_WINDOW_INPUT_FOCUS | SDL_WINDOW_ALWAYS_ON_TOP`
- Fill background with transparent color (RGB=0,0,0, A=0)
- Draw bboxes with semi-transparent colors
- Use `SDL_SetWindowPosition(window, 0, 0)` with `SDL_VIDEODRAW_NONE` or Wayland native

**Caveats on COSMIC/wlroots:**
- Non-layer-SHSDL windows behave as regular toplevel windows, which means they appear in Alt+Tab, get taskbar entries, and may NOT go below other app windows reliably (`keep_below` is ignored by most compositors on Wayland).
- To mitigate: set window type hint to override-redirect if possible, or use `SDL_HINT_RENDER_VSYNC` tricks.
- Transparency works on Wayland SDL2 surfaces via the alpha channel.
- Pointer input passthrough is trickier: SDL2 doesn't expose input regions directly. Would need to handle clicks yourself and ignore/handle them.

**Verdict:** Second-best option. Simplest to set up (no sudo), but inferior window management on Wayland.

### 4c. Qt6 Frameless Translucent Window

**Feasibility:** ❌ Not viable — Qt6 / PySide6 / PyQt6 are not installed and would require building against multiple shared libs. Overkill for this project.

### 4d. X11 Override-Redirect Window (via XWayland)

**Feasibility:** ❌ Poor choice. Runs inside XWayland emulation layer, suffers from:
- Fractional scaling artifacts (both monitors are 1× so this is minor here)
- Higher latency vs native Wayland
- No proper layer ordering (must manually manage stacking)
- Can't easily span multiple monitors seamlessly
- XWayland windows don't participate in Wayland layer-shell protocol

**Only use as absolute last resort.**

---

## 5. Recommended Overlay Stack

### Decision: GTK3 + gtk-layer-shell as primary, SDL2/pygame as fallback

**Rationale:** COSMIC fully supports wlr-layer-shell. GTK3 + gtk-layer-shell gives us:
- Native layer-surface positioning (automatically spans entire outputs correctly)
- Proper click-passthrough via `wl_input_region` — pointer events only hit defined bbox regions, everything else passes through
- ARGB transparency natively handled by the compositor
- No taskbar/AppSwitcher entries (layer surfaces are excluded automatically)
- Automatic multi-monitor coverage (full-screen layer surface covers all outputs)

### Architecture overview

```
┌──────────────────────────────────────────────┐
│  cosmic-comp (Smithay compositor)            │
│                                              │
│  ┌────────────────────────────────────────┐  │ ← TOP layer (panels, dialogs)
│  │  Top-bar / Panel / Notifications       │  │
│  ├────────────────────────────────────────┤  │ ← OVERLAY layer (tooltips)
│  │  Tooltip popups                        │  │
│  ├────────────────────────────────────────┤  │ ← BOTTOM layer (video wallpaper)
│  │  video.mp4 loop (mpvpaper)             │  │
│  ├────────────────────────────────────────┤  │ ← BOTTOM layer (transparent overlay)
│  │  floor796_bbox_overlay.py (GTK3 LS)    │  │
│  └────────────────────────────────────────┘  │ ← BACKGROUND (solid bg)
│  solid color                                  │
└──────────────────────────────────────────────┘
```

### Process architecture

Two separate processes communicating via Unix socket:

1. **`video_wallpaper.sh`** — thin wrapper around `mpv` (or ffmpeg pipe):
   ```
   mpv --no-terminal --loop --geometry=0x0+0+0 \
       --wid=<layer-surface-wid-or-XID> <wallpaper.mp4>
   ```
   On Wayland, mpv can render to a Wayland output directly when passed the layer surface identifier. Alternatively, `mpvpaper` handles this integration natively.

2. **`bbox_overlay.py`** — Python 3.12 script (launched via `/usr/bin/python3`) using:
   - `gi.repository.GtkLayerShell` for layer-surface creation
   - `gi.repository.Gtk` for window/widget lifecycle
   - `gi.repository.Gdk` for display/monitor geometry
   - Cairo for rendering bounding boxes
   - `wl_input_region` for click-passthrough

Communication between processes: simple JSON-over-Unix-domain-socket for commands like "highlight id=42", "unhighlight all".

### Why NOT GTK Layer Shell background instead of a separate mpv process?

`cosmic-bg` (already running) handles static image wallpapers natively. For video wallpapers, `cosmic-bg` has **some video support** (the binary strings contain `Mvhd`, `Mdhd`, `VideoSampleEntry` — suggesting MOV/QuickTime container parsing), but it is primarily designed for still images and gradients. It does not expose a public API for injecting arbitrary video loops. Using mpv/mpvpaper remains the simpler, more proven approach.

---

## 6. Installation Steps Required

These steps would bring the required stack into place. They are **NOT executed** (read-only scope).

### Step 1: Install mpv (for video wallpaper)

```bash
sudo apt install -y mpv libmpv2
# Verifies: package exists at candidate 0.37.0-1ubuntu4
# Pulls: libmpv2 + dependencies (~15 MB download)
```

### Step 2: Install mpvpaper (for layer-surface video wallpaper)

```bash
# mpvpaper is NOT in any apt repository (confirmed: apt-cache search/mpvpaper → empty)
# Options:
#   a) Install from GitHub release:
#      git clone https://github.com/iboop/mpvpaper.git && cd mpvpaper
#      cargo build --release   # requires rustc + cargo
#      sudo cp target/release/mpvpaper /usr/local/bin/
#   b) Install via pip (if a wheel exists):
#      pip install mpvpaper    # unlikely to exist
#   c) Use plain mpv + manual layer-surface binding (custom shell script)
```

**Note:** Since mpvpaper is not in any apt repo, the cleanest path is either building from source (needs `cargo`) or writing a custom mpv wrapper. An alternative: use `pympv` Python library to embed mpv directly into the overlay process, eliminating the need for mpvpaper entirely.

### Step 3: Install gtk-layer-shell (for overlay window)

```bash
sudo apt install -y libgtk-layer-shell0 gir1.2-gtklayershell-0.1
# Verifies: 2 new packages, zero upgrades, no conflict with existing
# Candidate version: 0.8.2-1build2
```

### Step 4: Ensure system Python3 is available

Already present at `/usr/bin/python3` (3.12.3). No action needed.

### Step 5: Alternative — pure pympv approach (no mpvpaper needed)

If mpvpaper proves too hard to install, use `pympv` to embed mpv directly in the overlay process:

```bash
pip3 install pympv  # installs to user pip venv, no sudo needed
```

Then a single-process design: one Python script that spawns `mpv` via `pympv`, creates a GTK3 layer-surface, and manages both the video playback and the overlay rendering.

---

## 7. Risks & Open Questions

| Risk | Severity | Mitigation |
|------|----------|------------|
| **No sudo** — cannot install mpv or gtk-layer-shell | High | These require root/apt privileges. If sudo is unavailable, fall back to: (a) pympv embedded (still needs `libmpv2` from apt, also root); (b) cosmic-bg for wallpaper + pygame/SDL2 for overlay (no video support, just still frames or gstreamer within Python). |
| **mpvpaper not in apt** | Medium | Build from Rust source (needs cargo/rustc) or use pympv embedded approach. |
| **GTK3 gi not available in hermes venv** | Low | Spawn system python3 as subprocess; communicate via stdin/stdout or Unix socket. |
| **cosmic-bg video support unclear** | Medium | Investigate whether `cosmic-bg` can play arbitrary video files or only bundled ones. If only bundled images, stick with mpv/mpvpaper path. |
| **Input region precision** | Low | `wl_input_region` is well-documented and supported by COSMIC/composers. Known working in fono (bottom-center overlay panel) and similar projects. |
| **Multi-monitor fullscreen coverage** | Low | Layer-surface `anchor=top|bottom|left|right` with `exclusive_zone=0` covers all outputs atomically on wlroots/SMT. |
| **cosmic-comp sandbox restrictions** | Low | Sandbox gate applies to Flatpak apps. Our overlay runs as a native user-space process, not sandboxed. Full access to wayland socket. |
| **Monitor resolution changes** | Low | Re-read GDK/XRandr on `MONITORS_CHANGED` signal; redraw bboxes. |
| **HiDPI/fractional scaling future-proofing** | Low | Both GDK and gtk-layer-shell support fractional DPI. Currently all monitors are 1×. |

---

## 8. Summary Decision Matrix

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Wallpaper renderer | **mpv** (not mpvpaper — harder to install) + embedded layer-surface binding | Only video player available in apt; mpvpaper not in any repo |
| Overlay framework | **GTK3 + gtk-layer-shell** (requires `sudo apt install`) | Native WLR layer-shell support in cosmic-comp; click-passthrough via input regions; auto-fullscreen |
| Python runtime | **System `/usr/bin/python3`** (3.12.3) | Hermes venv (3.14) lacks gi modules; system Python has all GI bindings |
| Alternative overlay | **SDL2/pygame** (user-level, no sudo) | Works but inferior window management on Wayland — no layer protocol, taskbar entry, unreliable keep-below |
| Inter-process comm | **Unix domain socket** (JSON) | Clean separation; low overhead; no network stack needed |

---

*Document generated: 2026-11-06T*  
*Probes: env vars, loginctl, ps aux, pgrep, xrandr, GDK Display API, which/command -v, dpkg -l, apt-cache policy/search, strings binary analysis, web research on COSMIC ecosystem*
