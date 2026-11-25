"""Object stacks move together when terrain is raised."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import pokopia_island as pi

class LiftTests(unittest.TestCase):
    def test_stack_and_large_footprint_move_once(self):
        base = SimpleNamespace(handle=1,x=10,y=29,z=10,h=2,dir=0,box=(10,10,11,10))
        top = SimpleNamespace(handle=2,x=11,y=31,z=10,h=1,dir=0,box=(11,10,11,10))
        unrelated = SimpleNamespace(handle=3,x=12,y=29,z=10,h=1,dir=0,box=(12,10,12,10))
        objs=[base,top,unrelated]
        def objects_in(x0,z0,x1,z1):
            return (o for o in objs if o.box[0]<=x1 and o.box[2]>=x0 and o.box[1]<=z1 and o.box[3]>=z0)
        island=SimpleNamespace(objects_in=objects_in,move_objects=Mock())
        pi.Island._lift_surface_objects(island,10,10,28)
        self.assertEqual(island.move_objects.call_args.args[0],[(1,10,30,10,0),(2,11,32,10,0)])

    def test_no_objects_is_noop(self):
        island=SimpleNamespace(objects_in=lambda *args: [],move_objects=Mock())
        pi.Island._lift_surface_objects(island,10,10,28)
        island.move_objects.assert_not_called()
