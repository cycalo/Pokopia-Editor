"""Deep paint only replaces existing terrain; rectangle passes its scope."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pokopia_island as pi
from gui.pages.map import MapPage

class PaintLayersTests(unittest.TestCase):
    def island(self):
        cells={0:pi.BEDROCK,1:2,2:pi.AIR,3:4,4:5,5:pi.OBJECT,6:pi.BEDROCK,7:3,8:6}
        def cls(b):
            return {pi.AIR:pi.C_AIR,pi.OBJECT:pi.C_OBJECT,5:pi.C_LIQUID}.get(b,pi.C_SOLID)
        island=SimpleNamespace(_top_solid=lambda *args:(7,cells[7]),cls=cls,
            get_cell=lambda x,y,z:cells.get(y),set_cell=lambda x,y,z,v:cells.__setitem__(y,v))
        return island,cells
    def test_surface_only_default(self):
        i,c=self.island();before=dict(c)
        self.assertEqual(pi.Island.paint(i,[(10,20)],6),1)
        self.assertEqual(c[7],6|pi.PLAYER)
        self.assertTrue(all(c[y]==before[y] for y in c if y!=7))
    def test_layers_skip_air_water_objects_bedrock_buildings_and_above_cut(self):
        i,c=self.island();before=dict(c)
        with patch.object(pi,'block_kind',side_effect=lambda b:pi.K_BUILD if b==4 else pi.K_TERRAIN):
            self.assertEqual(pi.Island.paint(i,[(10,20)],6,all_layers=True),2)
        for y in (1,7):self.assertEqual(c[y],6|pi.PLAYER)
        for y in (0,2,3,4,5,6,8):self.assertEqual(c[y],before[y])
    def test_paint_rectangle_uses_checkbox_and_single_commit(self):
        i=SimpleNamespace(x0=0,z0=0,width=10,height=10,paint=Mock(return_value=12))
        p=SimpleNamespace(drag=dict(kind='paint_box',mode='paint',a=(1,1)),view_data=SimpleNamespace(isl=i),
            world=lambda p:p,lift_objects_check=Mock(),paint_layers_check=SimpleNamespace(isChecked=lambda:True),
            paint_block=6,commit=Mock(),app=Mock(),fail=Mock(),update_hint=Mock(),overlay=Mock())
        MapPage.release(p,(2,3),None)
        i.paint.assert_called_once_with([(x,z) for x in (1,2) for z in (1,2,3)],6,all_layers=True)
        p.commit.assert_called_once()
