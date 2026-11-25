"""Rectangle height edits use inclusive cells and one history entry."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import pokopia_island as pi
from gui.pages.map import MapPage

class HeightRectangleTests(unittest.TestCase):
    def page(self, mode):
        island=SimpleNamespace(x0=10,z0=20,width=5,height=5,
                               raise_ground=Mock(return_value=6),lower_ground=Mock(return_value=6),
                               level_ground=Mock(return_value=6))
        page=SimpleNamespace(drag=dict(kind='height_box',mode=mode,a=(12,22),b=(10,20)),
                             view_data=SimpleNamespace(isl=island),world=lambda p:p,
                             lift_objects_check=SimpleNamespace(isChecked=lambda:True),flatten_y=40,
                             commit=Mock(),fail=Mock(),update_hint=Mock(),overlay=Mock(),app=Mock())
        return page,island
    def test_modes_reverse_drag_and_lifting(self):
        for mode in ('raise','lower','flatten'):
            with self.subTest(mode=mode):
                p,i=self.page(mode);MapPage.release(p,(10,21),None)
                cells=[(x,z) for x in range(10,13) for z in range(21,23)]
                if mode=='raise':i.raise_ground.assert_called_once_with(cells,lift_objects=True)
                elif mode=='lower':i.lower_ground.assert_called_once_with(cells)
                else:i.level_ground.assert_called_once_with(cells,40,lift_objects=True)
                p.commit.assert_called_once();self.assertIsNone(p.drag)
    def test_collision_rolls_back_instead_of_committing(self):
        p,i=self.page('raise');i.raise_ground.side_effect=pi.EditError('Ceiling')
        MapPage.release(p,(10,21),None)
        p.fail.assert_called_once();p.commit.assert_not_called()
    def test_bounds_clip_to_map(self):
        p,i=self.page('raise');MapPage.release(p,(0,0),None)
        cells=i.raise_ground.call_args.args[0]
        self.assertEqual(len(cells),9)
        self.assertTrue(all(10<=x<=12 and 20<=z<=22 for x,z in cells))
