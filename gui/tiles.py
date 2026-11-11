"""Painted tiles and wheels used by the Moves & Emotes and Wardrobe pages."""
import math
from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from gui import theme as T


def _elide2(text, fm, w):
    if fm.horizontalAdvance(text) <= w:
        return [text]
    words = text.split(' ')
    for n in range(len(words) - 1, 0, -1):
        a = ' '.join(words[:n])
        if fm.horizontalAdvance(a) <= w:
            return [a, fm.elidedText(' '.join(words[n:]), Qt.ElideRight, w)]
    return [fm.elidedText(text, Qt.ElideRight, w)]


class IconTile(QWidget):
    """Clickable tile with an icon, a title and an on/off state. Optional drag payload when on.

    style 'v': icon above the title (emotes, wardrobe). style 'h': icon left, title + note right (moves)."""
    clicked = Signal()

    def __init__(self, title, pixmap_fn, style='v', size=(104, 100), mime=None, payload=None, parent=None):
        super().__init__(parent)
        self.title, self.pixmap_fn, self.style_ = title, pixmap_fn, style
        self.note, self.badge, self.on, self.locked = '', None, False, False
        self.mime, self.payload = mime, payload
        self.hover = False
        self.press_pos = None
        if size[0] is None:
            self.setFixedHeight(size[1])
            self.setMinimumWidth(190)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setFixedSize(*size)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def set_state(self, on, note='', badge=None, locked=False, tip=None):
        self.on, self.note, self.badge, self.locked = on, note, badge, locked
        if tip is not None:
            self.setToolTip(tip)
        self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press_pos = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self.press_pos is not None and self.mime and self.on and \
                (e.position().toPoint() - self.press_pos).manhattanLength() >= QApplication.startDragDistance():
            self.press_pos = None
            md = QMimeData()
            md.setData(self.mime, QByteArray(str(self.payload).encode()))
            drag = QDrag(self)
            drag.setMimeData(md)
            pm = self.pixmap_fn(48)
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(24, 24))
            drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, e):
        if self.press_pos is not None and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        self.press_pos = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.on:
            bg = T.c('sel')
            pen = QPen(T.c('selline'), 1.6)
        else:
            bg = T.c('tilehi') if self.hover else T.c('tile')
            pen = QPen(T.c('line2') if self.hover else T.c('line'), 1)
        p.setBrush(bg)
        p.setPen(pen)
        p.drawRoundedRect(r, 12, 12)
        if self.style_ == 'v':
            s = min(int(r.height() * 0.52), int(r.width() * 0.6))
            pm = self.pixmap_fn(s)
            p.setOpacity(1.0 if self.on or self.locked else 0.42)
            p.drawPixmap(QPointF(r.center().x() - s / 2, r.y() + 8), pm)
            p.setOpacity(1.0)
            f = T.font(8.5, QFont.DemiBold if self.on else QFont.Normal)
            p.setFont(f)
            p.setPen(T.c('text') if self.on else T.c('muted'))
            lines = _elide2(self.title, QFontMetrics(f), int(r.width() - 10))
            p.drawText(QRectF(r.x() + 4, r.y() + s + 12, r.width() - 8, r.height() - s - 14),
                       Qt.AlignHCenter | Qt.AlignTop, '\n'.join(lines))
        else:
            s = int(r.height() - 16)
            pm = self.pixmap_fn(s)
            p.setOpacity(1.0 if self.on else 0.45)
            p.drawPixmap(QPointF(r.x() + 9, r.y() + 8), pm)
            p.setOpacity(1.0)
            p.setFont(T.font(10, QFont.DemiBold))
            p.setPen(T.c('text') if self.on else T.c('muted'))
            tx = r.x() + s + 20
            p.drawText(QRectF(tx, r.y() + 8, r.width() - s - 60, r.height() / 2 - 6), Qt.AlignBottom | Qt.AlignLeft, self.title)
            p.setFont(T.font(8.5))
            p.setPen(T.c('muted'))
            p.drawText(QRectF(tx, r.center().y() + 2, r.width() - s - 60, r.height() / 2 - 8), Qt.AlignTop | Qt.AlignLeft, self.note)
        # state badge
        if self.badge or self.on:
            glyph, col = self.badge or (T.G['check'], 'accent')
            d = 20
            br = QRectF(r.right() - d - 5, r.y() + 5, d, d)
            if self.style_ == 'h':
                br = QRectF(r.right() - d - 10, r.center().y() - d / 2, d, d)
            p.setBrush(T.c(col) if col in T.P else QColor(col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(br)
            gp = T.glyph_pixmap(glyph, 12, T.P['onaccent'] if col == 'accent' else '#ffffff')
            p.drawPixmap(QPointF(br.center().x() - 6, br.center().y() - 6), gp)


class RadialWheel(QWidget):
    """A wheel of N slots (the in-game move wheel). Click a slot to choose, or drop a payload on it."""
    slot_clicked = Signal(int, QPoint)
    slot_dropped = Signal(int, int)

    def __init__(self, n, mime, pixmap_fn, name_fn, size=300, parent=None):
        super().__init__(parent)
        self.n, self.mime, self.pixmap_fn, self.name_fn = n, mime, pixmap_fn, name_fn
        self.values = [0] * n
        self.hover = self.drop = None
        self.setFixedSize(size, size)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_values(self, values):
        self.values = list(values)
        self.update()

    def _geom(self):
        w = self.width()
        return QPointF(w / 2, w / 2), w / 2 - 6, w * 0.2

    def slot_at(self, pos):
        c, ro, ri = self._geom()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        dist = math.hypot(dx, dy)
        if not ri <= dist <= ro:
            return None
        ang = (math.degrees(math.atan2(dy, dx)) + 90 + 360 / self.n / 2) % 360
        return int(ang // (360 / self.n))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c, ro, ri = self._geom()
        step = 360 / self.n
        for k in range(self.n):
            start = -90 - step / 2 + k * step   # degrees, clockwise from the top
            path = QPainterPath()
            outer = QRectF(c.x() - ro, c.y() - ro, 2 * ro, 2 * ro)
            inner = QRectF(c.x() - ri, c.y() - ri, 2 * ri, 2 * ri)
            path.arcMoveTo(outer, -start)
            path.arcTo(outer, -start, -step)
            path.arcTo(inner, -(start + step), step)
            path.closeSubpath()
            v = self.values[k]
            if k == self.drop:
                bg = T.mix('sel', 'accent', 0.3)
            elif k == self.hover:
                bg = T.c('tilehi')
            elif v:
                bg = T.c('tilefill')
            else:
                bg = T.c('tile')
            p.setBrush(bg)
            p.setPen(QPen(T.c('card'), 3))
            p.drawPath(path)
            mid = math.radians(start + step / 2)
            rm = (ro + ri) / 2
            cx, cy = c.x() + rm * math.cos(mid), c.y() + rm * math.sin(mid)
            s = int(min(ro - ri - 14, 2 * math.pi * rm / self.n - 16, 56))
            if v:
                p.drawPixmap(QPointF(cx - s / 2, cy - s / 2), self.pixmap_fn(v, s))
            else:
                p.setPen(T.c('faint'))
                p.setFont(T.font(9))
                p.drawText(QRectF(cx - 20, cy - 10, 40, 20), Qt.AlignCenter, 'empty')
            # slot number near the rim
            nr = ro - 9
            p.setPen(T.c('faint'))
            p.setFont(T.font(7, QFont.Bold))
            p.drawText(QRectF(c.x() + nr * math.cos(mid) - 8, c.y() + nr * math.sin(mid) - 7, 16, 14), Qt.AlignCenter, str(k + 1))
        p.setBrush(T.c('card2'))
        p.setPen(QPen(T.c('line'), 1))
        p.drawEllipse(c, ri - 5, ri - 5)
        p.setPen(T.c('muted'))
        p.setFont(T.font(8, QFont.Bold))
        label = self.name_fn(self.values[self.hover]) if self.hover is not None and self.values[self.hover] else \
            (f'Slot {self.hover + 1}' if self.hover is not None else 'WHEEL')
        p.drawText(QRectF(c.x() - ri + 8, c.y() - 20, 2 * ri - 16, 40), Qt.AlignCenter | Qt.TextWordWrap, label)

    def mouseMoveEvent(self, e):
        h = self.slot_at(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        k = self.slot_at(e.position())
        if k is not None and e.button() == Qt.LeftButton:
            self.slot_clicked.emit(k, e.globalPosition().toPoint())

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(self.mime):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        k = self.slot_at(e.position())
        if k != self.drop:
            self.drop = k
            self.update()
        e.acceptProposedAction() if k is not None else e.ignore()

    def dragLeaveEvent(self, e):
        self.drop = None
        self.update()

    def dropEvent(self, e):
        k = self.slot_at(e.position())
        self.drop = None
        self.update()
        if k is not None and e.mimeData().hasFormat(self.mime):
            e.acceptProposedAction()
            self.slot_dropped.emit(k, int(bytes(e.mimeData().data(self.mime)).decode()))


class SlotGrid(QWidget):
    """A grid of N numbered slots (the 24-slot emote wheel). Click to choose, or drop a payload."""
    slot_clicked = Signal(int, QPoint)
    slot_dropped = Signal(int, int)

    def __init__(self, n, cols, mime, pixmap_fn, name_fn, tile=64, parent=None):
        super().__init__(parent)
        self.n, self.cols, self.mime, self.pixmap_fn, self.name_fn, self.tile = n, cols, mime, pixmap_fn, name_fn, tile
        self.values = [0] * n
        self.hover = self.drop = None
        self.gap = 8
        rows = (n + cols - 1) // cols
        self.setFixedSize(cols * tile + (cols - 1) * self.gap, rows * tile + (rows - 1) * self.gap)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_values(self, values):
        self.values = list(values)
        self.update()

    def rect_of(self, k):
        s = self.tile + self.gap
        return QRectF((k % self.cols) * s, (k // self.cols) * s, self.tile, self.tile)

    def slot_at(self, pos):
        for k in range(self.n):
            if self.rect_of(k).contains(pos):
                return k
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for k in range(self.n):
            r = self.rect_of(k).adjusted(0.5, 0.5, -0.5, -0.5)
            v = self.values[k]
            bg = T.mix('sel', 'accent', 0.3) if k == self.drop else T.c('tilehi') if k == self.hover else \
                T.c('tilefill') if v else T.c('tile')
            p.setBrush(bg)
            p.setPen(QPen(T.c('accent') if k == self.drop else T.c('line2') if v else T.c('line'), 1.4 if k == self.drop else 1,
                          Qt.DashLine if k == self.drop else Qt.SolidLine))
            p.drawRoundedRect(r, 12, 12)
            if v:
                s = int(self.tile * 0.7)
                p.drawPixmap(QPointF(r.center().x() - s / 2, r.center().y() - s / 2 - 2), self.pixmap_fn(v, s))
            p.setPen(T.c('faint'))
            p.setFont(T.font(7, QFont.Bold))
            p.drawText(QRectF(r.x() + 6, r.y() + 4, 20, 12), Qt.AlignLeft | Qt.AlignTop, str(k + 1))

    def event(self, e):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QToolTip
        if e.type() == QEvent.ToolTip:
            k = self.slot_at(QPointF(e.pos()))
            if k is not None:
                v = self.values[k]
                QToolTip.showText(e.globalPos(), f'Slot {k + 1}: {self.name_fn(v) if v else "empty"}', self)
            return True
        return super().event(e)

    def mouseMoveEvent(self, e):
        h = self.slot_at(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        k = self.slot_at(e.position())
        if k is not None and e.button() == Qt.LeftButton:
            self.slot_clicked.emit(k, e.globalPosition().toPoint())

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(self.mime):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        k = self.slot_at(e.position())
        if k != self.drop:
            self.drop = k
            self.update()
        e.acceptProposedAction() if k is not None else e.ignore()

    def dragLeaveEvent(self, e):
        self.drop = None
        self.update()

    def dropEvent(self, e):
        k = self.slot_at(e.position())
        self.drop = None
        self.update()
        if k is not None and e.mimeData().hasFormat(self.mime):
            e.acceptProposedAction()
            self.slot_dropped.emit(k, int(bytes(e.mimeData().data(self.mime)).decode()))
