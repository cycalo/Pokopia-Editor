import os
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QFileDialog, QInputDialog, QMessageBox, QVBoxLayout

import pokopia_mods as pm
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page


class ModsPage(Page):
    title, nav, glyph = 'Mods', 'Mods', T.G['layers']
    subtitle = 'Game mods: install them into your emulator, or save them for an SD card.'
    scrollable = True

    def build(self):
        self.mods = pm.list_mods()
        self.cards = []
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        emu = W.Card('Emulator', 'Mods are installed into this emulator\'s "load" folder.', T.G['folder'], padding=14)
        self.where = QComboBox()
        self.where.currentIndexChanged.connect(lambda *_: self.refresh())
        row = W.hbox(self.where, W.button('Choose folder…', T.G['folder'], self.choose_load),
                     W.button('Open', T.G['open'], self.open_load))
        row.setStretch(0, 1)
        emu.body.addLayout(row)
        lay.addWidget(emu)
        self.fill_where()

        for mod in self.mods:
            m = mod.meta
            card = W.Card(m['name'], m.get('summary', ''), T.G['star'], padding=14)
            card.pill = W.Pill('')
            card.actions.addWidget(card.pill)
            if m.get('status') == 'experimental':
                card.actions.addWidget(W.Pill('Experimental', 'pillwarn'))
            for combo, does in m.get('controls', []):
                card.body.addWidget(W.label(f'<b>{combo}</b> — {does}'))
            card.pick = None
            if mod.choice:
                card.pick = QComboBox()
                card.pick.addItems(list(mod.options))
                card.pick.setCurrentText(mod.option)
                card.pick.currentTextChanged.connect(lambda text, mod=mod: self.pick_option(mod, text))
                row = W.hbox(W.label(mod.choice['label'] + ':'), card.pick, None)
                card.body.addLayout(row)
            for issue in m.get('known_issues', []):
                card.body.addWidget(W.label('Known issue: ' + issue, 'warn', wrap=True))
            card.body.addWidget(W.label(f'Made for Pokopia {m.get("game_update", "")} (build {mod.build_id[:16]}). '
                                        'On other versions it is not applied.', 'small', wrap=True))
            card.body.addWidget(W.label('After installing, tick it in the game\'s Properties → Add-Ons, and keep '
                                        'Enable GDB Stub off. Use the button combos only once you are in the world.',
                                        'small', wrap=True))
            card.b_install = W.button('Install', T.G['add'], lambda mod=mod: self.install(mod), accent=True)
            card.b_remove = W.button('Uninstall', T.G['delete'], lambda mod=mod: self.uninstall(mod), danger=True)
            card.body.addLayout(W.hbox(card.b_install, card.b_remove,
                                       W.button('Save as…', T.G['saveas'], lambda mod=mod: self.save_as(mod)), None))
            card.mod = mod
            self.cards.append(card)
            lay.addWidget(card)
        if not self.mods:
            lay.addWidget(W.label('No mods were found next to the program.', 'muted'))
        lay.addStretch(1)

    # ---------- emulator folder ----------
    def fill_where(self, select=None):
        self.where.blockSignals(True)
        self.where.clear()
        dirs = pm.find_load_dirs()
        custom = self.app.settings.get('mods_load_dir')
        if custom and all(os.path.normcase(custom) != os.path.normcase(d) for _, d in dirs):
            dirs.append(('chosen folder', custom))
        for name, d in dirs:
            self.where.addItem(f'{name}  —  {d}', d)
        if not dirs:
            self.where.addItem('No emulator found. Choose its "load" folder.', None)
        if select:
            i = self.where.findData(select)
            if i >= 0:
                self.where.setCurrentIndex(i)
        self.where.blockSignals(False)

    def load_dir(self):
        return self.where.currentData()

    def choose_load(self):
        d = QFileDialog.getExistingDirectory(self, 'Choose the emulator\'s "load" folder', self.load_dir() or '')
        if d:
            d = os.path.normpath(d)
            self.app.settings['mods_load_dir'] = d
            self.app.write_settings()
            self.fill_where(select=d)
            self.refresh()

    def open_load(self):
        d = self.load_dir()
        if d and os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))
        else:
            self.app.toast('That folder does not exist yet. It is created when you install a mod.', 'info')

    # ---------- mod actions ----------
    def pick_option(self, mod, text):
        mod.option = text
        self.refresh(sync_picks=False)

    def refresh(self, sync_picks=True):
        d = self.load_dir()
        for card in self.cards:
            if sync_picks and card.pick is not None and d:
                # show the option the installed copy was made for
                have = card.mod.installed_option(d)
                if have:
                    card.mod.option = have
                    card.pick.blockSignals(True)
                    card.pick.setCurrentText(have)
                    card.pick.blockSignals(False)
            st = card.mod.status(d) if d else 'missing'
            text, kind = {'installed': ('Installed', 'pillok'), 'outdated': ('Different version installed', 'pillwarn'),
                          'missing': ('Not installed', 'pill')}[st]
            card.pill.set(text, kind)
            card.pill.setMinimumWidth(card.pill.sizeHint().width())
            card.b_install.setText('Reinstall' if st == 'installed' else 'Update' if st == 'outdated' else 'Install')
            card.b_install.setEnabled(bool(d))
            card.b_remove.setEnabled(st != 'missing')

    def install(self, mod):
        d = self.load_dir()
        if not d:
            return self.app.toast('Choose your emulator\'s "load" folder first.', 'err')
        try:
            mod.write(d)
        except OSError as e:
            return self.app.toast(f'Could not install {mod.name}:\n{e}', 'err')
        self.refresh()
        self.app.toast(f'{mod.name} installed. Restart the game and tick it under Properties → Add-Ons.')

    def uninstall(self, mod):
        d = self.load_dir()
        if QMessageBox.question(self, 'Uninstall mod', f'Remove {mod.name} from\n{d}?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            mod.remove(d)
        except OSError as e:
            return self.app.toast(f'Could not remove {mod.name}:\n{e}', 'err')
        self.refresh()
        self.app.toast(f'{mod.name} removed. Restart the game for it to take effect.')

    def save_as(self, mod):
        names = list(pm.LAYOUTS.values())
        choice, ok = QInputDialog.getItem(self, 'Save mod as', 'Folder layout:', names, 0, False)
        if not ok:
            return
        layout = list(pm.LAYOUTS)[names.index(choice)]
        hint = ('the emulator\'s "load" folder' if layout == 'emulator' else 'the root of the SD card')
        d = QFileDialog.getExistingDirectory(self, f'Save {mod.name} to… (pick {hint})')
        if not d:
            return
        try:
            written = mod.write(os.path.normpath(d), layout)
        except OSError as e:
            return self.app.toast(f'Could not save {mod.name}:\n{e}', 'err')
        self.refresh()
        self.app.toast(f'Saved {len(written)} files to {d}.')
