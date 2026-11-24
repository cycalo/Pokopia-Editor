"""Brush footprints must have exact dimensions and match application coordinates."""
from types import SimpleNamespace
import unittest

from gui.pages.map import MapPage, brush_offsets


class BrushTests(unittest.TestCase):
    def test_square_sizes(self):
        for size in (1, 2, 3, 8, 32):
            cells = brush_offsets('square', size, 1)
            self.assertEqual(len(cells), size * size)
            self.assertEqual(len(set(cells)), len(cells))
            self.assertEqual(len({x for x, _ in cells}), size)
            self.assertEqual(len({z for _, z in cells}), size)

    def test_rectangle_dimensions(self):
        for width, depth in ((1, 8), (8, 1), (4, 7), (8, 4), (32, 32)):
            cells = brush_offsets('rectangle', width, depth)
            self.assertEqual(len(cells), width * depth)
            self.assertEqual(len({x for x, _ in cells}), width)
            self.assertEqual(len({z for _, z in cells}), depth)

    def test_original_circle_footprint(self):
        self.assertEqual(set(brush_offsets('circle', 3, 3)), {(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)})

    def test_tool_settings_are_independent(self):
        page = SimpleNamespace(tool='height', height_brush_shape='rectangle', height_brush=4,
                               height_brush_depth=2, brush_shape='square', brush=3, brush_depth=3)
        self.assertEqual(MapPage.brush_cells(page, 20, 30),
                         [(20 + x, 30 + z) for x, z in brush_offsets('rectangle', 4, 2)])
        page.tool = 'paint'
        self.assertEqual(len(MapPage.brush_cells(page, 20, 30)), 9)
