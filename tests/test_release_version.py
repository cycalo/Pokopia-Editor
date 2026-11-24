import unittest
from gui.updates import newer, parse


class ReleaseVersionTests(unittest.TestCase):
    def test_linux_release_tags(self):
        self.assertEqual(parse('linux-v1.0.0'), (1, 0, 0))
        self.assertEqual(parse('v1.0.0'), (1, 0, 0))
        self.assertFalse(newer('linux-v1.0.0', current=(1, 0, 0)))
        self.assertTrue(newer('linux-v1.0.1', current=(1, 0, 0)))
        self.assertIsNone(parse('linux-v1.0.1-invalid'))
