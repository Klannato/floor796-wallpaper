#!/usr/bin/env python3
"""Play a tile's mp4 loop into a cairo surface, on demand.

Each floor796 tile has a 1024x820, 60-frame h264 loop on the CDN — that is the
real animated artwork. This module wraps one GStreamer appsink per tile, keeps
only the newest frame, and exposes it as a cairo surface so the renderer can
draw it exactly like a still tile.

Only visible tiles should have a pipeline running: stop() when a tile leaves
the viewport.
"""

import os
import sys

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

Gst.init(None)

FMT = "BGRA"     # matches cairo FORMAT_ARGB32 on little-endian


class TileVideo:
    def __init__(self, path, width=1024, height=820, fps=12):
        self.path = path
        self.w = width
        self.h = height
        self.fps = fps
        self.surface = None
        self._buf = None
        self._pipeline = None
        self._sink = None

    def _build(self):
        desc = (
            f"filesrc location=\"{self.path}\" ! decodebin ! "
            f"videoconvert ! videoscale ! "
            f"video/x-raw,format={FMT},width={self.w},height={self.h} ! "
            f"appsink name=sink emit-signals=true sync=true "
            f"max-buffers=2 drop=true"
        )
        self._pipeline = Gst.parse_launch(desc)
        self._sink = self._pipeline.get_by_name("sink")
        self._size = self.w * self.h * 4
        self._buf = bytearray(self._size)
        self._sink.connect("new-sample", self._on_sample)
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_eos)
        self._pipeline.set_state(Gst.State.PLAYING)

    def _on_eos(self, _bus, _msg):
        # Loop the 5 s clip.
        self._pipeline.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            0)

    def _on_sample(self, sink):
        import cairo
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        data = buf.extract_dup(0, buf.get_size())
        if len(data) != self._size:
            return Gst.FlowReturn.OK
        self._buf[:] = data
        if self.surface is None:
            self.surface = cairo.ImageSurface.create_for_data(
                self._buf, cairo.FORMAT_ARGB32, self.w, self.h, self.w * 4)
        else:
            self.surface.mark_dirty()
        return Gst.FlowReturn.OK

    def start(self):
        if self._pipeline is None:
            self._build()

    def stop(self):
        if self._pipeline is not None:
            bus = self._pipeline.get_bus()
            try:
                bus.remove_signal_watch()
            except Exception:
                pass
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._sink = None
            self.surface = None
            self._buf = None


class VideoPool:
    """Keeps pipelines alive only for the tiles currently on screen."""

    def __init__(self, rips_dir=None, max_live=12):
        self.dir = rips_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "vendor", "mp4")
        self.max_live = max_live
        self.live = {}          # tid -> TileVideo
        self.scale = 1.0

    def available(self):
        if not os.path.isdir(self.dir):
            return set()
        return {f[:-4] for f in os.listdir(self.dir) if f.endswith(".mp4")}

    def path_for(self, tid):
        """Half-res transcode when zoomed out — h264 decode cost tracks the
        source resolution, so a 512x410 clip is ~4x cheaper to play."""
        lo = os.path.join(os.path.dirname(self.dir), "mp4_lo", f"{tid}.mp4")
        if self.scale <= 0.6 and os.path.exists(lo):
            return lo
        return os.path.join(self.dir, f"{tid}.mp4")

    def size_for(self, scale):
        scale = min(max(scale, 0.25), 1.0)
        return int(1024 * scale) // 2 * 2, int(820 * scale) // 2 * 2

    def sync(self, visible_tids, scale=1.0):
        """Start pipelines for newly visible tiles, stop the ones that left.

        Two rules learned the hard way:
        * Never rebuild on zoom. Tearing down every pipeline mid-gesture turns
          a smooth zoom into a multi-hundred-ms stall; decode at a fixed size
          and let cairo stretch it.
        * Start at most a couple of pipelines per call. parse_launch +
          READY->PLAYING costs ~100 ms each; doing 8 at once during a pan is
          exactly the stutter we're trying to avoid.
        """
        self.scale = 0.5     # fixed 512x410 decode; see path_for()
        w, h = self.size_for(self.scale)

        avail = self.available()
        want = [t for t in visible_tids if t in avail][:self.max_live]
        for tid in list(self.live):
            if tid not in want:
                self.live.pop(tid).stop()

        started = 0
        for tid in want:
            if started >= 2:
                break
            if tid not in self.live:
                tv = TileVideo(self.path_for(tid), w, h)
                try:
                    tv.start()
                    self.live[tid] = tv
                    started += 1
                except Exception as e:
                    print(f"video {tid} failed: {e}", file=sys.stderr)

    def surface(self, tid):
        tv = self.live.get(tid)
        return tv.surface if tv else None
