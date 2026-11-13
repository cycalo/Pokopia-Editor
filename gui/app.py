"""Main window: sidebar, header, status bar, pages, and all save / undo / file handling."""
import datetime, json, os, sys, threading

from PySide6.QtCore import QByteArray, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut, QPalette, QColor
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QFileDialog, QAbstractSpinBox, QStackedWidget, QVBoxLayout, QWidget,
                               QSizePolicy)

import pokopia_extras as px
import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.assets import Assets, app_icon, set_app_id
from gui.updates import UpdateChecker
from version import VERSION_STR, WHATS_NEW

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False):  # the exe keeps its settings in %APPDATA%\Pokopia Editor
    _APPDATA = os.environ.get('APPDATA') or os.path.expanduser('~')
    _USER_DIR = os.path.join(_APPDATA, 'Pokopia Editor')
    _OLD_DIR = os.path.join(_APPDATA, 'Pokopia Save Editor')  # name before 1.2
    if not os.path.isdir(_USER_DIR) and os.path.isdir(_OLD_DIR):
        try:
            os.rename(_OLD_DIR, _USER_DIR)
        except OSError:
            _USER_DIR = _OLD_DIR
    os.makedirs(_USER_DIR, exist_ok=True)
    SETTINGS = os.path.join(_USER_DIR, 'settings.json')
else:
    SETTINGS = os.path.join(HERE, 'settings.json')


class Bridge(QObject):
    """Results from worker threads, delivered on the GUI thread."""
    done = Signal(str, object, object, object)


def page_classes():
    from gui.pages.overview import OverviewPage
    from gui.pages.bag import BagPage, CatalogPage
    from gui.pages.residents import ResidentsPage
    from gui.pages.moves import MovesPage
    from gui.pages.wardrobe import WardrobePage
    from gui.pages.map import MapPage
    from gui.pages.photos import PhotosPage
    from gui.pages.backups import BackupsPage
    from gui.pages.advanced import AdvancedPage
    from gui.pages.mods import ModsPage
    return [('Save', [OverviewPage]),
            ('Edit', [BagPage, CatalogPage, ResidentsPage, MovesPage, WardrobePage]),
            ('Explore', [MapPage, PhotosPage]),
            ('Tools', [BackupsPage, ModsPage, AdvancedPage])]


class App(QMainWindow):
    def __init__(self, folder=None, theme=None, persist=True):
        super().__init__()
        self.persist = persist  # False for screenshot runs, which must not change the user's settings
        self.settings = self.read_settings()
        T.set_theme(theme or self.settings.get('theme', 'dark'))
        self.save, self.album, self.album_thumbs, self.album_state = None, None, [], 'none'
        self.map_cache, self.emus, self.adv_unlocked = {}, [], False
        self.assets = Assets()
        self.bridge = Bridge()
        self.bridge.done.connect(self.on_result)
        self.current = 'Overview'
        self.setWindowTitle('Pokopia Editor')
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1180, 760)
        self.restore_geometry()
        self.build_ui()
        self.shortcuts()
        QGuiApplication.instance().applicationStateChanged.connect(self.on_app_state)
        self.emu_timer = QTimer(self, interval=20000, timeout=self.check_emulators)
        self.emu_timer.start()
        last = self.settings.get('last_folder')
        start = folder or (last if last and px.save_header(last) else None) or px.default_save()
        if start:
            self.load(start, quiet=True)
            if self.save and start != last and not folder:
                QTimer.singleShot(400, lambda: self.toast(f'Found your save automatically:\n{start}', 'info'))
        self.check_emulators()
        self.updates = UpdateChecker(self.settings, self)
        self.updates.found.connect(self.on_update)
        if persist:  # not in screenshot runs
            QTimer.singleShot(2500, self.updates.start)
            if self.settings.get('whats_new_seen') != VERSION_STR:
                QTimer.singleShot(700, self.show_whats_new)

    def show_whats_new(self):
        """Once per version: a short list of what changed."""
        from gui.dialogs import WhatsNew
        d = WhatsNew(self, VERSION_STR, WHATS_NEW)
        d.exec()
        self.settings['whats_new_seen'] = VERSION_STR
        self.write_settings()
        if d.open_mods and self.save:
            self.show_page('Mods')

    # ---------- updates ----------
    def on_update(self, tag, url):
        self.update_url = url
        self.st_update.setText(f'Update available: {tag}')
        self.st_update.setToolTip(f'{tag} is out. Click to open the download page.')
        self.st_update.show()
        if self.settings.get('update_toasted') != tag:
            self.settings['update_toasted'] = tag
            self.toast(f'Pokopia Editor {tag} is available.\n'
                       'Click "Update available" at the bottom right to download it.', 'info')

    def open_update(self):
        QDesktopServices.openUrl(QUrl(getattr(self, 'update_url', None) or 'https://github.com/cycalo/Pokopia-Editor/releases/latest'))

    def set_check_updates(self, on):
        self.settings['check_updates'] = bool(on)
        if on:
            self.updates.start(force=True)
        else:
            self.st_update.hide()
        self.write_settings()

    # ---------- settings ----------
    def read_settings(self):
        try:
            with open(SETTINGS, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def write_settings(self):
        if not self.persist:
            return
        self.settings['theme'] = T.NAME
        self.settings['last_folder'] = self.save.folder if self.save else self.settings.get('last_folder')
        self.settings['qt_geometry'] = bytes(self.saveGeometry().toBase64()).decode('ascii')
        try:
            with open(SETTINGS, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=1)
        except OSError:
            pass

    def restore_geometry(self):
        g = self.settings.get('qt_geometry')
        if g and self.restoreGeometry(QByteArray.fromBase64(g.encode('ascii'))):
            return
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w, h = min(1440, int(scr.width() * 0.92)), min(920, int(scr.height() * 0.9))
        self.resize(w, h)
        self.move(scr.x() + (scr.width() - w) // 2, scr.y() + (scr.height() - h) // 2)

    # ---------- layout ----------
    def build_ui(self):
        app = QApplication.instance()
        app.setStyleSheet(T.stylesheet())
        pal = app.palette()
        for role, key in ((QPalette.Window, 'bg'), (QPalette.Base, 'card2'), (QPalette.Text, 'text'),
                          (QPalette.WindowText, 'text'), (QPalette.Highlight, 'accent'), (QPalette.ToolTipBase, 'card'),
                          (QPalette.ToolTipText, 'text'), (QPalette.Button, 'card2'), (QPalette.ButtonText, 'text'),
                          (QPalette.PlaceholderText, 'faint')):
            pal.setColor(role, QColor(T.P[key]))
        app.setPalette(pal)
        old = self.centralWidget()
        root = QWidget()
        root.setObjectName('Root')
        self.setCentralWidget(root)
        if old is not None:
            old.deleteLater()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.build_sidebar())
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        outer.addLayout(main, 1)
        main.addWidget(self.build_header())
        self.stack = QStackedWidget()
        body = QHBoxLayout()
        body.setContentsMargins(24, 4, 24, 18)
        body.addWidget(self.stack)
        main.addLayout(body, 1)
        main.addWidget(self.build_status())
        self.pages = {}
        for _, classes in page_classes():
            for cls in classes:
                p = cls(self)
                self.pages[cls.nav] = p
                self.stack.addWidget(p)
        from gui.pages.welcome import WelcomePage
        self.welcome = WelcomePage(self)
        self.stack.addWidget(self.welcome)
        self.toasts = W.ToastHost(root)
        T.dark_titlebar(self, T.NAME == 'dark')
        self.show_page(self.current)
        self.update_chrome()

    def build_sidebar(self):
        side = QFrame()
        side.setObjectName('Sidebar')
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(2)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(self.assets.app(40))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        t = W.label('Pokopia', 'h2')
        names.addWidget(t)
        names.addWidget(W.label('Editor', 'small'))
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(16)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.navb = {}
        for section, classes in page_classes():
            cap = W.label(section.upper(), 'caps')
            cap.setContentsMargins(12, 10, 0, 4)
            lay.addWidget(cap)
            for cls in classes:
                b = W.QPushButton('  ' + cls.nav.replace('&', '&&'))
                b.setProperty('nav', 'true')
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.setIcon(T.glyph_icon(cls.glyph, 'muted', 18, active_key='accent'))
                b.setIconSize(QSize(18, 18))
                b.clicked.connect(lambda _=False, n=cls.nav: self.show_page(n))
                self.nav_group.addButton(b)
                lay.addWidget(b)
                self.navb[cls.nav] = b
        lay.addStretch(1)
        # player mini card
        self.side_card = QFrame()
        self.side_card.setObjectName('SubCard')
        sc = QHBoxLayout(self.side_card)
        sc.setContentsMargins(10, 10, 10, 10)
        self.side_avatar = QLabel()
        self.side_avatar.setPixmap(self.assets.villager(78, 34, circle=True))
        sc.addWidget(self.side_avatar)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.side_name = W.label('No save open', 'h3')
        self.side_info = W.label('Open a save folder', 'small', wrap=True)
        col.addWidget(self.side_name)
        col.addWidget(self.side_info)
        sc.addLayout(col, 1)
        lay.addWidget(self.side_card)
        lay.addSpacing(8)
        dark = T.NAME == 'dark'
        tb = W.button('Light theme' if dark else 'Dark theme', T.G['sun'] if dark else T.G['moon'], self.toggle_theme,
                      flat=True, glyph_color='muted')
        tb.setStyleSheet('text-align: left; padding-left: 12px;')
        lay.addWidget(tb)
        return side

    def build_header(self):
        head = QFrame()
        head.setObjectName('Header')
        lay = QHBoxLayout(head)
        lay.setContentsMargins(24, 18, 24, 12)
        lay.setSpacing(8)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        self.h_title = W.label('', 'h1')
        self.h_sub = W.label('', 'muted')
        tcol.addWidget(self.h_title)
        tcol.addWidget(self.h_sub)
        lay.addLayout(tcol, 1)
        self.b_open = W.button('Open', T.G['open'], self.open_dialog, tip='Open another save (Ctrl+O)')
        self.b_undo = W.button('', T.G['undo'], self.undo, tip='Undo (Ctrl+Z)')
        self.b_redo = W.button('', T.G['redo'], self.redo, tip='Redo (Ctrl+Y)')
        self.b_saveas = W.button('Save copy', T.G['saveas'], self.save_new,
                                 tip='Write a complete copy of the save, with your edits, into an empty folder (Ctrl+Shift+S)')
        self.b_save = W.button('Save', T.G['save'], self.save_inplace, accent=True,
                               tip='Overwrite the open save (Ctrl+S). A full backup of the folder is made first.')
        self.b_save.setMinimumWidth(96)
        for b in (self.b_open, self.b_undo, self.b_redo, self.b_saveas, self.b_save):
            lay.addWidget(b, 0, Qt.AlignVCenter)
        return head

    def build_status(self):
        bar = QFrame()
        bar.setObjectName('StatusBar')
        bar.setFixedHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(10)
        self.st_state = W.label('', 'small')
        self.st_path = W.label('', 'small')
        self.st_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.st_emu = W.Pill('')
        self.st_update = W.button('', T.G['down'], self.open_update, accent=True, small=True)
        self.st_update.hide()
        lay.addWidget(self.st_state)
        lay.addWidget(W.label('·', 'small'))
        lay.addWidget(self.st_path, 1)
        lay.addWidget(self.st_update)
        lay.addWidget(self.st_emu)
        return bar

    def shortcuts(self):
        for seq, fn in (('Ctrl+O', self.open_dialog), ('Ctrl+S', self.save_inplace), ('Ctrl+Shift+S', self.save_new),
                        ('Ctrl+Z', self.undo_key), ('Ctrl+Y', self.redo_key), ('Ctrl+Shift+Z', self.redo_key),
                        ('F5', self.reload), ('Ctrl+F', self.focus_search)):
            QShortcut(QKeySequence(seq), self, activated=fn)
        for n in range(1, 10):
            QShortcut(QKeySequence(f'Ctrl+{n}'), self, activated=lambda n=n: self.nav_index(n - 1))

    def nav_index(self, n):
        names = [cls.nav for _, cl in page_classes() for cls in cl]
        if 0 <= n < len(names) and self.save:
            self.show_page(names[n])

    def focus_search(self):
        p = self.pages.get(self.current)
        if p and self.save:
            p.focus_search()

    def undo_key(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, QLineEdit) and fw.isUndoAvailable():
            return fw.undo()
        self.undo()

    def redo_key(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, QLineEdit) and fw.isRedoAvailable():
            return fw.redo()
        self.redo()

    def toggle_theme(self):
        T.set_theme('light' if T.NAME == 'dark' else 'dark')
        T.clear_icon_cache()
        self.assets._pm.clear()
        for d in self.map_cache.values():
            getattr(d, 'composed', {}).clear()
        self.build_ui()
        self.write_settings()

    def show_page(self, name):
        if not self.save:
            self.stack.setCurrentWidget(self.welcome)
            self.h_title.setText('Welcome')
            self.h_sub.setText('Open a Pokopia save to start editing')
            self.nav_group.setExclusive(False)
            for b in self.navb.values():
                b.setChecked(False)
                b.setEnabled(False)
            self.nav_group.setExclusive(True)
            return
        for b in self.navb.values():
            b.setEnabled(True)
        self.current = name
        page = self.pages[name]
        self.navb[name].setChecked(True)
        self.stack.setCurrentWidget(page)
        self.h_title.setText(page.title)
        self.h_sub.setText(page.subtitle_text())
        if page.dirty:
            page.dirty = False
            page.refresh()

    def update_chrome(self):
        c = self.save.common if self.save else None
        edited = bool(c and c.edited)
        self.setWindowTitle(('● ' if edited else '') + 'Pokopia Editor' + (f'  —  {c.player_name}' if c else ''))
        n = len(c.history) if c else 0
        self.b_save.setEnabled(edited)
        self.b_save.setText(f'Save  ·  {n}' if edited and n else 'Save')
        self.b_undo.setEnabled(bool(c and c.history))
        self.b_redo.setEnabled(bool(c and c.can_redo))
        self.b_saveas.setEnabled(bool(c))
        if not c:
            self.st_state.setText('No save open')
            self.st_path.setText('')
            self.side_name.setText('No save open')
            self.side_info.setText('Open a save folder')
        else:
            self.st_state.setText(f'{n} unsaved edit{"s" if n != 1 else ""}' if edited else 'No unsaved changes')
            self.st_path.setText(self.save.folder)
            self.st_path.setToolTip(self.save.folder)
            pt = c.play_seconds
            self.side_name.setText(c.player_name or 'Player')
            self.side_info.setText(f'{ps.fmt_playtime(pt) if pt is not None else "?"} played\n{len(c.villagers())} residents')
        if self.emus:
            self.st_emu.set('●  ' + ', '.join(self.emus) + ' running', 'pillwarn')
            self.st_emu.setToolTip('Close the emulator before overwriting the save.')
        else:
            self.st_emu.set('●  No emulator running', 'pillok')
            self.st_emu.setToolTip('Safe to overwrite the save.')

    def data_changed(self):
        for p in self.pages.values():
            p.dirty = True
        self.update_chrome()
        self.show_page(self.current)

    def toast(self, msg, kind='ok'):
        if kind == 'err':
            QApplication.beep()
        self.toasts.show(msg, kind)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'toasts'):
            self.toasts.layout()

    # ---------- background work ----------
    def run_bg(self, kind, key, fn):
        def work():
            try:
                self.bridge.done.emit(kind, key, fn(), None)
            except Exception as ex:
                self.bridge.done.emit(kind, key, None, str(ex) or ex.__class__.__name__)
        threading.Thread(target=work, daemon=True).start()

    def on_result(self, kind, key, result, err):
        if kind == 'map':
            self.pages['Island Map'].loaded(key, result, err)
        elif kind == 'album' and self.save and key == self.save.folder:
            if err:
                self.album, self.album_state = None, f'Cannot read photos: {err}'
            else:
                self.album, self.album_thumbs = result
                self.album_state = 'ready'
            for n in ('Overview', 'Photos'):
                self.pages[n].dirty = True
            self.show_page(self.current)
        elif kind == 'emu':
            if result != self.emus:
                self.emus = result
                self.pages['Overview'].dirty = True
                self.update_chrome()
                if self.current == 'Overview':
                    self.show_page('Overview')

    def load_album(self):
        self.album, self.album_thumbs = None, []
        path = self.save.photo_file()
        if not path or px.Image is None:
            self.album_state = 'none' if px.Image is not None else 'Pillow is not installed'
            return
        self.album_state = 'loading'
        from gui.pages.photos import THUMB

        def work():
            a = px.PhotoAlbum(path)
            thumbs = []
            for i in range(len(a)):
                im = a.image(i)
                im.draft('RGB', (THUMB[0] * 2, THUMB[1] * 2))
                thumbs.append(im.convert('RGB').resize(THUMB, px.Image.LANCZOS))
            return a, thumbs
        self.run_bg('album', self.save.folder, work)

    def check_emulators(self):
        self.run_bg('emu', None, px.running_emulators)

    def on_app_state(self, state):
        if state != Qt.ApplicationActive:
            return
        self.check_emulators()
        if self.save and self.save.changed_on_disk():
            if self.save.common.edited:
                self.toast('The game saved again while you had unsaved edits. Reload (F5) before overwriting.', 'err')
            else:
                self.load(self.save.folder, quiet=True)
                self.toast('The save changed on disk and was reloaded.', 'info')

    # ---------- editing ----------
    def need(self):
        if not self.save:
            self.toast('Open a save folder first.', 'err')
            return False
        return True

    def do(self, label, fn):
        """Run one edit as an undo step. Errors roll the edit back and show as a toast."""
        if not self.need():
            return False
        c = self.save.common
        try:
            fn()
        except (ValueError, ps.FormatError) as ex:
            c.rollback()
            self.toast(str(ex), 'err')
            self.data_changed()
            return False
        if c.commit(label):
            self.toast(label, 'info')
        self.data_changed()
        return True

    def undo(self):
        label = self.save and self.save.common.undo()
        if label:
            self.toast(f'Undone: {label}', 'info')
            self.data_changed()

    def redo(self):
        label = self.save and self.save.common.redo()
        if label:
            self.toast(f'Redone: {label}', 'info')
            self.data_changed()

    # ---------- files ----------
    def open_dialog(self):
        if not self.discard_ok():
            return
        from gui.dialogs import SavePicker
        d = SavePicker(self).pick()
        if d:
            self.load(d)

    def reload(self):
        if self.save and self.discard_ok():
            self.load(self.save.folder)

    def discard_ok(self):
        if self.save and self.save.common.edited:
            r = QMessageBox.question(self, 'Unsaved edits', 'You have edits that are not saved. Discard them?',
                                     QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
            return r == QMessageBox.Discard
        return True

    def load(self, d, quiet=False):
        try:
            self.save = ps.SaveFolder(d)
        except Exception as ex:
            QMessageBox.critical(self, 'Cannot open', str(ex))
            return
        self.load_album()
        for p in self.pages.values():
            if hasattr(p, 'save_changed'):
                p.save_changed()
        if self.stack.currentWidget() is self.welcome:
            self.current = 'Overview'
        self.data_changed()
        self.write_settings()
        if not quiet:
            self.toast(f'Opened {self.save.folder}')

    def review(self, confirm=None):
        if not self.need():
            return False
        from gui.dialogs import ChangesDialog
        lines = self.save.common.pending_changes()
        return ChangesDialog(self, 'Changes to be written' if confirm else 'Pending changes', lines, confirm).run()

    def save_new(self):
        if not self.need():
            return
        if not self.save.common.edited and QMessageBox.question(
                self, 'No edits', 'Nothing has been changed. Write an identical copy anyway?') != QMessageBox.Yes:
            return
        d = QFileDialog.getExistingDirectory(self, 'Choose an EMPTY folder for the edited save')
        if not d:
            return
        try:
            t, _ = self.save.write(out_folder=d)
        except Exception as ex:
            return QMessageBox.critical(self, 'Not written', str(ex))
        self.toast(f'Written and verified: {t}\nCopy its contents over the live save when the emulator is closed.')

    def save_inplace(self):
        if not self.need():
            return
        if not self.save.common.edited:
            return self.toast('Nothing to save.', 'info')
        self.emus = px.running_emulators()
        if self.emus and QMessageBox.warning(
                self, 'Emulator running', f'{", ".join(self.emus)} is running.\n\nIf the game is open it will overwrite '
                'this file the next time it saves, and may not notice the change at all. Close it first.\n\nWrite anyway?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if not self.review('Back up and overwrite'):
            return
        try:
            t, b = self.save.write(in_place=True)
        except Exception as ex:
            return QMessageBox.critical(self, 'Not written', str(ex))
        self.load(t, quiet=True)
        self.toast(f'Saved and verified.\nBackup of the previous save: {b}')

    def closeEvent(self, e):
        if self.discard_ok():
            self.write_settings()
            e.accept()
        else:
            e.ignore()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    shot = theme = None
    if '--screenshot' in args:
        i = args.index('--screenshot')
        shot = args[i + 1]
        del args[i:i + 2]
    if '--theme' in args:
        i = args.index('--theme')
        theme = args[i + 1]
        del args[i:i + 2]
    set_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qa = QApplication.instance() or QApplication(sys.argv[:1])
    qa.setApplicationName('Pokopia Editor')
    qa.setWindowIcon(app_icon())
    qa.setFont(T.font(10))
    win = App(args[0] if args else None, theme, persist=not shot)
    win.show()
    if shot:
        from gui.shots import run_screenshots
        run_screenshots(win, shot)
    return qa.exec()
