"""Tool preferences survive application restart without changing a game save."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
import gui.app as module
from version import VERSION_STR


class PreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.qt = QApplication.instance() or QApplication([])

    def test_map_and_browser_preferences_survive_restart(self):
        with TemporaryDirectory() as directory:
            settings = Path(directory) / 'settings.json'
            settings.write_text(json.dumps(dict(check_updates=False, whats_new_seen=VERSION_STR)))
            with patch.object(module, 'SETTINGS', str(settings)):
                first = module.App()
                page = first.pages['Island Map']
                page.restore_preferences()
                shape, width, depth, _ = page.brush_controls[True]
                shape.setCurrentIndex(2)
                width.setValue(8)
                depth.setValue(5)
                page.flat_spin.setValue(36)
                page.set_height_mode('flatten')
                page.set_tool('height')
                page.layer_rows['grid'].toggle.setChecked(True)
                page.cut_slider.setValue(42)
                page.cut_row.toggle.set_quiet(True)
                catalog = first.pages['Item Catalog']
                catalog.restore_preferences()
                catalog.browser.q.setText('berry')
                catalog.browser.set_mode('list')
                catalog.amount.setValue(17)
                first.close()
                second = module.App()
                page = second.pages['Island Map']
                page.restore_preferences()
                self.assertEqual((page.height_brush_shape, page.height_brush, page.height_brush_depth),
                                 ('rectangle', 8, 5))
                self.assertEqual((page.tool, page.height_mode, page.flatten_y), ('height', 'flatten', 36))
                self.assertTrue(page.opts['grid'])
                self.assertEqual(page._pending_map_cut, (True, 42))
                catalog = second.pages['Item Catalog']
                catalog.restore_preferences()
                self.assertEqual(catalog.browser.q.text(), 'berry')
                self.assertEqual(catalog.browser.mode, 'list')
                self.assertEqual(catalog.amount.value(), 17)
                second.close()

    def test_unvisited_tools_and_readonly_sessions_preserve_preferences(self):
        with TemporaryDirectory() as directory:
            settings = Path(directory) / 'settings.json'
            state = dict(check_updates=False, whats_new_seen=VERSION_STR,
                         tools={'Island Map': {'tool': 'height', 'brushes': []}})
            settings.write_text(json.dumps(state))
            with patch.object(module, 'SETTINGS', str(settings)):
                app = module.App()
                app.close()
                self.assertEqual(json.loads(settings.read_text())['tools']['Island Map'], state['tools']['Island Map'])
                before = settings.read_bytes()
                app = module.App(persist=False)
                app.pages['Island Map'].restore_preferences()
                app.close()
                self.assertEqual(before, settings.read_bytes())
