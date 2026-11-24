"""Regression checks for Linux process detection and folder buttons."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pokopia_extras as px
from gui.pages.overview import OverviewPage
from gui.pages.backups import BackupsPage


@unittest.skipUnless(os.sys.platform.startswith('linux'), 'Linux integration')
class LinuxTests(unittest.TestCase):
    def test_emulator_scan_handles_exited_processes(self):
        with TemporaryDirectory() as directory:
            paths = []
            for index, name in enumerate(('eden', 'bash', 'ryujinx', 'eden')):
                path = Path(directory) / str(index)
                path.write_text(name + '\n')
                paths.append(str(path))
            paths.append(str(Path(directory) / 'exited'))
            with patch.object(px.glob, 'glob', return_value=paths):
                self.assertEqual(px.running_emulators(), ['eden', 'ryujinx'])

    def test_overview_opens_local_url(self):
        page = SimpleNamespace(app=SimpleNamespace(save=SimpleNamespace(folder='/tmp/save with spaces')))
        with patch('gui.pages.overview.QDesktopServices.openUrl') as open_url:
            OverviewPage.open_folder(page)
            self.assertEqual(open_url.call_args.args[0].toLocalFile(), '/tmp/save with spaces')

    def test_backups_opens_default_folder(self):
        with TemporaryDirectory() as directory:
            page = SimpleNamespace(tv=SimpleNamespace(currentItem=lambda: None))
            with patch.object(px.ps, 'default_backup_root', return_value=directory), \
                    patch('gui.pages.backups.QDesktopServices.openUrl') as open_url:
                BackupsPage.open_folder(page)
                self.assertEqual(open_url.call_args.args[0].toLocalFile(), directory)


if __name__ == '__main__':
    unittest.main()
