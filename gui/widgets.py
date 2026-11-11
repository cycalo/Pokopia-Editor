"""Reusable widgets: cards, stat tiles, toggles, toasts, flow layout, search field, empty states."""
from PySide6.QtCore import (Qt, QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, QTimer,
                            QVariantAnimation, Signal, Property)
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLayout, QLineEdit, QProgressBar, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget, QWidgetItem, QStyle)

from gui import theme as T


# ---------------------------------------------------------------- small helpers
def label(text='', role=None, wrap=False, sel=False):
    w = QLabel(text)
    if role:
        w.setProperty('role', role)
    if wrap:
        w.setWordWrap(True)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        w.setSizePolicy(sp)
    else:
        w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    if sel:
        w.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return w


def set_role(w, role):
    w.setProperty('role', role)
    w.style().unpolish(w)
    w.style().polish(w)


def button(text='', glyph=None, slot=None, accent=False, danger=False, flat=False, small=False, tip=None,
           glyph_color=None, checkable=False):
    b = QPushButton(text.replace('&', '&&'))
    b.setCursor(Qt.PointingHandCursor)
    for k, v in (('accent', accent), ('danger', danger), ('flat', flat), ('small', small)):
        if v:
            b.setProperty(k, 'true')
    if glyph:
        col = glyph_color or ('onaccent' if accent else 'danger' if danger else 'text')
        b.setIcon(T.glyph_icon(glyph, col, 16))
        b.setIconSize(QSize(15, 15) if not small else QSize(13, 13))
    if not text and glyph:
        b.setProperty('icononly', 'true')
    if tip:
        b.setToolTip(tip)
    if checkable:
        b.setCheckable(True)
    if slot:
        b.clicked.connect(lambda *_: slot())
    return b


def chip(text, checkable=True, slot=None):
    b = QPushButton(text)
    b.setProperty('chip', 'true')
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(lambda *_: slot())
    return b


def hbox(*items, spacing=8, margins=(0, 0, 0, 0), parent=None):
    lay = QHBoxLayout(parent) if parent else QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        add(lay, it)
    return lay


def vbox(*items, spacing=8, margins=(0, 0, 0, 0), parent=None):
    lay = QVBoxLayout(parent) if parent else QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        add(lay, it)
    return lay


def add(lay, it):
    if it is None:
        lay.addStretch(1)
    elif isinstance(it, int):
        lay.addSpacing(it)
    elif isinstance(it, QLayout):
        lay.addLayout(it)
    else:
        lay.addWidget(it)


def wrap(layout):
    w = QWidget()
    w.setLayout(layout)
    return w


def hline():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f'background: {T.P["line"]}; border: none;')
    return f


def shadow(widget, blur=28, alpha=60, dy=6):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(T.c('shadow', alpha))
    widget.setGraphicsEffect(eff)
    return eff


# ---------------------------------------------------------------- cards
class Card(QFrame):
    """Rounded panel. `title`/`subtitle` make a header; add header widgets with `actions.addWidget`."""

    def __init__(self, title=None, subtitle=None, glyph=None, padding=16, spacing=10, parent=None):
        super().__init__(parent)
        self.setObjectName('Card')
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(padding, padding - 2, padding, padding)
        self.outer.setSpacing(spacing)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        self.title_lbl = self.sub_lbl = None
        if title is not None:
            head = QHBoxLayout()
            head.setSpacing(10)
            if glyph:
                ic = QLabel()
                ic.setPixmap(T.glyph_pixmap(glyph, 18, T.P['accent']))
                ic.setFixedSize(20, 26)
                head.addWidget(ic, 0, Qt.AlignTop)
            tl = QVBoxLayout()
            tl.setSpacing(0)
            self.title_lbl = label(title, 'h2')
            tl.addWidget(self.title_lbl)
            if subtitle is not None:
                self.sub_lbl = label(subtitle, 'muted', wrap=True)
                tl.addWidget(self.sub_lbl)
            head.addLayout(tl, 1)
            head.addLayout(self.actions)
            self.actions.setAlignment(Qt.AlignTop)
            self.outer.addLayout(head)
        self.body = self.outer

    def set_subtitle(self, text):
        if self.sub_lbl:
            self.sub_lbl.setText(text)


class StatTile(QFrame):
    def __init__(self, glyph, caption, color='accent', parent=None):
        super().__init__(parent)
        self.setObjectName('Card')
        self.color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)
        self.badge = QLabel()
        self.badge.setFixedSize(42, 42)
        self.badge.setAlignment(Qt.AlignCenter)
        col = QColor(T.P[color])
        bg = QColor(col)
        bg.setAlpha(38)
        self.badge.setStyleSheet(f'background: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()}); border-radius: 21px;')
        self.badge.setPixmap(T.glyph_pixmap(glyph, 20, col))
        lay.addWidget(self.badge, 0, Qt.AlignTop)
        col_l = QVBoxLayout()
        col_l.setSpacing(1)
        self.cap = label(caption.upper(), 'caps')
        self.val = label('-', 'big')
        self.sub = label('', 'small')
        self.sub.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.hide()
        for w in (self.cap, self.val, self.sub):
            col_l.addWidget(w)
        col_l.addSpacing(4)
        col_l.addWidget(self.bar)
        col_l.addStretch(1)
        lay.addLayout(col_l, 1)

    def set(self, value, sub='', frac=None):
        self.val.setText(str(value))
        self.sub.setText(sub)
        if frac is None:
            self.bar.hide()
        else:
            self.bar.show()
            self.bar.setValue(round(max(0.0, min(1.0, frac)) * 1000))


# ---------------------------------------------------------------- toggle switch
class Toggle(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._step)
        self.toggled.connect(self._go)

    def _go(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _step(self, v):
        self._pos = float(v)
        self.update()

    def set_quiet(self, on):
        """Set the state without emitting signals or animating."""
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 2, self.width() - 2, self.height() - 4)
        on_col, off_col = T.c('accent'), T.c('line2')
        t = self._pos
        col = T.mix(off_col, on_col, t)
        if not self.isEnabled():
            col.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.x() + 3 + (r.width() - d - 6) * t
        p.setBrush(QColor('#ffffff') if self.isEnabled() else T.c('card2'))
        p.drawEllipse(QRectF(x, r.y() + 3, d, d))


class ToggleRow(QWidget):
    """Text (+ optional muted note) on the left, a Toggle on the right."""

    def __init__(self, text, note='', parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.text = label(text)
        self.note = label(note, 'small', wrap=True)
        col.addWidget(self.text)
        col.addWidget(self.note)
        self.note.setVisible(bool(note))
        lay.addLayout(col, 1)
        self.toggle = Toggle()
        lay.addWidget(self.toggle, 0, Qt.AlignVCenter)

    def set_note(self, note):
        self.note.setText(note)
        self.note.setVisible(bool(note))


# ---------------------------------------------------------------- search field
class SearchField(QLineEdit):
    def __init__(self, placeholder='Search', parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(T.glyph_icon(T.G['search'], 'muted', 16), QLineEdit.LeadingPosition)
        self.setMinimumHeight(34)


# ---------------------------------------------------------------- empty state
class EmptyState(QWidget):
    def __init__(self, glyph, title, text='', action=None, action_text='', parent=None, pixmap=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        ic = QLabel()
        ic.setPixmap(pixmap or T.glyph_pixmap(glyph, 54, T.P['faint']))
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        t = label(title, 'h2')
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self.text = label(text, 'muted', wrap=True)
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setFixedWidth(520)
        lay.addLayout(hbox(None, self.text, None))
        if action:
            b = button(action_text, accent=True, slot=action)
            lay.addSpacing(8)
            lay.addWidget(b, 0, Qt.AlignHCenter)
        lay.addStretch(1)


# ---------------------------------------------------------------- toasts
class Toast(QFrame):
    def __init__(self, host, text, kind):
        super().__init__(host)
        col = {'ok': 'accent', 'err': 'danger', 'info': 'sky', 'warn': 'warn'}.get(kind, 'sky')
        glyph = {'ok': T.G['check'], 'err': T.G['warn'], 'info': T.G['info'], 'warn': T.G['warn']}.get(kind, T.G['info'])
        self.setStyleSheet(f'QFrame {{ background: {T.P["card"]}; border: 1px solid {T.P["line2"]}; '
                           f'border-left: 4px solid {T.P[col]}; border-radius: 10px; }} '
                           f'QLabel {{ border: none; background: transparent; }}')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(T.glyph_pixmap(glyph, 18, T.P[col]))
        lay.addWidget(ic, 0, Qt.AlignTop)
        t = QLabel(text)
        t.setWordWrap(True)
        t.setMaximumWidth(420)
        t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(t, 1)
        self.op = QGraphicsOpacityEffect(self)
        self.op.setOpacity(0.0)
        self.setGraphicsEffect(self.op)
        self.adjustSize()


class ToastHost:
    """Stacks toasts in the bottom-right corner of `host`."""

    def __init__(self, host, bottom=46):
        self.host, self.bottom, self.items = host, bottom, []

    def show(self, text, kind='ok', ms=None):
        ms = ms or (6500 if kind == 'err' else 4200)
        t = Toast(self.host, text, kind)
        t.show()
        t.raise_()
        self.items.append(t)
        self.layout()
        a = QPropertyAnimation(t.op, b'opacity', t)
        a.setDuration(180)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.start()
        QTimer.singleShot(ms, lambda: self.hide(t))
        while len(self.items) > 4:
            self.hide(self.items[0], fast=True)

    def hide(self, t, fast=False):
        if t not in self.items:
            return
        self.items.remove(t)
        try:
            a = QPropertyAnimation(t.op, b'opacity', t)
            a.setDuration(80 if fast else 260)
            a.setStartValue(t.op.opacity())
            a.setEndValue(0.0)
            a.finished.connect(t.deleteLater)
            a.start()
        except RuntimeError:
            pass
        self.layout()

    def layout(self):
        y = self.host.height() - self.bottom
        for t in reversed(self.items):
            try:
                t.adjustSize()
                y -= t.height()
                t.move(self.host.width() - t.width() - 22, y)
                y -= 8
            except RuntimeError:
                pass


# ---------------------------------------------------------------- flow layout
class FlowLayout(QLayout):
    def __init__(self, parent=None, hspacing=6, vspacing=6):
        super().__init__(parent)
        self.items = []
        self.h, self.v = hspacing, vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self.items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        for it in self.items:
            if it.widget() and not it.widget().isVisible() and not test:
                pass
            sz = it.sizeHint()
            nx = x + sz.width() + self.h
            if nx - self.h > rect.right() and line > 0:
                x, y = rect.x(), y + line + self.v
                nx, line = x + sz.width() + self.h, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x, line = nx, max(line, sz.height())
        return y + line - rect.y()


# ---------------------------------------------------------------- misc
class Avatar(QLabel):
    def __init__(self, pixmap=None, size=48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        if pixmap is not None:
            self.setPixmap(pixmap)


class Pill(QLabel):
    def __init__(self, text='', kind='pill', parent=None):
        super().__init__(text, parent)
        self.set(text, kind)

    def set(self, text, kind='pill'):
        self.setText(text)
        set_role(self, kind)
