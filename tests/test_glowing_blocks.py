"""Read-only treasure table parsing, with cleared and malformed entries."""
import struct
import unittest
import pokopia_island as pi


class GlowingBlockTests(unittest.TestCase):
    def test_valid_empty_and_invalid_positions(self):
        island = object.__new__(pi.Island)
        island.d = bytearray(pi.GLOWING_POSITIONS + pi.GLOWING_SLOTS * 8)
        island.cmap = [0xffff] * 4096
        chunk = (1137 >> 5) * 64 + (1006 >> 5)
        island.cmap[chunk] = 0
        record = pi.GLOWING_POSITIONS + 13 * 8
        struct.pack_into('<HHHH', island.d, record, 1006, 36, 1137, 4)
        struct.pack_into('<HHHH', island.d, pi.GLOWING_POSITIONS, 1006, 128, 1137, 0)
        struct.pack_into('<HHHH', island.d, pi.GLOWING_POSITIONS + 8, 2048, 36, 1137, 0)
        before = bytes(island.d)
        self.assertEqual(island.glowing_blocks(), [(13, 1006, 36, 1137, 4)])
        self.assertEqual(bytes(island.d), before)
        struct.pack_into('<HHHH', island.d, record, 0, 0, 0, 0)
        self.assertEqual(island.glowing_blocks(), [])
