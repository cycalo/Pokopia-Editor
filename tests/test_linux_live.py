"""Exercise real Linux process memory access against an owned child process."""
import hashlib
import os
import struct
import subprocess
import sys
import unittest
from unittest.mock import mock_open, patch

import pokopia_live as live


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux procfs')
class LinuxLiveTests(unittest.TestCase):
    def test_attach_read_write_and_reject_wrong_build(self):
        code = '''
import ctypes, mmap, struct, sys
memory = mmap.mmap(-1, 0x4000000)
memory[:0x100] = b'T' * 0x100
struct.pack_into('<Q', memory, 0x3483AB8, 0x8000000 + 0x35618F0)
print('ready', flush=True)
sys.stdin.readline()
'''
        with subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True) as child:
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                with patch.object(live, 'HEAD_SHA256', hashlib.sha256(b'T' * 0x100).hexdigest()):
                    game = live._attach_linux(child.pid, 'lichii')
                    self.assertIsNotNone(game)
                    try:
                        self.assertTrue(game.alive())
                        game.select(25, 7)
                        self.assertEqual(game.u16(game.main + live.SELECTED), 25)
                        self.assertEqual(game.u16(game.main + live.POSITION), 7)
                        with self.assertRaisesRegex(live.LiveError, 'Load into the world'):
                            game.transform(25)
                        holder = game.main + 0x3800000
                        player = game.main + 0x3900000
                        game.write(game.main + live.PLAYER_PTR, struct.pack('<Q', holder))
                        game.write(holder + 0x30, struct.pack('<Q', player))
                        game.transform(25)
                        self.assertEqual(game.u16(game.main + live.FORM), 25)
                        self.assertEqual(game.u16(player + live.P_DESIRED), 25)
                        self.assertEqual(game.u16(player + live.P_ANIM), live.ANIM_TRANSFORM)
                        self.assertEqual(game.read(player + live.P_GO, 1), b'\x01')
                        game.transform(0)
                        self.assertEqual(game.u16(game.main + live.FORM), 0)
                        self.assertEqual(game.u16(player + live.P_DESIRED), live.HUMAN)
                    finally:
                        game.close()
                self.assertIsNone(live._attach_linux(child.pid, 'lichii'))
            finally:
                child.stdin.write('\n')
                child.stdin.flush()
                child.wait(timeout=5)

    def test_appimage_executable_detection_skips_mount_helper(self):
        with patch.object(live.glob, 'glob', return_value=['/proc/123/comm', '/proc/456/comm']), \
                patch('builtins.open', mock_open(read_data='AppRun\n')), \
                patch.object(live.os, 'readlink', side_effect=['/tmp/.mount_test/usr/bin/lichii', '/tmp/lichii.AppImage']):
            self.assertEqual(live.emulator_pids(), [(123, 'lichii')])
