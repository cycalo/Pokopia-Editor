"""Height inspection includes concealed objects and combines contiguous terrain."""
from types import SimpleNamespace
import unittest
from gui.pages.map import column_layers


class LayerTests(unittest.TestCase):
    def test_layers_include_hidden_objects_and_terrain_bands(self):
        soil = {y: 3 for y in range(1, 11)}
        soil.update({0: 1, 11: 0x7ff, 12: 3})
        objects = [SimpleNamespace(y=5, h=2, name='Chest', handle=1),
                   SimpleNamespace(y=12, h=1, name='Roof', handle=2)]
        island = SimpleNamespace(cut=6, get_cell=lambda x, y, z: soil.get(y, 0),
                                 objects_in=lambda *args: iter(objects))
        rows = column_layers(island, 40, 50)
        self.assertIn((6, 5, 'Chest', 1), rows)
        self.assertIn((12, 12, 'Roof', 2), rows)
        self.assertTrue(any(top == 10 and bottom == 1 and handle is None
                            for top, bottom, _, handle in rows))
        self.assertFalse(any(top == 11 and handle is None for top, _, _, handle in rows))
        self.assertEqual([r[0] for r in rows], sorted((r[0] for r in rows), reverse=True))
        island.cut = 127
        self.assertEqual(rows, column_layers(island, 40, 50))

    def test_empty_cell_outside_island(self):
        island = SimpleNamespace(get_cell=lambda *args: None, objects_in=lambda *args: iter(()))
        self.assertEqual(column_layers(island, -1, -1), [])
