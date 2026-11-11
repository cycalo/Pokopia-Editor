import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QSplitter)

import pokopia_extras as px
import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.dialogs import change_html
from gui.pages.base import Page


class BackupsPage(Page):
    title, nav, glyph = 'Backups', 'Backups', T.G['history']
    subtitle = 'Every overwrite is backed up first. Compare and restore here.'

    def build(self):
        self.rows = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        top = W.Card('Backups', '', T.G['history'], padding=14)
        self.top = top
        top.actions.addWidget(W.button('Back up now', T.G['save'], self.backup, accent=True))
        top.actions.addWidget(W.button('Open folder', T.G['folder'], self.open_folder))
        self.tv = QTreeWidget()
        self.tv.setRootIsDecorated(False)
        self.tv.setHeaderLabels(['Saved', 'Folder', 'Player', 'Played', 'Residents', 'Bag items'])
        for i, w in enumerate((150, 300, 110, 90, 90, 80)):
            self.tv.setColumnWidth(i, w)
        self.tv.header().setStretchLastSection(True)
        self.tv.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tv.itemSelectionChanged.connect(self.sel_changed)
        self.tv.itemDoubleClicked.connect(lambda *_: self.compare())
        top.body.addWidget(self.tv, 1)
        self.b_compare = W.button('Compare with the open save', T.G['compare'], self.compare)
        self.b_restore = W.button('Restore…', T.G['restore'], self.restore, danger=True)
        top.body.addLayout(W.hbox(self.b_compare, self.b_restore, None,
                                  W.button('What changed since the game\'s last save?', T.G['info'], self.compare_b00)))
        out = W.Card('Differences', 'Pick a backup and press Compare, or ask what changed since the game\'s last save.',
                     T.G['list'], padding=14)
        self.out_card = out
        self.out = QTextBrowser()
        out.body.addWidget(self.out, 1)
        sp = QSplitter(Qt.Vertical)
        sp.addWidget(top)
        sp.addWidget(out)
        sp.setSizes([340, 420])
        sp.setHandleWidth(14)
        lay.addWidget(sp, 1)

    def refresh(self):
        self.rows = px.list_backups()
        keep = self.tv.currentIndex().row()
        self.tv.clear()
        for e in self.rows:
            it = QTreeWidgetItem([f'{e["when"]:%d %b %Y  %H:%M}', e['name'], e['player'],
                                  ps.fmt_playtime(e['playtime']) if e['playtime'] is not None else '-',
                                  str(e['residents']), str(e['items'])])
            it.setToolTip(1, e['path'])
            self.tv.addTopLevelItem(it)
        self.top.set_subtitle(f'{len(self.rows)} backup{"s" if len(self.rows) != 1 else ""} in {ps.default_backup_root()}')
        if 0 <= keep < len(self.rows):
            self.tv.setCurrentItem(self.tv.topLevelItem(keep))
        self.sel_changed()

    def sel_changed(self):
        on = self.tv.currentItem() is not None
        self.b_compare.setEnabled(on)
        self.b_restore.setEnabled(on)

    def chosen(self):
        it = self.tv.currentItem()
        if it is None:
            self.app.toast('Select a backup in the list first.', 'err')
            return None
        return self.rows[self.tv.indexOfTopLevelItem(it)]

    def show_lines(self, title, lines):
        self.out_card.set_subtitle(title)
        self.out.setHtml(change_html(lines) if lines else
                         f'<span style="color:{T.P["muted"]}">No differences in the fields this editor understands.</span>')

    def backup(self):
        if not self.app.need():
            return
        try:
            dst = px.create_backup(self.app.save.folder)
        except Exception as ex:
            return self.app.toast(f'Backup failed: {ex}', 'err')
        self.refresh()
        self.app.toast(f'Backup written: {dst}')

    def compare(self):
        e = self.chosen()
        if not e or not self.app.need():
            return
        try:
            old = ps.SaveFolder(e['path']).common
        except Exception as ex:
            return self.app.toast(str(ex), 'err')
        self.show_lines(f'From backup "{e["name"]}" to the open save (including unsaved edits)',
                        ps.describe_changes(old, self.c))

    def compare_b00(self):
        if not self.app.need():
            return
        old = self.app.save.game_backup()
        if old is None:
            return self.app.toast('This save has no readable B00 slot.', 'err')
        self.show_lines('From the game\'s previous save (B00) to the open save', ps.describe_changes(old, self.c))

    def open_folder(self):
        it = self.tv.currentItem()
        p = self.rows[self.tv.indexOfTopLevelItem(it)]['path'] if it else ps.default_backup_root()
        if os.path.isdir(p):
            os.startfile(p)

    def restore(self):
        e = self.chosen()
        app = self.app
        if not e or not app.need():
            return
        if app.emus and QMessageBox.warning(
                self, 'Emulator running', f'{", ".join(app.emus)} is running.\n\nRestoring while the game is open can be '
                'undone by the game\'s next save. Restore anyway?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        msg = (f'Replace the whole save folder\n{app.save.folder}\n\nwith backup "{e["name"]}" ({e["when"]:%d %b %Y %H:%M})?\n\n'
               'The current save is backed up first.' + ('\nUnsaved edits in the editor are discarded.' if self.c.edited else ''))
        if QMessageBox.question(self, 'Restore backup', msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            safety = px.restore_backup(e['path'], app.save.folder)
        except Exception as ex:
            return QMessageBox.critical(self, 'Not restored', str(ex))
        app.load(app.save.folder, quiet=True)
        app.toast(f'Restored. The previous save is in {safety}')
