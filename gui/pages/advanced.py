from PySide6.QtCore import QRectF, QSize, Qt, QEvent
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSizePolicy, QSpinBox, QToolTip, QVBoxLayout, QWidget

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page

UNKNOWN_GROUP = 'Not identified yet'
UNUSED_GROUP = f'Unused by the game ({ps.FLAG_UNUSED_FROM}–{ps.FLAG_COUNT - 1})'
# colour key per source of a flag's meaning
SOURCE_COLOR = {'game': 'accent', 'data': 'sky', 'guess': 'warn'}


def source_tag_width(fm, text):
    return fm.horizontalAdvance(text) + 16


def draw_tag(p, r, text, key, fm):
    col = T.c(key)
    fill = QColor(col)
    fill.setAlpha(34)
    p.setPen(QPen(col, 1))
    p.setBrush(fill)
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    p.setPen(col)
    p.drawText(r, Qt.AlignCenter, text)


def draw_switch(p, r, on, enabled):
    col = T.c('accent') if on else T.c('line2')
    if not enabled:
        col.setAlpha(120)
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    d = r.height() - 6
    x = r.right() - d - 3 if on else r.x() + 3
    p.setBrush(QColor('#ffffff') if enabled else T.c('card2'))
    p.drawEllipse(QRectF(x, r.y() + 3, d, d))


class FlagList(QWidget):
    """Grouped, searchable list of function flags. Every row shows the number, what the flag does, how sure we
    are of that, and an on/off switch. Rows flow into columns when the page is wide."""
    ROW, HEAD, GAP, MIN_COL = 40, 38, 10, 420

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.ids = []                 # flag ids to show, already filtered
        self.items = []               # ('head', rect, group, on, total) / ('flag', rect, id)
        self.hover = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @staticmethod
    def group_of(i):
        if i in ps.FLAG_INFO:
            return ps.FLAG_INFO[i][1]
        return UNUSED_GROUP if i >= ps.FLAG_UNUSED_FROM else UNKNOWN_GROUP

    def set_ids(self, ids):
        self.ids = ids
        self.relayout()

    def relayout(self):
        w = max(self.width(), 300)
        cols = max(1, min(3, (w + self.GAP) // (self.MIN_COL + self.GAP)))
        cw = (w - self.GAP * (cols - 1)) / cols
        order = ps.FLAG_GROUPS + [UNKNOWN_GROUP, UNUSED_GROUP]
        groups = {g: [] for g in order}
        for i in self.ids:
            groups[self.group_of(i)].append(i)
        c = self.page.c
        self.items, y = [], 0
        for g in order:
            ids = sorted(groups[g])
            if not ids:
                continue
            on = sum(1 for i in ids if c and c.get_flag(i))
            self.items.append(('head', QRectF(0, y, w, self.HEAD), g, on, len(ids)))
            y += self.HEAD
            rows = (len(ids) + cols - 1) // cols
            for n, i in enumerate(ids):
                col, row = n % cols, n // cols
                self.items.append(('flag', QRectF(col * (cw + self.GAP), y + row * self.ROW, cw, self.ROW - 4), i))
            y += rows * self.ROW + 8
        self.setFixedHeight(max(int(y), 60))
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            self.relayout()

    def flag_at(self, pos):
        for it in self.items:
            if it[0] == 'flag' and it[1].contains(pos):
                return it[2]
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.page.c
        if not self.items:
            p.setPen(T.c('muted'))
            p.setFont(T.font(10))
            p.drawText(self.rect(), Qt.AlignCenter, 'No flags match this filter.' if c else 'Open a save to see its flags.')
            return
        live = self.page.unlocked
        f_head, f_num = T.font(10, QFont.DemiBold), T.font(8.5, QFont.DemiBold)
        f_lab, f_tag, f_small = T.font(9.5), T.font(7.5, QFont.DemiBold), T.font(8.5)
        fm_lab, fm_tag = QFontMetrics(f_lab), QFontMetrics(f_tag)
        for it in self.items:
            if it[0] == 'head':
                _, r, g, on, total = it
                p.setFont(f_head)
                p.setPen(T.c('text'))
                p.drawText(r.adjusted(2, 0, 0, -6), Qt.AlignLeft | Qt.AlignBottom, g)
                p.setFont(f_small)
                p.setPen(T.c('muted'))
                p.drawText(r.adjusted(0, 0, -2, -6), Qt.AlignRight | Qt.AlignBottom, f'{on} of {total} on')
                p.setPen(QPen(T.c('line'), 1))
                yl = r.bottom() - 2
                p.drawLine(int(r.left()), int(yl), int(r.right()), int(yl))
                continue
            _, r, i = it
            on = bool(c and c.get_flag(i))
            info = ps.FLAG_INFO.get(i)
            p.setPen(Qt.NoPen)
            p.setBrush(T.c('tilehi') if i == self.hover else T.c('tile'))
            p.drawRoundedRect(r, 9, 9)
            # number
            nr = QRectF(r.x() + 8, r.y() + 8, 42, r.height() - 16)
            p.setBrush(T.c('sel') if on else T.c('card2'))
            p.drawRoundedRect(nr, 6, 6)
            p.setFont(f_num)
            p.setPen(T.c('accent') if on else T.c('muted'))
            p.drawText(nr, Qt.AlignCenter, str(i))
            # switch on the right, source tag left of it
            sw = QRectF(r.right() - 48, r.center().y() - 10, 38, 20)
            draw_switch(p, sw, on, live)
            right = sw.x() - 10
            if info:
                text = ps.FLAG_SOURCES[info[2]][0]
                tw = source_tag_width(fm_tag, text)
                tr = QRectF(right - tw, r.center().y() - 9, tw, 18)
                p.setFont(f_tag)
                draw_tag(p, tr, text, SOURCE_COLOR[info[2]], fm_tag)
                right = tr.x() - 10
                label, col = info[0], 'text'
            elif i >= ps.FLAG_UNUSED_FROM:
                label, col = 'Never used by the game', 'faint'
            else:
                label, col = 'Meaning not known yet', 'faint'
            lr = QRectF(nr.right() + 12, r.y(), right - nr.right() - 12, r.height())
            p.setFont(f_lab)
            p.setPen(T.c(col))
            p.drawText(lr, Qt.AlignVCenter | Qt.AlignLeft, fm_lab.elidedText(label, Qt.ElideRight, int(lr.width())))

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            i = self.flag_at(e.position() if hasattr(e, 'position') else e.pos())
            if i is not None:
                info = ps.FLAG_INFO.get(i)
                state = 'on' if self.page.c and self.page.c.get_flag(i) else 'off'
                text = (f'Flag {i}: {info[0]}\n{ps.FLAG_SOURCES[info[2]][1]}' if info else f'Flag {i}: meaning not known')
                QToolTip.showText(e.globalPos(), f'{text}\nCurrently {state}. Click to switch it.', self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def mouseMoveEvent(self, e):
        h = self.flag_at(e.position())
        if h != self.hover:
            self.hover = h
            self.setCursor(Qt.PointingHandCursor if h is not None else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        i = self.flag_at(e.position())
        if i is not None and e.button() == Qt.LeftButton:
            self.page.flip(i)


class Legend(QWidget):
    """One line explaining the source tags and the switch."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(26)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f_tag, f_txt = T.font(7.5, QFont.DemiBold), T.font(8.5)
        fm_tag, fm_txt = QFontMetrics(f_tag), QFontMetrics(f_txt)
        x = 0.0
        sw = QRectF(x, 4, 34, 18)
        draw_switch(p, sw, True, True)
        x += 40
        p.setFont(f_txt)
        p.setPen(T.c('muted'))
        t = 'flag is on in this save'
        p.drawText(QRectF(x, 0, 400, 26), Qt.AlignVCenter | Qt.AlignLeft, t)
        x += fm_txt.horizontalAdvance(t) + 22
        hints = {'game': 'checked in game', 'data': "game's code/data, not played",
                 'guess': 'likely, unconfirmed'}
        for key, (name, _) in ps.FLAG_SOURCES.items():
            tw = source_tag_width(fm_tag, name)
            p.setFont(f_tag)
            draw_tag(p, QRectF(x, 4, tw, 18), name, SOURCE_COLOR[key], fm_tag)
            x += tw + 6
            p.setFont(f_txt)
            p.setPen(T.c('muted'))
            p.drawText(QRectF(x, 0, 400, 26), Qt.AlignVCenter | Qt.AlignLeft, hints[key])
            x += fm_txt.horizontalAdvance(hints[key]) + 18
        self.setMinimumWidth(int(x))


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
        fc = W.Card('Function flags', 'Story and feature switches the game keeps in your save. Click a row to switch '
                    'that flag on or off.', T.G['flag'])
        self.flag_sum = W.label('', 'muted')
        fc.actions.addWidget(self.flag_sum)
        fc.body.addWidget(Legend())
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.flag_q = W.SearchField('Search by number or description')
        self.flag_q.setMinimumWidth(290)
        self.flag_q.setMaximumWidth(360)
        self.flag_q.textChanged.connect(lambda *_: self.fill_flags())
        bar.addWidget(self.flag_q)
        bar.addSpacing(8)
        self.flag_mode = 'known'
        self.mode_chips = {}
        for key in ('known', 'on', 'all'):
            ch = W.chip('', slot=lambda k=key: self.set_flag_mode(k))
            bar.addWidget(ch)
            self.mode_chips[key] = ch
        bar.addStretch(1)
        self.unused_chip = W.chip(f'Show unused {ps.FLAG_UNUSED_FROM}–{ps.FLAG_COUNT - 1}', slot=self.fill_flags)
        self.unused_chip.setToolTip('These flags are never read or set anywhere in the game.')
        bar.addWidget(self.unused_chip)
        fc.body.addLayout(bar)
        self.flags = FlagList(self)
        fc.body.addWidget(self.flags)
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
        for p in self.app.pages.values():
            if p is not self:
                p.dirty = True
        self.refresh()

    def set_flag_mode(self, mode):
        self.flag_mode = mode
        self.fill_flags()

    def fill_flags(self):
        c = self.c
        pool = range(1, ps.FLAG_UNUSED_FROM)
        on = [i for i in pool if c and c.get_flag(i)]
        known = [i for i in pool if i in ps.FLAG_INFO]
        names = {'known': f'With a description ({len(known)})', 'on': f'Switched on ({len(on)})',
                 'all': f'All used ({len(pool)})'}
        for k, ch in self.mode_chips.items():
            ch.setText(names[k])
            ch.setChecked(k == self.flag_mode)
        ids = list({'known': known, 'on': on, 'all': pool}[self.flag_mode])
        # the unused block is added whatever the filter, so the chip always shows it
        if self.unused_chip.isChecked():
            ids += list(range(ps.FLAG_UNUSED_FROM, ps.FLAG_COUNT))
        q = self.flag_q.text().strip().lower()
        if q:
            ids = [i for i in ids if q == str(i) or q in ps.FLAG_INFO.get(i, ('', '', ''))[0].lower()
                   or q in FlagList.group_of(i).lower()]
        total_on = sum(1 for i in range(1, ps.FLAG_COUNT) if c and c.get_flag(i))
        self.flag_sum.setText(f'{total_on} of {ps.FLAG_COUNT - 1} on  ·  {len(ps.FLAG_INFO)} described' if c else '')
        self.flags.set_ids(ids if c else [])

    def flip(self, i):
        if not self.app.need():
            return
        if not self.unlocked:
            return self.app.toast('Switch on "I understand" above to edit advanced values.', 'err')
        on = not self.c.get_flag(i)
        self.app.do(f'Flag {i} {"on" if on else "off"}', lambda: self.c.set_flag(i, on))

    def refresh(self):
        self.gate.toggle.set_quiet(self.app.adv_unlocked)
        c = self.c
        if not c:
            return
        self.fill_flags()
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
