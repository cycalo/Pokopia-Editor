"""--screenshot DIR: show every page, wait for background work, save a PNG of the window, quit.

Used to check the UI. Settings are not written in this mode.
"""
import os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from gui import theme as T


def run_screenshots(win, outdir):
    os.makedirs(outdir, exist_ok=True)
    names = list(win.pages)

    def prep(name):
        p = win.pages[name]
        if name == 'Bag':
            p.browser.q.setText('berry')
            p.grid.sel = {0}
            p.grid.changed()
        elif name == 'Item Catalog':
            p.cats.setCurrentRow(6)
        elif name == 'Residents':
            if p.model.rows:
                p.tv.selectRow(0)
        elif name == 'Backups':
            p.compare_b00()
        elif name == 'Advanced':
            p.gate.toggle.setChecked(True)

    def busy(name):
        if name == 'Island Map':
            return win.pages['Island Map'].data is None and bool(win.pages['Island Map'].loading or not win.map_cache)
        if name in ('Photos', 'Overview'):
            return win.album_state == 'loading'
        return False

    def step(i, waited=0):
        if i >= len(names):
            QApplication.instance().quit()
            return
        name = names[i]
        if waited == 0:
            win.show_page(name)
            prep(name)
        if busy(name) and waited < 150:
            return QTimer.singleShot(200, lambda: step(i, waited + 1))
        QTimer.singleShot(700, lambda: grab(i))

    def grab(i):
        QApplication.processEvents()
        fn = f'{i + 1:02}_{names[i].replace(" & ", "_").replace(" ", "_")}_{T.NAME}.png'
        win.grab().save(os.path.join(outdir, fn))
        step(i + 1)

    QTimer.singleShot(900, lambda: step(0))
