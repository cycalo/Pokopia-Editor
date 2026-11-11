"""Bag page (custom bag grid with drag and drop + item browser) and the Item Catalog page."""
import json, os, sys
from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal, QEvent
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QSpinBox,
                               QToolTip, QVBoxLayout, QWidget, QInputDialog)

import pokopia_items as pi
import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.items import ITEM_MIME, SLOT_MIME, CategoryList, ItemBrowser, drag_pixmap, item_tooltip
from gui.pages.base import Page

HERE = (os.path.join(os.path.expanduser('~'), 'Documents') if getattr(sys, 'frozen', False)  # presets default folder
        else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
COLS = 10
ROWS = ps.INV_MAIN // COLS
BAR = ps.INV_COUNT - ps.INV_MAIN


class BagGrid(QWidget):
    """The 120 main slots plus the 10-slot second bar, painted. Selection, keyboard, drag and drop."""
    selection_changed = Signal()

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.app = page.app
        self.sel, self.anchor = set(), None
        self.hover = self.drop = None
        self.press = None          # (slot or None, QPoint, modifiers)
        self.band = None           # rubber band QRect
        self.clip = []             # copied (item, count)
        self.tile, self.gap, self.x0, self.y0 = 54, 6, 0, 0
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(COLS * 44 + 20, (ROWS + 1) * 44 + 90)

    @property
    def c(self):
        return self.app.save.common if self.app.save else None

    # ---------- geometry ----------
    HEAD, BARHEAD = 26, 40

    def resizeEvent(self, e):
        w, h = self.width(), self.height()
        gap = 6
        t_w = (w - 8 - gap * (COLS - 1)) / COLS
        t_h = (h - self.HEAD - self.BARHEAD - 6 - gap * ROWS) / (ROWS + 1)
        t = int(max(38, min(t_w, t_h, 86)))
        self.tile, self.gap = t, gap
        total_w = COLS * t + (COLS - 1) * gap
        self.x0 = (w - total_w) / 2
        self.y0 = self.HEAD
        super().resizeEvent(e)

    def rect_of(self, i):
        step = self.tile + self.gap
        if i < ps.INV_MAIN:
            return QRectF(self.x0 + (i % COLS) * step, self.y0 + (i // COLS) * step, self.tile, self.tile)
        k = i - ps.INV_MAIN
        y = self.y0 + ROWS * step - self.gap + self.BARHEAD
        return QRectF(self.x0 + k * step, y, self.tile, self.tile)

    def slot_at(self, pos):
        for i in range(ps.INV_COUNT):
            if self.rect_of(i).contains(QPointF(pos)):
                return i
        return None

    # ---------- painting ----------
    def paintEvent(self, e):
        c = self.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if not c:
            return
        filled_main = sum(1 for i in range(ps.INV_MAIN) if c.get_slot(i)[0])
        filled_bar = sum(1 for i in range(ps.INV_MAIN, ps.INV_COUNT) if c.get_slot(i)[0])
        cap = T.font(8, QFont.Bold)
        p.setFont(cap)
        p.setPen(T.c('muted'))
        p.drawText(QRectF(self.x0, 0, 400, self.HEAD - 6), Qt.AlignLeft | Qt.AlignVCenter,
                   f'MAIN BAG   ·   {filled_main} / {ps.INV_MAIN}')
        bar_y = self.rect_of(ps.INV_MAIN).y()
        p.drawText(QRectF(self.x0, bar_y - self.BARHEAD + 8, 400, self.BARHEAD - 12), Qt.AlignLeft | Qt.AlignVCenter,
                   f'SECOND BAR   ·   {filled_bar} / {BAR}')
        # divider
        p.setPen(QPen(T.c('line'), 1))
        mid = bar_y - self.BARHEAD + 4
        p.drawLine(QPointF(self.x0 + 150, mid + (self.BARHEAD - 12) / 2 + 4),
                   QPointF(self.x0 + COLS * (self.tile + self.gap) - self.gap, mid + (self.BARHEAD - 12) / 2 + 4))
        rad = self.tile * 0.2
        icon = round(self.tile * 0.72)
        badge_f = T.font(8 if self.tile < 56 else 8.5, QFont.Bold)
        fm = QFontMetrics(badge_f)
        for i in range(ps.INV_COUNT):
            r = self.rect_of(i)
            iid, cnt, _ = c.get_slot(i)
            on, hov, drop = i in self.sel, i == self.hover, i == self.drop
            bar = i >= ps.INV_MAIN
            if drop:
                bg = T.mix('sel', 'accent', 0.25)
            elif on:
                bg = T.c('sel')
            elif hov:
                bg = T.c('tilehi')
            elif iid:
                bg = T.c('tilefill')
            else:
                bg = T.mix('tile', 'sky', 0.07) if bar else T.c('tile')
            p.setBrush(bg)
            if drop:
                p.setPen(QPen(T.c('accent'), 2, Qt.DashLine))
            elif on:
                p.setPen(QPen(T.c('selline'), 2))
            else:
                p.setPen(QPen(T.c('line2') if iid else T.c('line'), 1))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
            if not iid:
                continue
            pm = self.app.assets.item(iid, icon)
            p.drawPixmap(QPointF(r.center().x() - icon / 2, r.center().y() - icon / 2 - self.tile * 0.04), pm)
            t = str(cnt)
            bw = fm.horizontalAdvance(t) + 9
            br = QRectF(r.right() - bw - 3, r.bottom() - 17, bw, 15)
            p.setBrush(T.c('badge', 225))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(br, 7.5, 7.5)
            p.setFont(badge_f)
            p.setPen(T.c('warn') if cnt >= 255 else T.c('text'))
            p.drawText(br, Qt.AlignCenter, t)
        if self.band:
            p.setBrush(T.c('accent', 35))
            p.setPen(QPen(T.c('accent'), 1))
            p.drawRect(QRectF(self.band))

    # ---------- tooltips ----------
    def event(self, e):
        if e.type() == QEvent.ToolTip and self.c:
            i = self.slot_at(e.position().toPoint() if hasattr(e, 'position') else e.pos())
            if i is None:
                QToolTip.hideText()
                return True
            iid, cnt, _ = self.c.get_slot(i)
            where = f'Slot {i}' if i < ps.INV_MAIN else f'Second bar {i - ps.INV_MAIN + 1} (slot {i})'
            if iid:
                QToolTip.showText(e.globalPos(), item_tooltip(iid, None, f'<b>×{cnt}</b>  ·  {where}'), self)
            else:
                QToolTip.showText(e.globalPos(), f'{where}: empty', self)
            return True
        return super().event(e)

    # ---------- mouse ----------
    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.RightButton:
            return
        if e.button() != Qt.LeftButton:
            return
        i = self.slot_at(e.position().toPoint())
        mods = e.modifiers()
        self.press = (i, e.position().toPoint(), mods)
        if i is None:
            if not mods & (Qt.ControlModifier | Qt.ShiftModifier):
                self.sel = set()
            self.band = QRect(e.position().toPoint(), QSize(0, 0))
        elif mods & Qt.ControlModifier:
            self.sel ^= {i}
            self.anchor = i
        elif mods & Qt.ShiftModifier and self.anchor is not None:
            a, b = sorted((self.anchor, i))
            self.sel = set(range(a, b + 1))
        elif i not in self.sel:
            self.sel, self.anchor = {i}, i
        self.changed()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self.band is not None and self.press:
            self.band = QRect(self.press[1], pos).normalized()
            base = set(self.sel) if self.press[2] & (Qt.ControlModifier | Qt.ShiftModifier) else set()
            hit = {i for i in range(ps.INV_COUNT) if QRectF(self.band).intersects(self.rect_of(i))}
            self.sel = base | hit
            self.changed()
            return
        if self.press and self.press[0] is not None and e.buttons() & Qt.LeftButton and \
                (pos - self.press[1]).manhattanLength() >= QApplication.startDragDistance():
            src = self.press[0]
            self.press = None
            if self.c and self.c.get_slot(src)[0]:
                self.start_drag(src)
            return
        h = self.slot_at(pos)
        if h != self.hover:
            self.hover = h
            self.update()

    def mouseReleaseEvent(self, e):
        if self.band is not None:
            self.band = None
            self.update()
        elif self.press and self.press[0] is not None and not self.press[2] & (Qt.ControlModifier | Qt.ShiftModifier):
            i = self.press[0]
            if len(self.sel) > 1 and i in self.sel:
                self.sel, self.anchor = {i}, i
                self.changed()
        self.press = None

    def mouseDoubleClickEvent(self, e):
        i = self.slot_at(e.position().toPoint())
        if i is not None:
            self.page.put([i])

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def contextMenuEvent(self, e):
        i = self.slot_at(e.pos())
        if i is None or not self.c:
            return
        if i not in self.sel:
            self.sel, self.anchor = {i}, i
            self.changed()
        self.page.slot_menu(e.globalPos())

    def changed(self):
        self.update()
        self.selection_changed.emit()

    # ---------- drag source ----------
    def start_drag(self, src):
        iid, cnt, _ = self.c.get_slot(src)
        sel = sorted(self.sel) if src in self.sel else [src]
        md = QMimeData()
        md.setData(SLOT_MIME, QByteArray(f'{src};{",".join(map(str, sel))}'.encode()))
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.setPixmap(drag_pixmap(self.app.assets, iid, cnt, 52))
        drag.setHotSpot(QPoint(26, 26))
        drag.exec(Qt.MoveAction | Qt.CopyAction, Qt.MoveAction)
        self.drop = None
        self.update()

    # ---------- drop target ----------
    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(ITEM_MIME) or md.hasFormat(SLOT_MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        md = e.mimeData()
        i = self.slot_at(e.position().toPoint())
        if i != self.drop:
            self.drop = i
            self.update()
        if i is None:
            e.ignore()
            return
        if md.hasFormat(SLOT_MIME):
            e.setDropAction(Qt.CopyAction if e.modifiers() & Qt.ControlModifier else Qt.MoveAction)
            e.accept()
        else:
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.drop = None
        self.update()

    def dropEvent(self, e):
        md = e.mimeData()
        i = self.slot_at(e.position().toPoint())
        self.drop = None
        self.update()
        if i is None:
            return e.ignore()
        if md.hasFormat(ITEM_MIME):
            item = int(bytes(md.data(ITEM_MIME)).decode())
            e.acceptProposedAction()
            self.page.drop_item(item, i)
        elif md.hasFormat(SLOT_MIME):
            src = int(bytes(md.data(SLOT_MIME)).decode().split(';')[0])
            copy = bool(e.modifiers() & Qt.ControlModifier)
            e.setDropAction(Qt.CopyAction if copy else Qt.MoveAction)
            e.accept()
            self.page.drop_slot(src, i, copy)
        self.setFocus()

    # ---------- keyboard ----------
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        moves = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -COLS, Qt.Key_Down: COLS}
        if k in moves:
            cur = self.anchor if self.anchor is not None else 0
            if self.sel and self.anchor is None:
                cur = min(self.sel)
            nxt = cur + moves[k]
            if cur >= ps.INV_MAIN and k == Qt.Key_Up:
                nxt = ps.INV_MAIN - COLS + (cur - ps.INV_MAIN)
            elif cur >= ps.INV_MAIN - COLS and cur < ps.INV_MAIN and k == Qt.Key_Down:
                nxt = ps.INV_MAIN + (cur % COLS)
            nxt = max(0, min(ps.INV_COUNT - 1, nxt))
            if mods & Qt.ShiftModifier and self.sel:
                self.sel.add(nxt)
            else:
                self.sel = {nxt}
            self.anchor = nxt
            self.changed()
        elif k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.page.clear()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self.page.put()
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            self.page.nudge(+1)
        elif k == Qt.Key_Minus:
            self.page.nudge(-1)
        elif e.matches(QKeySequence.SelectAll):
            self.page.select_filled()
        elif e.matches(QKeySequence.Copy):
            self.copy()
        elif e.matches(QKeySequence.Paste):
            self.page.paste(self.clip)
        elif k == Qt.Key_Escape:
            self.sel = set()
            self.changed()
        else:
            super().keyPressEvent(e)

    def copy(self):
        if not self.c:
            return
        self.clip = [self.c.get_slot(s)[:2] for s in sorted(self.sel) if self.c.get_slot(s)[0]]
        if self.clip:
            self.app.toast(f'Copied {len(self.clip)} slot{"s" if len(self.clip) != 1 else ""}. Select a slot and press Ctrl+V.', 'info')


class AmountBox(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        self.spin = QSpinBox()
        self.spin.setRange(1, 255)
        self.spin.setValue(99)
        self.spin.setMinimumWidth(70)
        lay.addWidget(self.spin)
        for n in (1, 10, 50, 99, 255):
            b = W.chip(str(n), checkable=False, slot=lambda n=n: self.spin.setValue(n))
            lay.addWidget(b)
        lay.addStretch(1)

    def value(self):
        return self.spin.value()


class BagPage(Page):
    title, nav, glyph = 'Bag', 'Bag', T.G['bag']
    subtitle = 'Drag items in from the browser, drag slots to swap them'

    def build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        # left: the bag
        bagc = W.Card('Your bag', None, T.G['bag'], padding=14)
        self.count_pill = W.Pill('')
        bagc.actions.addWidget(self.count_pill)
        more = W.button('Bag tools', T.G['more'], small=True)
        m = QMenu(more)
        m.addAction(T.glyph_icon(T.G['sort']), 'Sort by item ID', lambda: self.app.do('Sort bag by ID', lambda: self.c.sort_main()))
        m.addAction(T.glyph_icon(T.G['sort']), 'Sort A–Z', lambda: self.app.do('Sort bag by name', lambda: self.c.sort_main(True)))
        m.addSeparator()
        m.addAction(T.glyph_icon(T.G['check']), 'Select all filled slots', self.select_filled)
        m.addAction(T.glyph_icon(T.G['add']), 'All stacks to the chosen amount', self.fill_all)
        m.addSeparator()
        m.addAction(T.glyph_icon(T.G['save']), 'Save bag preset…', self.save_preset)
        m.addAction(T.glyph_icon(T.G['open']), 'Load bag preset…', self.load_preset)
        more.setMenu(m)
        bagc.actions.addWidget(more)
        self.grid = BagGrid(self)
        self.grid.selection_changed.connect(self.show_selection)
        bagc.body.addWidget(self.grid, 1)
        bagc.body.addWidget(W.label('Click, Ctrl- or Shift-click, or drag across empty space to select.  Drag a slot onto '
                                    'another to swap (hold Ctrl to copy), or onto the item list to remove it.  '
                                    'Del clears · +/− changes the amount · Ctrl+C / Ctrl+V copy slots.', 'small', wrap=True))
        lay.addWidget(bagc, 3)
        # right column
        right = QVBoxLayout()
        right.setSpacing(12)
        selc = W.Card(padding=14)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.sel_icon = QLabel()
        self.sel_icon.setFixedSize(60, 60)
        self.sel_icon.setAlignment(Qt.AlignCenter)
        self.sel_icon.setStyleSheet(f'background: {T.P["tile"]}; border: 1px solid {T.P["line"]}; border-radius: 12px;')
        row.addWidget(self.sel_icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.sel_title = W.label('', 'h3')
        self.sel_sub = W.label('', 'small', wrap=True)
        col.addWidget(self.sel_title)
        col.addWidget(self.sel_sub)
        row.addLayout(col, 1)
        selc.body.addLayout(row)
        right.addWidget(selc)
        brc = W.Card('Items', None, T.G['grid'], padding=14)
        self.browser = ItemBrowser(self.app, compact=True, icon_size=38)
        self.browser.picked.connect(self.picked)
        self.browser.activated.connect(lambda i: self.put())
        self.browser.view.slots_dropped.connect(self.clear_slots)
        brc.body.addWidget(self.browser, 1)
        right.addWidget(brc, 1)
        act = W.Card(padding=14)
        act.body.addWidget(W.label('AMOUNT', 'caps'))
        self.amount = AmountBox()
        act.body.addWidget(self.amount)
        self.b_put = W.button('Put in selected', T.G['add'], self.put, accent=True)
        act.body.addLayout(W.hbox(self.b_put, W.button('Add to first empty', T.G['bag'], self.add)))
        act.body.addLayout(W.hbox(W.button('Set amount only', T.G['edit'], self.set_count),
                                  W.button('Clear', T.G['delete'], self.clear, danger=True), None))
        right.addWidget(act)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(420)
        right.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(rw)

    def save_changed(self):
        self.grid.sel = set()
        self.browser.save_changed()

    def focus_search(self):
        self.browser.focus_search()

    def refresh(self):
        c = self.c
        if not c:
            return
        n = len(c.filled_slots())
        self.count_pill.set(f'{n} / {ps.INV_COUNT} filled')
        self.grid.update()
        self.show_selection()

    @property
    def pick(self):
        return self.browser.current_id()

    def picked(self, i):
        self.b_put.setText(f'Put {ps.item_name(i)}' if len(ps.item_name(i)) < 22 else 'Put in selected')
        if not self.grid.sel:
            self.show_selection()

    def show_selection(self):
        c, sel = self.c, sorted(self.grid.sel)
        if not c:
            return
        if not sel:
            i = self.pick
            if i:
                self.sel_icon.setPixmap(self.app.assets.item(i, 48))
                self.sel_title.setText(ps.item_name(i))
                self.sel_sub.setText(f'Chosen in the list · ID {i} · {pi.CAT_LABEL[pi.category(i)]}\n'
                                     'Select slots, then Put — or drag it onto the bag.')
            else:
                self.sel_icon.setPixmap(T.glyph_pixmap(T.G['bag'], 26, T.P['faint']))
                self.sel_title.setText('Nothing selected')
                self.sel_sub.setText('Click a slot, or pick an item on the right and drag it into the bag.')
            return
        if len(sel) == 1:
            s = sel[0]
            iid, cnt, _ = c.get_slot(s)
            where = f'Slot {s}' if s < ps.INV_MAIN else f'Second bar {s - ps.INV_MAIN + 1}'
            if iid:
                self.sel_icon.setPixmap(self.app.assets.item(iid, 48))
                self.sel_title.setText(f'{ps.item_name(iid)}  ×{cnt}')
                self.sel_sub.setText(f'{where} · Item ID {iid} · {pi.CAT_LABEL[pi.category(iid)]}')
            else:
                self.sel_icon.setPixmap(T.glyph_pixmap(T.G['add'], 24, T.P['faint']))
                self.sel_title.setText(f'{where}: empty')
                self.sel_sub.setText('Drag an item here, or choose one on the right and press Put.')
        else:
            filled = [s for s in sel if c.get_slot(s)[0]]
            self.sel_icon.setPixmap(T.glyph_pixmap(T.G['check'], 26, T.P['accent']))
            self.sel_title.setText(f'{len(sel)} slots selected')
            self.sel_sub.setText(f'{len(filled)} filled, {len(sel) - len(filled)} empty. Put fills all of them; '
                                 'dropping an item on a selected slot does too.')

    # ---------- actions ----------
    def _n(self, n):
        return f'{n} slot{"s" if n != 1 else ""}'

    def put(self, slots=None):
        if not self.app.need():
            return
        item = self.pick
        if not item:
            return self.app.toast('Choose an item in the list first.', 'err')
        sel = sorted(slots if slots is not None else self.grid.sel)
        if not sel:
            return self.add()
        n = self.amount.value()
        self.app.do(f'{ps.item_name(item)} ×{n} into {self._n(len(sel))}',
                    lambda: [self.c.set_slot(s, item, n) for s in sel])

    def add(self):
        if not self.app.need():
            return
        item = self.pick
        if not item:
            return self.app.toast('Choose an item in the list first.', 'err')
        box = []
        n = self.amount.value()
        if self.app.do(f'Add {ps.item_name(item)} ×{n}', lambda: box.append(self.c.add_item(item, n))) and box:
            self.grid.sel, self.grid.anchor = {box[0]}, box[0]
            self.grid.changed()

    def drop_item(self, item, slot):
        c = self.c
        n = self.amount.value()
        name = ps.item_name(item)
        if slot in self.grid.sel and len(self.grid.sel) > 1:
            sel = sorted(self.grid.sel)
            self.app.do(f'{name} ×{n} into {self._n(len(sel))}', lambda: [c.set_slot(s, item, n) for s in sel])
            return
        iid, cnt, _ = c.get_slot(slot)
        if iid == item:
            total = min(255, cnt + n)
            if total == cnt:
                return self.app.toast(f'{name} is already a full stack (255).', 'info')
            self.app.do(f'{name} stack {cnt} → {total}', lambda: c.set_count(slot, total))
        else:
            self.app.do(f'{name} ×{n} into slot {slot}', lambda: c.set_slot(slot, item, n))
        self.grid.sel, self.grid.anchor = {slot}, slot
        self.grid.changed()

    def drop_slot(self, src, dst, copy):
        if src == dst:
            return
        c = self.c
        if copy:
            iid, cnt, _ = c.get_slot(src)
            self.app.do(f'Copy slot {src} to {dst}', lambda: c.set_slot(dst, iid, cnt))
        else:
            self.app.do(f'Swap slots {src} and {dst}', lambda: c.swap_slots(src, dst))
        self.grid.sel, self.grid.anchor = {dst}, dst
        self.grid.changed()

    def clear_slots(self, slots):
        c = self.c
        slots = [s for s in slots if c and c.get_slot(s)[0]]
        if slots:
            self.app.do(f'Remove {self._n(len(slots))} from the bag', lambda: [c.set_slot(s, 0, 0) for s in slots])
            self.grid.sel = set()
            self.grid.changed()

    def clear(self):
        self.clear_slots(sorted(self.grid.sel))

    def set_count(self, n=None):
        sel = [s for s in sorted(self.grid.sel) if self.c and self.c.get_slot(s)[0]]
        if not sel:
            return self.app.toast('Select at least one filled slot.', 'err')
        n = self.amount.value() if n is None else n
        self.app.do(f'Amount {n} for {self._n(len(sel))}', lambda: [self.c.set_count(s, n) for s in sel])

    def nudge(self, d):
        c = self.c
        sel = [s for s in sorted(self.grid.sel) if c and c.get_slot(s)[0]]
        if not sel:
            return
        new = {s: max(1, min(255, c.get_slot(s)[1] + d)) for s in sel}
        if all(new[s] == c.get_slot(s)[1] for s in sel):
            return
        self.app.do(f'Amount {"+" if d > 0 else "−"}1 for {self._n(len(sel))}', lambda: [c.set_count(s, new[s]) for s in sel])

    def fill_all(self):
        if not self.app.need():
            return
        n = self.amount.value()
        self.app.do(f'All stacks to {n}', lambda: [self.c.set_count(s, n) for s in self.c.filled_slots()])

    def select_filled(self):
        if self.c:
            self.grid.sel = set(self.c.filled_slots())
            self.grid.changed()

    def duplicate(self):
        sel = [s for s in sorted(self.grid.sel) if self.c.get_slot(s)[0]]
        if sel:
            self.app.do(f'Copy {self._n(len(sel))} into empty slots',
                        lambda: [self.c.add_item(*self.c.get_slot(s)[:2]) for s in sel])

    def paste(self, clip):
        if not clip or not self.app.need():
            return
        start = min(self.grid.sel) if self.grid.sel else self.c.first_empty()
        if start is None:
            return self.app.toast('Select where to paste first.', 'err')
        dst = list(range(start, min(ps.INV_COUNT, start + len(clip))))

        def go():
            for s, (iid, cnt) in zip(dst, clip):
                self.c.set_slot(s, iid, cnt)
        self.app.do(f'Paste {self._n(len(dst))} at slot {start}', go)
        self.grid.sel = set(dst)
        self.grid.changed()

    def slot_menu(self, pos):
        m = QMenu(self)
        item = self.pick
        sel = sorted(self.grid.sel)
        filled = [s for s in sel if self.c.get_slot(s)[0]]
        a = m.addAction(T.glyph_icon(T.G['add']), f'Put {ps.item_name(item)} here' if item else 'Put chosen item here', self.put)
        a.setEnabled(bool(item))
        m.addAction(T.glyph_icon(T.G['edit']), f'Set amount to {self.amount.value()}', self.set_count).setEnabled(bool(filled))
        m.addAction('Full stack (255)', lambda: self.set_count(255)).setEnabled(bool(filled))
        m.addAction(T.glyph_icon(T.G['copy']), 'Copy into empty slots', self.duplicate).setEnabled(bool(filled))
        m.addAction('Copy (Ctrl+C)', self.grid.copy).setEnabled(bool(filled))
        m.addAction('Paste (Ctrl+V)', lambda: self.paste(self.grid.clip)).setEnabled(bool(self.grid.clip))
        if len(filled) == 1:
            iid = self.c.get_slot(filled[0])[0]
            m.addAction(T.glyph_icon(T.G['search']), 'Show in item list', lambda: self.browser.select(iid))
        m.addSeparator()
        m.addAction(T.glyph_icon(T.G['check']), 'Select all filled slots', self.select_filled)
        m.addAction(T.glyph_icon(T.G['delete'], 'danger'), 'Clear', self.clear).setEnabled(bool(filled))
        m.exec(pos)

    def save_preset(self):
        if not self.app.need():
            return
        f, _ = QFileDialog.getSaveFileName(self, 'Save bag preset', os.path.join(HERE, 'bag_preset.json'), 'Bag preset (*.json)')
        if f:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(self.c.export_bag(), fh, indent=1, ensure_ascii=False)
            self.app.toast(f'Preset saved: {f}')

    def load_preset(self):
        if not self.app.need():
            return
        f, _ = QFileDialog.getOpenFileName(self, 'Load bag preset', HERE, 'Bag preset (*.json)')
        if not f:
            return
        try:
            with open(f, encoding='utf-8') as fh:
                entries = json.load(fh)
        except Exception as ex:
            return self.app.toast(f'Cannot read preset: {ex}', 'err')
        self.app.do(f'Load bag preset ({len(entries)} items)', lambda: self.c.import_bag(entries))


class DropZone(QFrame):
    dropped = Signal(int)

    def __init__(self, text):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(64)
        self.text, self.hot = text, False

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(ITEM_MIME):
            self.hot = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.hot = False
        self.update()

    def dropEvent(self, e):
        self.hot = False
        self.update()
        if e.mimeData().hasFormat(ITEM_MIME):
            e.acceptProposedAction()
            self.dropped.emit(int(bytes(e.mimeData().data(ITEM_MIME)).decode()))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(T.c('accent', 40 if self.hot else 14))
        p.setPen(QPen(T.c('accent') if self.hot else T.c('line2'), 1.5, Qt.DashLine))
        p.drawRoundedRect(r, 12, 12)
        p.setPen(T.c('accent') if self.hot else T.c('muted'))
        p.setFont(T.font(9.5, QFont.DemiBold))
        p.drawText(r, Qt.AlignCenter, self.text)


class CatalogPage(Page):
    title, nav, glyph = 'Item Catalog', 'Item Catalog', T.G['grid']
    subtitle = 'Browse every item by type'

    def build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        cats = W.Card('Categories', None, T.G['filter'], padding=12)
        self.cats = CategoryList()
        cats.body.addWidget(self.cats, 1)
        cats.body.addWidget(W.label('Categories are worked out from item names and whether an item can be placed; '
                                    'the game\'s own groups are not known.', 'small', wrap=True))
        cats.setFixedWidth(262)
        lay.addWidget(cats)
        mid = W.Card(padding=14)
        self.browser = ItemBrowser(self.app, compact=False, icon_size=58)
        self.cats.chosen.connect(self.browser.set_category)
        self.browser.picked.connect(self.show_item)
        self.browser.activated.connect(lambda i: self.add_to_bag(i))
        mid.body.addWidget(self.browser, 1)
        lay.addWidget(mid, 1)
        det = W.Card(padding=16)
        det.setFixedWidth(300)
        self.big = QLabel()
        self.big.setFixedSize(150, 150)
        self.big.setAlignment(Qt.AlignCenter)
        self.big.setStyleSheet(f'background: {T.P["tile"]}; border: 1px solid {T.P["line"]}; border-radius: 22px;')
        det.body.addWidget(self.big, 0, Qt.AlignHCenter)
        self.d_name = W.label('Pick an item', 'h2', wrap=True)
        self.d_name.setAlignment(Qt.AlignCenter)
        det.body.addWidget(self.d_name)
        self.d_cat = W.Pill('')
        det.body.addWidget(self.d_cat, 0, Qt.AlignHCenter)
        self.d_info = W.label('', 'muted', wrap=True)
        det.body.addWidget(self.d_info)
        det.body.addStretch(1)
        det.body.addWidget(W.label('AMOUNT', 'caps'))
        self.amount = QSpinBox()
        self.amount.setRange(1, 255)
        self.amount.setValue(99)
        det.body.addWidget(self.amount)
        self.b_add = W.button('Add to bag', T.G['add'], lambda: self.add_to_bag(self.browser.current_id()), accent=True)
        det.body.addWidget(self.b_add)
        zone = DropZone('Drop an item here to add it to your bag')
        zone.dropped.connect(self.add_to_bag)
        det.body.addWidget(zone)
        lay.addWidget(det)

    def save_changed(self):
        self.browser.save_changed()

    def focus_search(self):
        self.browser.focus_search()

    def refresh(self):
        i = self.browser.current_id()
        self.show_item(i) if i else self.show_item(0)

    def show_item(self, i):
        c = self.c
        if not i:
            self.big.setPixmap(T.glyph_pixmap(T.G['grid'], 48, T.P['faint']))
            self.d_name.setText('Pick an item')
            self.d_cat.hide()
            self.d_info.setText('Double-click an item to add it to your bag, or drag it onto the drop zone below.')
            self.b_add.setEnabled(False)
            return
        self.b_add.setEnabled(True)
        self.big.setPixmap(self.app.assets.item(i, 120))
        self.d_name.setText(ps.item_name(i))
        cat = pi.category(i)
        self.d_cat.show()
        self.d_cat.set(f'{pi.CAT_GLYPH[cat]}  {pi.CAT_LABEL[cat]}')
        lines = [f'Item ID {i}']
        size = pi.placeable(i)
        lines.append(f'Placeable: {size[0]} × {size[2]} blocks, {size[1]} high' if size else 'Not placeable on islands')
        d = pi.duplicate_count(i)
        if d > 1:
            lines.append(f'{d} items share this name')
        if c:
            lines.append('✔  In your item catalog' if c.catalog_state(i) else 'Not obtained yet (item catalog)')
            slots = [s for s in c.filled_slots() if c.get_slot(s)[0] == i]
            if slots:
                total = sum(c.get_slot(s)[1] for s in slots)
                lines.append(f'In your bag: {total} in {len(slots)} slot{"s" if len(slots) != 1 else ""}')
            else:
                lines.append('Not in your bag')
        if not pi.has_icon(i):
            lines.append('No game icon is available for this item; the tile is generated.')
        self.d_info.setText('\n'.join(lines))

    def add_to_bag(self, i):
        if not i or not self.app.need():
            return
        n = self.amount.value()
        self.app.do(f'Add {ps.item_name(i)} ×{n}', lambda: self.c.add_item(i, n))
