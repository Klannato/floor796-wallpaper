#!/usr/bin/env python3
"""Level-of-detail sprite animation for floor796 tiles, memory-mapped.

Each tile's 5 s loop is pre-packed into `vendor/anim_<size>/<tile>.raw`: 60
frames of BGRX laid out back to back. Animation is then "point cairo at a byte
range" — no decoder, no copy, no Python heap, and memory is just whatever page
cache the OS keeps.

LODs pick the frame size from the zoom:
    256x205  zoomed out      (cheap, plenty sharp when tiles are small)
    512x410  default view    (1:1 at 0.5 zoom)
    1024x820 zoomed in       (generated on demand, pruned to a disk cap)

If a LOD isn't packed yet the renderer falls back to the next one down and
upscales, so you never see a hole.

Hard-won notes (each was tried and failed):
  * GStreamer pipeline per tile: >100% CPU, 2 GB RSS, leaked bus watches
  * one tall WebP strip: WebP refuses images over 16383 px
  * one big WebP grid drawn with an offset: cairo expands the pattern across the
    whole surface — seconds per frame
  * slicing an mmap with `mm[a:b]` returns read-only bytes; cairo needs a
    writable memoryview, so hold `memoryview(mm)` and slice that
"""

import mmap
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

LODS = [(0.0, 256), (0.45, 512), (0.95, 1024)]   # min zoom -> frame size
FPS = 12
N_FRAMES = 60
MAP_BUDGET = 24            # open mappings; eviction only drops a view
HI_RES_DISK_CAP = 12       # keep at most this many 1024 LOD files

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKER = os.path.join(ROOT, "tools", "pack_frames.py")


def dims(size):
    return size, int(size * 820 / 1024)


class AnimSheets:
    def __init__(self, root=None):
        self.root = root or os.path.join(ROOT, "vendor")
        self._maps = {}        # (size, tid) -> memoryview
        self._order = []
        self._cur = {}         # (size, tid) -> (idx, surface)
        self._ids = {}         # size -> set(tid)
        self._missing = set()
        self._gen = ThreadPoolExecutor(max_workers=1)
        self._pending = set()

    # ── inventory ──────────────────────────────────────────────────────────
    def available(self, size):
        if size not in self._ids:
            d = os.path.join(self.root, f"anim_{size}")
            self._ids[size] = ({f[:-4] for f in os.listdir(d) if f.endswith(".raw")}
                               if os.path.isdir(d) else set())
        return self._ids[size]

    def lod_for(self, zoom):
        size = LODS[0][1]
        for min_zoom, s in LODS:
            if zoom >= min_zoom:
                size = s
        return size

    def frame_size_for(self, zoom):
        """Frame size the renderer will actually blit at this zoom."""
        return dims(self.lod_for(zoom))

    # ── mapping ────────────────────────────────────────────────────────────
    def _map(self, size, tid):
        key = (size, tid)
        mv = self._maps.get(key)
        if mv is not None:
            self._order.remove(key)
            self._order.append(key)
            return mv
        if key in self._missing:
            return None
        path = os.path.join(self.root, f"anim_{size}", f"{tid}.raw")
        if not os.path.exists(path):
            self._missing.add(key)
            return None
        try:
            fd = open(path, "rb")
            m = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_COPY)
            fd.close()
        except Exception:
            self._missing.add(key)
            return None
        mv = memoryview(m)     # slicing the mmap itself gives read-only bytes
        self._maps[key] = mv
        self._order.append(key)
        while len(self._order) > MAP_BUDGET:
            old = self._order.pop(0)
            if old != key:
                self._maps.pop(old, None)
                self._cur.pop(old, None)
        return mv

    # ── on-demand hi-res packing ───────────────────────────────────────────
    def _request_hi(self, tid):
        if tid in self._pending:
            return
        self._pending.add(tid)

        def job():
            try:
                subprocess.run(
                    [sys.executable, PACKER, tid, "--size", "1024"],
                    check=True, timeout=600,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._ids.pop(1024, None)
                self._prune_hi()
            except Exception:
                pass
            finally:
                self._pending.discard(tid)

        self._gen.submit(job)

    def _prune_hi(self):
        d = os.path.join(self.root, "anim_1024")
        if not os.path.isdir(d):
            return
        files = [os.path.join(d, f) for f in os.listdir(d)]
        if len(files) <= HI_RES_DISK_CAP:
            return
        files.sort(key=os.path.getmtime)
        for p in files[:-HI_RES_DISK_CAP]:
            try:
                os.remove(p)
            except OSError:
                pass

    # ── drawing ────────────────────────────────────────────────────────────
    def frame_for(self, tid, zoom=0.5):
        size = self.lod_for(zoom)
        while not self.available(size).__contains__(tid):
            if size == 1024:
                self._request_hi(tid)      # warm it for next time
            size = {1024: 512, 512: 256}.get(size, 0)
            if size == 0:
                return None

        idx = int(time.time() * FPS) % N_FRAMES
        key = (size, tid)
        cur = self._cur.get(key)
        if cur is not None and cur[0] == idx:
            return cur[1]

        mv = self._map(size, tid)
        if mv is None:
            return None
        import cairo
        fw, fh = dims(size)
        fb = fw * fh * 4
        off = idx * fb
        surf = cairo.ImageSurface.create_for_data(
            mv[off:off + fb], cairo.FORMAT_ARGB32, fw, fh, fw * 4)
        self._cur[key] = (idx, surf)
        return surf

    @property
    def live(self):
        return bool(self._maps)
