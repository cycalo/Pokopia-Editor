import os
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QCompleter, QFileDialog, QInputDialog, QMessageBox, QVBoxLayout

import pokopia_live as pl
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
        self.game = None  # pl.Game while connected to a running game
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
            if mod.any_label:
                self.build_live(card, mod)
            card.mod = mod
            self.cards.append(card)
            lay.addWidget(card)
        if not self.mods:
            lay.addWidget(W.label('No mods were found next to the program.', 'muted'))
        lay.addStretch(1)

    # ---------- change form while playing ----------
    def build_live(self, card, mod):
        card.body.addWidget(W.hline())
        card.body.addWidget(W.label('Change Pokémon while playing', 'h3'))
        card.body.addWidget(W.label(
            'With the game running in your emulator on this PC, pick a Pokémon and press Transform. No restart '
            f'is needed. If you installed "{mod.any_label}", {mod.meta["controls"][0][0]} also turns you into the '
            'last Pokémon you picked here, or Ditto if you have not picked one.', 'small', wrap=True))
        names = list(mod.numbers)
        card.live = QComboBox()
        card.live.setEditable(True)
        card.live.setInsertPolicy(QComboBox.NoInsert)
        card.live.addItems(names)
        comp = QCompleter(names, card.live)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        card.live.setCompleter(comp)
        card.live.setMinimumWidth(190)
        last = self.app.settings.get('live_pokemon')
        card.live.setCurrentText(last if last in mod.numbers else
                                 mod.option if mod.option in mod.numbers else
                                 'Ditto' if 'Ditto' in mod.numbers else names[0])
        card.live.lineEdit().returnPressed.connect(lambda mod=mod, card=card: self.live_transform(mod, card))
        card.live_state = W.label('', 'small', wrap=True)
        card.body.addLayout(W.hbox(
            card.live,
            W.button('Transform', T.G['star'], lambda: self.live_transform(mod, card), accent=True),
            W.button('Turn back', None, lambda: self.live_transform(mod, card, back=True)), None))
        card.body.addWidget(card.live_state)

    def live_game(self, mod):
        """The running game with this mod's patch loaded; raises pl.LiveError with the reason otherwise."""
        if self.game is None or not self.game.alive():
            if self.game:
                self.game.close()
            self.game = None
            self.game = pl.connect()
        with open(mod.source('exefs'), 'rb') as f:
            if not self.game.patch_loaded(f.read()):
                raise pl.LiveError(f'The game is running without the current {mod.name} patch. Install or update '
                                   'the mod, tick it under Properties → Add-Ons, then restart the game.')
        return self.game

    def live_transform(self, mod, card, back=False):
        name = card.live.currentText().strip()
        match = next((n for n in mod.numbers if n.lower() == name.lower()), None)
        try:
            if not back and match is None:
                raise pl.LiveError(f'"{name}" is not in the list.')
            game = self.live_game(mod)
            if match is not None:
                game.select(mod.numbers[match])
            game.transform(0 if back else mod.numbers[match])
        except (pl.LiveError, OSError) as e:
            W.set_role(card.live_state, 'warn')
            card.live_state.setText(str(e))
            return
        if match is not None:
            card.live.setCurrentText(match)
            if self.app.settings.get('live_pokemon') != match:
                self.app.settings['live_pokemon'] = match
                self.app.write_settings()
        W.set_role(card.live_state, 'small')
        card.live_state.setText('Turned back into your character.' if back else f'You are now {match}.')

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
            old = bool(d and card.mod.old_installed(d))
            text, kind = {'installed': ('Installed', 'pillok'),
                          'outdated': ('Older mod installed' if old else 'Different version installed', 'pillwarn'),
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
        old = sorted({os.path.basename(os.path.dirname(os.path.dirname(p))) for p in mod.old_installed(d)})
        try:
            mod.write(d)
        except OSError as e:
            return self.app.toast(f'Could not install {mod.name}:\n{e}', 'err')
        self.refresh()
        gone = f' It replaces {" and ".join(old)}, now removed.' if old else ''
        self.app.toast(f'{mod.name} installed.{gone}\nRestart the game and tick it under Properties → Add-Ons.')

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
