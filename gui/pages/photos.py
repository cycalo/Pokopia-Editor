from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListView, QSizePolicy, QStyle,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page

THUMB = (240, 135)


def pil_to_pixmap(im):
    im = im.convert('RGB')
    q = QImage(im.tobytes('raw', 'RGB'), im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(q)


class ThumbModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.pms = []

    def set(self, pms):
        self.beginResetModel()
        self.pms = pms
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.pms)

    def data(self, idx, role=Qt.DisplayRole):
        if role == Qt.DecorationRole:
            return self.pms[idx.row()]
        if role == Qt.ToolTipRole:
            return f'Photo {idx.row() + 1}'
        return None


class ThumbDelegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        return QSize(THUMB[0] + 14, THUMB[1] + 14)

    def paint(self, p, opt, idx):
        pm = idx.data(Qt.DecorationRole)
        r = QRectF(opt.rect).adjusted(7, 7, -7, -7)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.setClipPath(path)
        p.drawPixmap(r, pm, QRectF(pm.rect()))
        p.setClipping(False)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(T.c('accent') if sel else T.c('line2') if hov else T.c('line'), 3 if sel else 1))
        p.drawRoundedRect(r, 10, 10)
        p.restore()


class Viewer(QWidget):
    def __init__(self):
        super().__init__()
        self.pm = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set(self, pm):
        self.pm = pm
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self.pm:
            return
        w, h = self.width(), self.height()
        s = min(w / self.pm.width(), h / self.pm.height())
        tw, th = self.pm.width() * s, self.pm.height() * s
        r = QRectF((w - tw) / 2, (h - th) / 2, tw, th)
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.setClipPath(path)
        p.drawPixmap(r, self.pm, QRectF(self.pm.rect()))


class PhotosPage(Page):
    title, nav, glyph = 'Photos', 'Photos', T.G['camera']
    subtitle = 'The in-game photo album'

    def build(self):
        self.full = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        left = W.Card('Album', '', T.G['photo'], padding=12)
        self.album_card = left
        self.model = ThumbModel()
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setItemDelegate(ThumbDelegate())
        self.list.setViewMode(QListView.ListMode)
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.selectionModel().currentChanged.connect(lambda idx, _: self.show(idx.row()))
        left.body.addWidget(self.list, 1)
        left.setFixedWidth(THUMB[0] + 60)
        lay.addWidget(left)
        right = W.Card(padding=14)
        head = QHBoxLayout()
        self.pos_lbl = W.label('', 'h3')
        head.addWidget(self.pos_lbl)
        head.addStretch(1)
        self.b_prev = W.button('', T.G['back'], lambda: self.step(-1), tip='Previous (←)')
        self.b_next = W.button('', T.G['next'], lambda: self.step(1), tip='Next (→)')
        head.addWidget(self.b_prev)
        head.addWidget(self.b_next)
        head.addSpacing(8)
        head.addWidget(W.button('Export this photo…', T.G['export'], lambda: self.export([self.cur()])))
        head.addWidget(W.button('Export all…', T.G['export'], lambda: self.export(None), accent=True))
        right.body.addLayout(head)
        self.viewer = Viewer()
        right.body.addWidget(self.viewer, 1)
        self.note = W.label('Exports are the original 1920 × 1080 JPEG files, not re-compressed.', 'small')
        right.body.addWidget(self.note)
        self.empty = W.EmptyState(T.G['camera'], 'No photos', '')
        right.body.addWidget(self.empty, 1)
        lay.addWidget(right, 1)

    def save_changed(self):
        self.full = {}
        self.model.set([])

    def cur(self):
        idx = self.list.currentIndex()
        return idx.row() if idx.isValid() else None

    def refresh(self):
        app = self.app
        if app.album is None:
            self.model.set([])
            msg = {'loading': 'Reading the photo album…', 'none': 'This save has no photo file.'}.get(app.album_state, app.album_state)
            self.album_card.set_subtitle(msg)
            self.empty.text.setText(msg)
            self.empty.show()
            self.viewer.hide()
            self.pos_lbl.setText('')
            return
        n = len(app.album)
        self.album_card.set_subtitle(f'{n} photo{"s" if n != 1 else ""}')
        if len(self.model.pms) != n:
            self.model.set([pil_to_pixmap(t) for t in app.album_thumbs])
        self.empty.setVisible(n == 0)
        self.viewer.setVisible(n > 0)
        if n == 0:
            self.empty.text.setText('The album is empty.')
        elif self.cur() is None:
            self.list.setCurrentIndex(self.model.index(0))
        else:
            self.show(self.cur())

    def show(self, i):
        a = self.app.album
        if a is None or i is None or not 0 <= i < len(a):
            return
        if i not in self.full:
            im = a.image(i)
            im.draft('RGB', (1920, 1080))
            self.full[i] = pil_to_pixmap(im)
        self.viewer.set(self.full[i])
        self.pos_lbl.setText(f'Photo {i + 1} of {len(a)}')
        self.b_prev.setEnabled(i > 0)
        self.b_next.setEnabled(i < len(a) - 1)

    def step(self, d):
        i = self.cur()
        if i is not None and 0 <= i + d < self.model.rowCount():
            self.list.setCurrentIndex(self.model.index(i + d))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Left:
            self.step(-1)
        elif e.key() == Qt.Key_Right:
            self.step(1)
        else:
            super().keyPressEvent(e)

    def export(self, which):
        a = self.app.album
        if a is None or not len(a) or (which is not None and which[0] is None):
            return
        d = QFileDialog.getExistingDirectory(self, 'Folder to export photos into')
        if d:
            files = a.export(d, which)
            self.app.toast(f'{len(files)} photo{"s" if len(files) != 1 else ""} exported to {d}')
