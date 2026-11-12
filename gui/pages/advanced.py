from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QEvent
from PySide6.QtGui import QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSpinBox, QToolTip, QVBoxLayout, QWidget

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page


class FlagGrid(QWidget):
    COLS, CW, CH, GAP = 25, 36, 30, 4

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.hover = None
        rows = (ps.FLAG_COUNT + self.COLS - 1) // self.COLS
        self.setFixedSize(self.COLS * (self.CW + self.GAP), rows * (self.CH + self.GAP))
        self.setMouseTracking(True)

    def cell(self, pos):
        col, row = int(pos.x() // (self.CW + self.GAP)), int(pos.y() // (self.CH + self.GAP))
        i = row * self.COLS + col
        return i if 0 <= col < self.COLS and 1 <= i < ps.FLAG_COUNT else None

    def paintEvent(self, e):
        c = self.page.c
        if not c:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        live = self.page.unlocked
        f = T.font(7.5, QFont.DemiBold)
        p.setFont(f)
        for i in range(1, ps.FLAG_COUNT):
            x, y = (i % self.COLS) * (self.CW + self.GAP), (i // self.COLS) * (self.CH + self.GAP)
            r = QRectF(x + 0.5, y + 0.5, self.CW - 1, self.CH - 1)
            on, known = c.get_flag(i), i in ps.KNOWN_FLAGS
            if on:
                bg = T.c('accent') if live else T.c('faint')
            else:
                bg = T.c('tilehi') if i == self.hover else T.c('tile')
            p.setBrush(bg)
            p.setPen(QPen(T.c('warn') if known else T.c('line'), 1.6 if known else 1))
            p.drawRoundedRect(r, 7, 7)
            p.setPen(T.c('onaccent') if on else T.c('muted'))
            p.drawText(r, Qt.AlignCenter, str(i))

    def event(self, e):
        if e.type() == QEvent.ToolTip and self.page.c:
            i = self.cell(QPointF(e.pos()))
            if i is not None:
                QToolTip.showText(e.globalPos(), f'Flag {i}: {ps.KNOWN_FLAGS.get(i, "unknown")}  '
                                                 f'({"on" if self.page.c.get_flag(i) else "off"})', self)
            return True
        return super().event(e)

    def mouseMoveEvent(self, e):
        h = self.cell(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        i = self.cell(e.position())
        if i is not None:
            self.page.flip(i)


class AdvancedPage(Page):
    title, nav, glyph = 'Advanced', 'Advanced', T.G['settings']
    subtitle = 'Unverified raw values. Locked until you say otherwise.'
    scrollable = True

    @property
    def unlocked(self):
        return self.app.adv_unlocked

    def build(self):
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(14)
        upd = W.Card('Updates', None, T.G['bell'])
        row = W.ToggleRow('Check for new versions on GitHub',
                          'Checked each time the app starts. Only asks GitHub for the latest release; nothing about you or your save is sent.')
        row.toggle.set_quiet(self.app.settings.get('check_updates', True))
        row.toggle.toggled.connect(self.app.set_check_updates)
        upd.body.addWidget(row)
        lay.addWidget(upd)
        warn = W.Card('Handle with care', None, T.G['warn'])
        warn.title_lbl.setStyleSheet(f'color: {T.P["warn"]};')
        warn.body.addWidget(W.label('These fields are not verified. Raw flags, thank points and gift level were found by '
                                    'inspecting the save; nobody has confirmed what the game does when they are changed. '
                                    'Keep a backup.', 'muted', wrap=True))
        self.gate = W.ToggleRow('I understand, let me edit them')
        self.gate.toggle.set_quiet(self.app.adv_unlocked)
        self.gate.toggle.toggled.connect(self.set_gate)
        warn.body.addWidget(self.gate)
        lay.addWidget(warn)
        fc = W.Card('Function flags 1–249', 'Filled = on. Amber outline = behaviour known (hover for its name). Click to toggle.',
                    T.G['flag'])
        self.grid = FlagGrid(self)
        fc.body.addWidget(self.grid, 0, Qt.AlignLeft)
        lay.addWidget(fc)
        rc = W.Card('Resident values', None, T.G['people'])
        row = QHBoxLayout()
        row.setSpacing(10)
        self.who = QComboBox()
        self.who.setMinimumWidth(240)
        self.who.setIconSize(QSize(22, 22))
        self.who.currentIndexChanged.connect(self.load_res)
        row.addWidget(self.who)
        row.addSpacing(10)
        row.addWidget(W.label('Thank points'))
        self.thank = QSpinBox()
        self.thank.setRange(0, 65535)
        row.addWidget(self.thank)
        row.addSpacing(10)
        row.addWidget(W.label('Gift level'))
        self.lvl = QSpinBox()
        self.lvl.setRange(0, 255)
        row.addWidget(self.lvl)
        self.b_apply = W.button('Apply', T.G['check'], self.apply_res)
        row.addWidget(self.b_apply)
        row.addStretch(1)
        rc.body.addLayout(row)
        lay.addWidget(rc)
        lay.addStretch(1)
        self.ids = []

    def set_gate(self, on):
        self.app.adv_unlocked = on
        self.refresh()

    def flip(self, i):
        if not self.app.need():
            return
        if not self.unlocked:
            return self.app.toast('Switch on "I understand" above to edit advanced values.', 'err')
        on = not self.c.get_flag(i)
        self.app.do(f'Flag {i} {"on" if on else "off"}', lambda: self.c.set_flag(i, on))

    def refresh(self):
        c = self.c
        if not c:
            return
        self.grid.update()
        ids = c.villagers()
        if ids != self.ids:
            self.ids = ids
            cur = self.who.currentIndex()
            self.who.blockSignals(True)
            self.who.clear()
            for i in ids:
                self.who.addItem(QIcon(self.app.assets.villager(i, 22)), f'{ps.name_of(ps.VILLAGER_NAMES, i, "Resident")}  #{i}')
            self.who.blockSignals(False)
            self.who.setCurrentIndex(cur if 0 <= cur < len(ids) else 0)
        self.load_res()
        for w in (self.thank, self.lvl, self.b_apply):
            w.setEnabled(self.unlocked)

    def load_res(self, *_):
        if not self.ids or self.who.currentIndex() < 0:
            return
        v = self.c.get_villager(self.ids[self.who.currentIndex()])
        self.thank.setValue(v['thank_points'])
        self.lvl.setValue(v['present_level'])

    def apply_res(self):
        if not self.ids:
            return
        i = self.ids[self.who.currentIndex()]
        name = ps.name_of(ps.VILLAGER_NAMES, i, 'Resident')
        t, l = self.thank.value(), self.lvl.value()

        def go():
            self.c.set_thank_points(i, t)
            self.c.set_present_level(i, l)
        self.app.do(f'{name}: thank points {t}, gift level {l}', go)
