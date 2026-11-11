"""Dialogs: pick a save, review pending changes."""
import html, os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QApplication)

import pokopia_extras as px
from gui import theme as T
from gui import widgets as W


def short_path(p):
    """C:\\Users\\me\\AppData\\Roaming\\eden\\... -> %APPDATA%\\eden\\... for display."""
    for var in ('APPDATA', 'LOCALAPPDATA', 'USERPROFILE'):
        base = os.environ.get(var)
        if base and os.path.normcase(p).startswith(os.path.normcase(base) + os.sep):
            return f'%{var}%' + p[len(base):]
    return p


class Dialog(QDialog):
    def __init__(self, app, title, w, h):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(title)
        self.resize(w, h)
        self.setModal(True)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(22, 18, 22, 18)
        self.lay.setSpacing(10)

    def showEvent(self, e):
        super().showEvent(e)
        T.dark_titlebar(self, T.NAME == 'dark')


class SavePicker(Dialog):
    """Lists the Pokopia saves found in the usual emulator folders, with Browse for anything else."""

    def __init__(self, app):
        super().__init__(app, 'Open a save', 900, 460)
        self.result_folder, self.found = None, []
        self.lay.addWidget(W.label('Open a save', 'h2'))
        self.info = W.label('', 'muted', wrap=True)
        self.lay.addWidget(self.info)
        self.tv = QTreeWidget()
        self.tv.setRootIsDecorated(False)
        self.tv.setHeaderLabels(['Emulator', 'Last saved', 'Status', 'Folder'])
        self.tv.setAlternatingRowColors(False)
        h = self.tv.header()
        for i, w in enumerate((100, 140, 150)):
            self.tv.setColumnWidth(i, w)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        self.tv.itemDoubleClicked.connect(lambda *_: self.ok())
        self.tv.itemSelectionChanged.connect(self.update_buttons)
        self.lay.addWidget(self.tv, 1)
        self.b_open = W.button('Open', T.G['open'], self.ok, accent=True)
        row = W.hbox(W.button('Browse for a folder…', T.G['folder'], self.browse),
                     W.button('Search again', T.G['refresh'], self.scan), None,
                     W.button('Cancel', slot=self.reject), self.b_open)
        self.lay.addLayout(row)
        self.scan()

    def pick(self):
        self.exec()
        return self.result_folder

    def fill(self, rows):
        self.found = rows
        self.tv.clear()
        current = os.path.normcase(self.app.save.folder) if self.app.save else None
        for e in rows:
            state = 'Supported' if e['supported'] else 'Other game version'
            if current == os.path.normcase(e['folder']):
                state += '  (open)'
            it = QTreeWidgetItem([e['emulator'], f"{e['saved']:%d %b %Y  %H:%M}", state, short_path(e['folder'])])
            it.setToolTip(3, e['folder'])
            if not e['supported']:
                it.setForeground(2, T.c('warn'))
            self.tv.addTopLevelItem(it)
        if rows:
            self.tv.setCurrentItem(self.tv.topLevelItem(0))

    def scan(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rows = px.find_saves()
        finally:
            QApplication.restoreOverrideCursor()
        self.fill(rows)
        if rows:
            self.info.setText(f'Found {len(rows)} Pokopia save{"s" if len(rows) != 1 else ""} in the usual emulator '
                              'folders, newest first. Pick one, or browse for another folder.')
        else:
            self.info.setText('No Pokopia save was found in the usual folders of Eden, Yuzu, Suyu, Sudachi, Citron, '
                              'Torzu or Ryujinx (including a NAND folder moved in the emulator settings). Use "Browse for '
                              f'a folder" and pick the folder that contains G00 (in yuzu-family emulators it is named '
                              f'{px.TITLE_ID}).')
        self.update_buttons()

    def update_buttons(self):
        self.b_open.setEnabled(self.tv.currentItem() is not None)

    def ok(self):
        it = self.tv.currentItem()
        if it is not None:
            self.result_folder = self.found[self.tv.indexOfTopLevelItem(it)]['folder']
            self.accept()

    def browse(self):
        start = self.app.save.folder if self.app.save else os.path.expanduser('~')
        d = QFileDialog.getExistingDirectory(self, 'Select the save folder (the one containing G00)', start)
        if not d:
            return
        d = os.path.normpath(d)
        if os.path.basename(d).upper() in ('G00', 'B00', 'S00'):
            d = os.path.dirname(d)
        if not px.save_header(d):  # an emulator or parent folder: look inside it
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                hits = px.find_saves([d], defaults=False)
            finally:
                QApplication.restoreOverrideCursor()
            if not hits:
                return QMessageBox.critical(self, 'No save there',
                                            f'No Pokopia save (a folder containing G00\\CMNDAT.BIN) was found in\n{d}')
            if len(hits) > 1:
                self.fill(hits)
                self.info.setText(f'Found {len(hits)} saves inside {d}. Pick one.')
                return
            d = hits[0]['folder']
        self.result_folder = d
        self.accept()


def change_html(lines):
    """Colour the 'old -> new' parts of change lines."""
    out = []
    for ln in lines:
        head, sep, tail = ln.partition(': ')
        if sep and ' -> ' in tail:
            old, _, new = tail.partition(' -> ')
            out.append(f'<div style="margin:3px 0"><b>{html.escape(head)}</b>&nbsp;&nbsp;'
                       f'<span style="color:{T.P["muted"]}">{html.escape(old)}</span>'
                       f'<span style="color:{T.P["faint"]}">&nbsp;&nbsp;→&nbsp;&nbsp;</span>'
                       f'<span style="color:{T.P["accent"]};font-weight:600">{html.escape(new)}</span></div>')
        elif sep:
            out.append(f'<div style="margin:3px 0"><b>{html.escape(head)}</b>: {html.escape(tail)}</div>')
        else:
            out.append(f'<div style="margin:3px 0">{html.escape(ln)}</div>')
    return ''.join(out)


class ChangesDialog(Dialog):
    def __init__(self, app, title, lines, confirm=None):
        super().__init__(app, title, 680, 520)
        self.lay.addWidget(W.label(title, 'h2'))
        self.lay.addWidget(W.label(f'{len(lines)} difference{"s" if len(lines) != 1 else ""} from the save as it was '
                                   'opened.' + (' A full backup of the save folder is made before writing.' if confirm else ''),
                                   'muted', wrap=True))
        tb = QTextBrowser()
        tb.setHtml(change_html(lines) if lines else f'<span style="color:{T.P["muted"]}">Nothing has been changed.</span>')
        self.lay.addWidget(tb, 1)
        if confirm:
            row = W.hbox(None, W.button('Cancel', slot=self.reject), W.button(confirm, T.G['save'], self.accept, accent=True))
        else:
            row = W.hbox(None, W.button('Close', slot=self.reject))
        self.lay.addLayout(row)

    def run(self):
        return self.exec() == QDialog.Accepted
