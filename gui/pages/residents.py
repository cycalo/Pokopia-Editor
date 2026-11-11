import datetime
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSize, Qt, QItemSelectionModel
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QSlider,
                               QSpinBox, QStyle, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget)

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page

COLS = ['Pokémon', 'Friendship', 'Thanks', 'Gift lvl', 'Home', 'First met']
KEYS = [lambda v: v['name'].lower(), lambda v: v['friendship'], lambda v: v['thank_points'],
        lambda v: v['present_level'], lambda v: v['home_area_name'] or '~', lambda v: v['met'] or datetime.datetime.min]


class ResidentModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.sort_col, self.sort_order = 0, Qt.AscendingOrder

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self._sort()
        self.endResetModel()

    def _sort(self):
        self.rows.sort(key=KEYS[self.sort_col], reverse=self.sort_order == Qt.DescendingOrder)

    def sort(self, col, order=Qt.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        self.sort_col, self.sort_order = col, order
        self._sort()
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return COLS[s].upper()
        if o == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def data(self, idx, role=Qt.DisplayRole):
        v = self.rows[idx.row()]
        col = idx.column()
        if role == Qt.UserRole:
            return v
        if role == Qt.DisplayRole:
            if col == 2:
                return str(v['thank_points'])
            if col == 3:
                return str(v['present_level']) + ('  🎁' if v['waiting_present'] else '')
            if col == 4:
                return v['home_area_name'] or 'No home yet'
            if col == 5:
                return v['met'].strftime('%d %b %Y') if v['met'] else 'From the start'
        if role == Qt.ForegroundRole:
            if (col == 4 and not v['home_area_name']) or (col == 5 and not v['met']):
                return T.c('muted')
        if role == Qt.ToolTipRole and col == 3 and v['waiting_present']:
            return 'A gift is waiting'
        return None


class ResidentDelegate(QStyledItemDelegate):
    def __init__(self, page):
        super().__init__()
        self.page = page

    def paint(self, p, opt, idx):
        v = idx.data(Qt.UserRole)
        col = idx.column()
        sel = bool(opt.state & QStyle.State_Selected)
        r = QRectF(opt.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(opt.rect, T.c('sel') if sel else (T.c('tilehi') if opt.state & QStyle.State_MouseOver else T.c('card')))
        p.setPen(QPen(T.c('line'), 1))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        if col == 0:
            pm = self.page.app.assets.villager(v['index'], 38, circle=True)
            p.drawPixmap(int(r.x() + 10), int(r.center().y() - 19), pm)
            p.setFont(T.font(10, QFont.DemiBold))
            p.setPen(T.c('text'))
            p.drawText(QRectF(r.x() + 58, r.y(), r.width() - 60, r.height()), Qt.AlignVCenter, v['name'])
        elif col == 1:
            f = v['friendship']
            frac = min(1.0, f / ps.FRIENDSHIP_MAX)
            bx = r.x() + 30
            bw = max(40, r.width() - 82)
            br = QRectF(bx, r.center().y() - 4, bw, 8)
            p.setPen(Qt.NoPen)
            p.setBrush(T.c('line'))
            p.drawRoundedRect(br, 4, 4)
            if frac > 0:
                fill = QRectF(br.x(), br.y(), max(8, bw * frac), 8)
                p.setBrush(T.c('accent') if f >= ps.FRIENDSHIP_MAX else T.mix('heart', 'accent', frac * 0.8))
                p.drawRoundedRect(fill, 4, 4)
            heart = T.G['heartfill'] if f >= ps.FRIENDSHIP_MAX else T.G['heart']
            p.drawPixmap(int(r.x() + 8), int(r.center().y() - 8), T.glyph_pixmap(heart, 16, T.P['heart']))
            p.setFont(T.font(9.5, QFont.DemiBold))
            p.setPen(T.c('text'))
            p.drawText(QRectF(br.right() + 8, r.y(), 44, r.height()), Qt.AlignVCenter | Qt.AlignLeft, str(f))
        else:
            p.setFont(T.font(9.5))
            fg = idx.data(Qt.ForegroundRole)
            p.setPen(fg if fg is not None else T.c('text'))
            p.drawText(r.adjusted(10, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, idx.data(Qt.DisplayRole) or '')
        p.restore()

    def sizeHint(self, opt, idx):
        return QSize(100, 52)


class ResidentsPage(Page):
    title, nav, glyph = 'Residents', 'Residents', T.G['people']
    subtitle = 'Friendship, conversations and homes of the Pokémon living with you'

    def build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        left = W.Card(padding=12)
        top = QHBoxLayout()
        self.q = W.SearchField('Filter by name')
        self.q.textChanged.connect(self.fill)
        self.q.setMaximumWidth(280)
        top.addWidget(self.q)
        self.island = QComboBox()
        self.island.currentIndexChanged.connect(self.fill)
        self.island.setMinimumWidth(190)
        top.addWidget(self.island)
        top.addStretch(1)
        self.count = W.label('', 'small')
        top.addWidget(self.count)
        top.addWidget(W.button(f'Max friendship for everyone', T.G['heartfill'], self.max_all, glyph_color='heart'))
        left.body.addLayout(top)
        self.model = ResidentModel()
        tv = self.tv = QTableView()
        tv.setModel(self.model)
        tv.setItemDelegate(ResidentDelegate(self))
        tv.setSelectionBehavior(QAbstractItemView.SelectRows)
        tv.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tv.setShowGrid(False)
        tv.setMouseTracking(True)
        tv.verticalHeader().hide()
        tv.verticalHeader().setDefaultSectionSize(52)
        tv.setSortingEnabled(True)
        tv.sortByColumn(0, Qt.AscendingOrder)
        tv.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        h = tv.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionResizeMode(QHeaderView.Interactive)
        for i, w in enumerate((180, 200, 70, 76, 150, 112)):
            tv.setColumnWidth(i, w)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setMinimumSectionSize(60)
        tv.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tv.selectionModel().selectionChanged.connect(lambda *_: self.show())
        tv.doubleClicked.connect(lambda *_: self.goto_map())
        left.body.addWidget(tv, 1)
        lay.addWidget(left, 1)
        # detail panel
        d = W.Card(padding=18)
        d.setFixedWidth(340)
        self.portrait = QLabel()
        self.portrait.setAlignment(Qt.AlignCenter)
        d.body.addWidget(self.portrait, 0, Qt.AlignHCenter)
        self.d_name = W.label('Select a resident', 'h2')
        self.d_name.setAlignment(Qt.AlignCenter)
        d.body.addWidget(self.d_name)
        self.d_sub = W.label('', 'small')
        self.d_sub.setAlignment(Qt.AlignCenter)
        d.body.addWidget(self.d_sub)
        d.body.addWidget(W.hline())
        fr_head = QHBoxLayout()
        fr_head.addWidget(W.label('FRIENDSHIP', 'caps'))
        fr_head.addStretch(1)
        self.fr_val = W.label('', 'h3')
        fr_head.addWidget(self.fr_val)
        d.body.addLayout(fr_head)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, ps.FRIENDSHIP_MAX)
        self.spin = QSpinBox()
        self.spin.setRange(0, ps.FRIENDSHIP_MAX)
        self.spin.setFixedWidth(76)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.spin.valueChanged.connect(lambda v: self.fr_val.setText(f'{v} / {ps.FRIENDSHIP_MAX}'))
        d.body.addLayout(W.hbox(self.slider, self.spin))
        self.b_apply = W.button('Apply', T.G['check'], self.apply, accent=True)
        d.body.addLayout(W.hbox(W.button('−10', slot=lambda: self.bump(-10), small=True),
                                W.button('+10', slot=lambda: self.bump(10), small=True),
                                W.button('Max', T.G['heartfill'], lambda: self.bump(10 ** 6), small=True, glyph_color='heart'),
                                None, self.b_apply))
        self.talk = W.ToggleRow('Name conversation finished', 'The talk where you name the island together')
        self.talk.toggle.toggled.connect(self.set_talk)
        d.body.addWidget(self.talk)
        d.body.addWidget(W.hline())
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        self.info = {}
        for n, key in enumerate(('Thank points', 'Gift level', 'First met', 'Play time then', 'Home', 'Position')):
            g.addWidget(W.label(key, 'muted'), n, 0, Qt.AlignTop)
            lbl = W.label('', wrap=True)
            g.addWidget(lbl, n, 1)
            self.info[key] = lbl
        g.setColumnStretch(1, 1)
        d.body.addLayout(g)
        d.body.addStretch(1)
        self.map_btn = W.button('Show home on map', T.G['map'], self.goto_map)
        d.body.addWidget(self.map_btn)
        lay.addWidget(d)
        self.detail = d

    def focus_search(self):
        self.q.setFocus()

    def save_changed(self):
        self.island.blockSignals(True)
        self.island.clear()
        self.island.addItem('All islands', None)
        st = self.app.save.stage_files() if self.app.save else {}
        for n in st:
            self.island.addItem(ps.name_of(ps.AREA_NAMES, n, 'Area'), n)
        self.island.addItem('No home yet', -1)
        self.island.blockSignals(False)

    def refresh(self):
        self.fill()

    def fill(self):
        c = self.c
        if not c:
            return
        keep = set(self.selected())
        q = self.q.text().strip().lower()
        isl = self.island.currentData()
        rows = []
        for i in c.villagers():
            v = c.get_villager(i)
            if q and q not in v['name'].lower():
                continue
            if isl == -1 and v['home_type']:
                continue
            if isl not in (None, -1) and not (v['home_type'] and v['home_area'] == isl):
                continue
            rows.append(v)
        self.model.set_rows(rows)
        self.count.setText(f'{len(rows)} resident{"s" if len(rows) != 1 else ""}')
        sm = self.tv.selectionModel()
        for r, v in enumerate(self.model.rows):
            if v['index'] in keep:
                sm.select(self.model.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.show()

    def selected(self):
        return [self.model.rows[i.row()]['index'] for i in self.tv.selectionModel().selectedRows()] if self.model.rows else []

    def show(self):
        sel, c = self.selected(), self.c
        on = bool(sel and c)
        for w in (self.slider, self.spin, self.b_apply, self.talk):
            w.setEnabled(on)
        if not on:
            self.portrait.setPixmap(self.app.assets.villager(78, 132, circle=True))
            self.d_name.setText('Select a resident')
            self.d_sub.setText('Ctrl- or Shift-click to change several at once')
            for lbl in self.info.values():
                lbl.setText('')
            self.fr_val.setText('')
            self.map_btn.setEnabled(False)
            return
        v = c.get_villager(sel[0])
        self.portrait.setPixmap(self.app.assets.villager(v['index'], 132, circle=True))
        if len(sel) == 1:
            self.d_name.setText(v['name'])
            self.d_sub.setText(f'Resident #{v["index"]}')
        else:
            self.d_name.setText(f'{len(sel)} residents')
            self.d_sub.setText('Friendship and the conversation flag apply to all of them')
        self.spin.setValue(min(v['friendship'], ps.FRIENDSHIP_MAX))
        self.talk.toggle.set_quiet(v['name_talk_done'])
        self.info['Thank points'].setText(str(v['thank_points']))
        self.info['Gift level'].setText(f'{v["present_level"]}' + ('   ·   a gift is waiting 🎁' if v['waiting_present'] else ''))
        self.info['First met'].setText(f'{v["met"]:%d %b %Y, %H:%M}' if v['met'] else 'With you from the start')
        self.info['Play time then'].setText(ps.fmt_playtime(v['met_playtime']) if v['met_playtime'] is not None else '-')
        self.info['Home'].setText(v['home_area_name'] or 'No home yet')
        self.info['Position'].setText('X {}   Y {}   Z {}'.format(*v['home_xyz']) if v['home_xyz'] else '-')
        ok = len(sel) == 1 and v['home_xyz'] and v['home_area'] in self.app.save.stage_files()
        self.map_btn.setEnabled(bool(ok))

    def bump(self, d):
        sel = self.selected()
        if not sel:
            return
        if d >= 10 ** 6:
            val = ps.FRIENDSHIP_MAX
        else:
            val = max(0, min(ps.FRIENDSHIP_MAX, self.spin.value() + d))
        self.spin.setValue(val)
        self.apply()

    def apply(self):
        sel = self.selected()
        if not sel:
            return self.app.toast('Select a resident first.', 'err')
        val = self.spin.value()
        who = self.c.get_villager(sel[0])['name'] if len(sel) == 1 else f'{len(sel)} residents'
        self.app.do(f'{who}: friendship {val}', lambda: [self.c.set_friendship(i, val) for i in sel])

    def set_talk(self, on):
        sel = self.selected()
        if sel:
            self.app.do(f'Name conversation {"done" if on else "not done"}' + (f' ({len(sel)} residents)' if len(sel) > 1 else ''),
                        lambda: [self.c.set_name_talk_done(i, on) for i in sel])

    def max_all(self):
        if not self.app.need():
            return
        low = [i for i in self.c.villagers() if self.c.get_villager(i)['friendship'] < ps.FRIENDSHIP_MAX]
        if not low:
            return self.app.toast('Everyone is already at max friendship.', 'info')
        self.app.do(f'Max friendship for {len(low)} residents', lambda: [self.c.set_friendship(i, ps.FRIENDSHIP_MAX) for i in low])

    def select_resident(self, index):
        self.q.clear()
        self.island.setCurrentIndex(0)
        self.fill()
        for r, v in enumerate(self.model.rows):
            if v['index'] == index:
                self.tv.selectRow(r)
                self.tv.scrollTo(self.model.index(r, 0), QAbstractItemView.PositionAtCenter)
                break

    def goto_map(self):
        sel = self.selected()
        if sel:
            v = self.c.get_villager(sel[0])
            if v['home_xyz'] and v['home_area'] in self.app.save.stage_files():
                self.app.pages['Island Map'].focus_home(v)
                self.app.show_page('Island Map')
