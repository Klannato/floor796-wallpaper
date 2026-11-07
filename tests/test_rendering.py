"""Small synthetic rendering tests; no downloads or Wayland session needed."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import cairo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
from scene import Camera, Scene, paint_cover


def image(w=8, h=8, scale=1):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * scale, h * scale)
    surface.set_device_scale(scale, scale)
    return surface


def data(surface):
    surface.flush()
    return bytes(surface.get_data())


class RenderingTests(unittest.TestCase):
    def setUp(self):
        with patch("scene._load", side_effect=lambda name: {"mat": []}
                   if name == "matrix.json" else []), \
                patch.object(Scene, "_content_index", return_value=(set(), (0, 0, 8, 8))):
            self.scene = Scene()
        self.scene.mask_origin = (0, 0)
        self.scene.mask_scale = 1
        self.scene._mask_buf = bytearray([255, 255, 255, 255, 0, 0, 0, 0] * 8)
        self.scene.mask_surf = cairo.ImageSurface.create_for_data(
            self.scene._mask_buf, cairo.FORMAT_A8, 8, 8, 8)
        self.cam = Camera(0, 0, 1)

        def tiles(cr, *args):
            cr.set_source_rgba(1, 0, 0, 0.75)
            cr.rectangle(0, 0, 8, 4)
            cr.fill()
        self.scene._paint_tiles = tiles

    def test_masked_render_matches_legacy_at_normal_scale(self):
        expected, actual = image(), image()
        cr = cairo.Context(expected)
        cr.set_source_rgb(0.02, 0.02, 0.03)
        cr.paint()
        tiles = image()
        self.scene._paint_tiles(cairo.Context(tiles))
        cr.set_source_surface(tiles, 0, 0)
        cr.mask_surface(self.scene._mask_device(self.cam, 8, 8), 0, 0)
        self.scene.draw(cairo.Context(actual), self.cam, 8, 8, objs=False)
        self.assertEqual(data(expected), data(actual))

    def test_scaled_pixel_art_is_nearest_neighbour(self):
        logical, actual, expected = image(), image(scale=2), image(scale=2)
        self.scene.draw(cairo.Context(logical), self.cam, 8, 8, objs=False)
        self.scene.draw(cairo.Context(actual), self.cam, 8, 8, objs=False)
        cr = cairo.Context(expected)
        cr.set_source_surface(logical)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        self.assertEqual(data(expected), data(actual))

    def test_reused_scene_buffer_does_not_leave_old_pixels(self):
        target = image()
        self.scene.draw(cairo.Context(target), self.cam, 8, 8, objs=False)
        buffer = self.scene._tile_targets[(8, 8)]
        self.scene._paint_tiles = lambda *args: None
        self.scene.draw(cairo.Context(target), self.cam, 8, 8, objs=False)
        expected = image()
        cr = cairo.Context(expected)
        cr.set_source_rgb(0.02, 0.02, 0.03)
        cr.paint()
        self.assertEqual(data(expected), data(target))
        self.assertIs(buffer, self.scene._tile_targets[(8, 8)])

    def test_masks_are_cached_per_camera_and_bounded(self):
        first = self.scene._mask_device(self.cam, 8, 8)
        self.scene._mask_device(Camera(1, 0, 1), 8, 8)
        self.assertIs(first, self.scene._mask_device(self.cam, 8, 8))
        for x in range(10):
            self.scene._mask_device(Camera(x, 0, 1), 8, 8)
        self.assertEqual(len(self.scene._mask_cache), self.scene.viewport_cache_budget)

    def test_missing_tiles_are_safe_to_lookup_repeatedly(self):
        with patch("scene.os.path.exists", return_value=False):
            self.assertIsNone(self.scene.surface("missing"))
            self.assertIsNone(self.scene.surface("missing"))
            for i in range(20):
                self.scene.surface(f"missing-{i}")
        self.assertEqual(len(self.scene._surfaces), self.scene.surface_budget)
        self.assertEqual(set(self.scene._surfaces), set(self.scene._surface_order))

    def test_valid_small_tile_is_not_rejected(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            self.scene.keyed_dir = directory
            path = os.path.join(directory, "tiny.png")
            Image.new("RGB", (8, 8), "black").save(path)
            self.assertLess(os.path.getsize(path), 1024)
            tile = self.scene.surface("tiny")
            self.assertIsNotNone(tile)
            self.assertEqual(tile.get_width(), 8)
            self.assertIs(tile, self.scene.surface("tiny"))

    def test_background_cache_preserves_scaled_cover_and_reuses_it(self):
        background = image(4, 4)
        cr = cairo.Context(background)
        cr.set_source_rgb(0.1, 0.5, 0.8)
        cr.paint()
        for scale in (1, 2):
            expected, actual = image(scale=scale), image(scale=scale)
            paint_cover(cairo.Context(expected), background, 8, 8)
            with patch("scene.paint_cover", wraps=paint_cover) as cover:
                for _ in range(2):
                    actual = image(scale=scale)
                    self.scene.draw(cairo.Context(actual), self.cam, 8, 8,
                                    background=background, objs=False)
                self.assertEqual(cover.call_count, 1)
            # The lower half contains no scene art, only the cached backdrop.
            stride = actual.get_stride()
            self.assertEqual(data(expected)[4 * scale * stride:],
                             data(actual)[4 * scale * stride:])


if __name__ == "__main__":
    unittest.main()
