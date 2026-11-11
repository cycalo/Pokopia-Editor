"""Island map: zoomable terrain with relief, contours, placed objects and resident homes."""
import math
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation, QEasingCurve, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QStyleOptionGraphicsItem, QVBoxLayout, QWidget, QGridLayout)

import pokopia_extras as px
import pokopia_items as pi
import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page

ICON_ZOOM = 5.0   # draw object icons from this many screen pixels per block


def pil_to_qimage(im):
    im = im.convert('RGB')
    return QImage(im.tobytes('raw', 'RGB'), im.width, im.height, im.width * 3, QImage.Format_RGB888).copy()


class ObjectIcons(QGraphicsItem):
    """Item icons and outlines for placed objects, drawn only when zoomed in and only where visible."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)
        self.setZValue(2)

    def boundingRect(self):
        d = self.page.data
        return QRectF(0, 0, d.m.width, d.m.height) if d else QRectF()

    def paint(self, p, opt, widget=None):
        d = self.page.data
        s = p.worldTransform().m11()
        if not d or s < ICON_ZOOM:
            return
        r = opt.exposedRect
        m = d.m
        assets = self.page.app.assets
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 110), 0)
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        for var, item, x0, z0, x1, z1, y, hh, drn in d.parts_in(r.left(), r.top(), r.right(), r.bottom()):
            rect = QRectF(x0 - m.x0, z0 - m.z0, x1 - x0 + 1, z1 - z0 + 1)
            if rect.width() * rect.height() > 1:
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect.adjusted(0.06, 0.06, -0.06, -0.06), 0.18, 0.18)
            if item and min(rect.width(), rect.height()) * s >= 8:
                side = min(rect.width(), rect.height()) * 0.9
                px_size = max(16, min(96, int(side * s)))
                pm = assets.item(item, px_size)
                tgt = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
                p.drawPixmap(tgt, pm, QRectF(0, 0, pm.width(), pm.height()))


class GridOverlay(QGraphicsItem):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setZValue(1.5)

    def boundingRect(self):
        d = self.page.data
        return QRectF(0, 0, d.m.width, d.m.height) if d else QRectF()

    def paint(self, p, opt, widget=None):
        d = self.page.data
        if not d:
            return
        pen = QPen(QColor(255, 255, 255, 60), 0)
        pen.setCosmetic(True)
        p.setPen(pen)
        m = d.m
        for x in range(0, m.width + 1, 32):
            p.drawLine(QPointF(x, 0), QPointF(x, m.height))
        for z in range(0, m.height + 1, 32):
            p.drawLine(QPointF(0, z), QPointF(m.width, z))


class HomeMarker(QGraphicsItem):
    """A resident portrait pin that keeps its screen size at every zoom."""
    R = 17

    def __init__(self, page, index, name, pos):
        super().__init__()
        self.page, self.index, self.name = page, index, name
        self.setPos(pos)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(5)
        self.hover = False
        self.setToolTip(f'{name}\'s home — click to open {name} on the Residents page')

    def boundingRect(self):
        return QRectF(-90, -self.R * 2 - 12, 180, self.R * 2 + 40)

    def paint(self, p, opt, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hl = self.index == self.page.highlight or self.hover
        R = self.R + (4 if hl else 0)
        cy = -R - 9
        # pin tail + shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(0, 1), 5, 2.5)
        tail = QPainterPath()
        tail.moveTo(-6, cy + R - 3)
        tail.lineTo(0, 0)
        tail.lineTo(6, cy + R - 3)
        tail.closeSubpath()
        ring = QColor(T.P['gold']) if hl else QColor('#ffffff')
        p.setBrush(ring)
        p.drawPath(tail)
        p.drawEllipse(QPointF(0, cy), R + 2.5, R + 2.5)
        pm = self.page.app.assets.villager(self.index, 2 * R, circle=True)
        p.drawPixmap(QRectF(-R, cy - R, 2 * R, 2 * R), pm, QRectF(0, 0, pm.width(), pm.height()))
        if hl or self.page.view.zoom() >= 9:
            f = T.font(8.5, QFont.Bold)
            p.setFont(f)
            w = QFontMetrics(f).horizontalAdvance(self.name) + 14
            lr = QRectF(-w / 2, 6, w, 18)
            p.setBrush(QColor(12, 18, 26, 215))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(lr, 9, 9)
            p.setPen(QColor('#ffffff'))
            p.drawText(lr, Qt.AlignCenter, self.name)

    def hoverEnterEvent(self, e):
        self.hover = True
        self.setZValue(6)
        self.update()

    def hoverLeaveEvent(self, e):
        self.hover = False
        self.setZValue(5)
        self.update()

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        self.page.open_resident(self.index)


class MapView(QGraphicsView):
    hovered = Signal(float, float)
    zoomed = Signal(float)

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet('QGraphicsView { background: transparent; border: none; }')
        self.anim = None

    def zoom(self):
        return self.transform().m11()

    def set_zoom(self, z, anchor=None):
        z = max(0.25, min(48.0, z))
        f = z / self.zoom()
        if anchor is not None:
            old = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.NoAnchor)
            before = self.mapToScene(anchor)
            self.scale(f, f)
            after = self.mapToScene(anchor)
            d = after - before
            self.translate(d.x(), d.y())
            self.setTransformationAnchor(old)
        else:
            self.scale(f, f)
        self.zoomed.emit(self.zoom())

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120
        self.set_zoom(self.zoom() * (1.22 ** steps), e.position().toPoint())

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        sp = self.mapToScene(e.position().toPoint())
        self.hovered.emit(sp.x(), sp.y())

    def mouseDoubleClickEvent(self, e):
        self.fly_to(self.mapToScene(e.position().toPoint()), self.zoom() * 2)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Plus, Qt.Key_Equal):
            self.set_zoom(self.zoom() * 1.4)
        elif k == Qt.Key_Minus:
            self.set_zoom(self.zoom() / 1.4)
        elif k == Qt.Key_0:
            self.page.fit(True)
        else:
            super().keyPressEvent(e)

    def fly_to(self, scene_pt, zoom, ms=420):
        if self.anim:
            self.anim.stop()
        c0 = self.mapToScene(self.viewport().rect().center())
        z0 = self.zoom()
        z1 = max(0.25, min(48.0, zoom))
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=ms, easingCurve=QEasingCurve.InOutCubic)

        def step(t):
            t = float(t)
            z = z0 * (z1 / z0) ** t
            self.resetTransform()
            self.scale(z, z)
            self.centerOn(QPointF(c0.x() + (scene_pt.x() - c0.x()) * t, c0.y() + (scene_pt.y() - c0.y()) * t))
            self.zoomed.emit(z)
        self.anim.valueChanged.connect(step)
        self.anim.start()

    def drawBackground(self, p, rect):
        p.fillRect(rect, T.c('mapbg'))


class ScaleBar(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.resize(170, 34)

    def paintEvent(self, e):
        z = self.view.zoom()
        target = 110 / z
        nice = min((1, 2, 5, 10, 20, 50, 100, 200, 500), key=lambda n: abs(n - target))
        w = nice * z
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(12, 18, 26, 170))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w + 70, 30), 8, 8)
        p.setPen(QPen(QColor('#ffffff'), 2))
        p.drawLine(QPointF(10, 20), QPointF(10 + w, 20))
        p.drawLine(QPointF(10, 15), QPointF(10, 24))
        p.drawLine(QPointF(10 + w, 15), QPointF(10 + w, 24))
        p.setFont(T.font(8, QFont.Bold))
        p.drawText(QRectF(16 + w, 6, 60, 20), Qt.AlignVCenter | Qt.AlignLeft, f'{nice} blocks')


class MapPage(Page):
    title, nav, glyph = 'Island Map', 'Island Map', T.G['map']
    subtitle = 'Your islands from above, with every placed object and home'

    def build(self):
        self.area, self.pending, self.highlight, self.data = None, None, None, None
        self.loading = set()
        self.opts = dict(relief=True, contours=False, objects=True, icons=True, homes=True, grid=False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        mapc = QFrame()
        mapc.setObjectName('Card')
        ml = QVBoxLayout(mapc)
        ml.setContentsMargins(1, 1, 1, 1)
        ml.setSpacing(0)
        self.scene = QGraphicsScene()
        self.view = MapView(self)
        self.view.setScene(self.scene)
        self.view.hovered.connect(self.hover)
        self.view.zoomed.connect(self.zoom_changed)
        ml.addWidget(self.view, 1)
        self.scalebar = ScaleBar(self.view)
        # floating zoom buttons
        self.zoombox = QFrame(self.view)
        zb = QVBoxLayout(self.zoombox)
        zb.setContentsMargins(0, 0, 0, 0)
        zb.setSpacing(4)
        for glyph, tip, fn in ((T.G['add'], 'Zoom in (+)', lambda: self.view.set_zoom(self.view.zoom() * 1.5)),
                               (T.G['remove'], 'Zoom out (−)', lambda: self.view.set_zoom(self.view.zoom() / 1.5)),
                               (T.G['fit'], 'Fit island (0)', lambda: self.fit(True)),
                               (T.G['globe'], 'Show everything, including stray chunks', lambda: self.fit(False))):
            b = W.button('', glyph, fn, tip=tip)
            b.setFixedSize(36, 36)
            zb.addWidget(b)
        self.overlay = W.label('', 'h3')
        self.overlay.setParent(self.view)
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.setStyleSheet(f'background: {T.P["card"]}; border: 1px solid {T.P["line2"]}; border-radius: 12px; padding: 14px 22px;')
        self.overlay.hide()
        info = QFrame()
        info.setStyleSheet(f'border-top: 1px solid {T.P["line"]};')
        il = QHBoxLayout(info)
        il.setContentsMargins(14, 7, 14, 7)
        self.i_pos = W.label('Hover the map', 'small')
        self.i_obj = W.label('', 'small')
        self.i_zoom = W.label('', 'small')
        il.addWidget(self.i_pos)
        il.addWidget(self.i_obj, 1)
        il.addWidget(self.i_zoom)
        ml.addWidget(info)
        lay.addWidget(mapc, 1)
        # side panel
        side = QScrollArea()
        side.setWidgetResizable(True)
        side.setFrameShape(QFrame.NoFrame)
        side.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side.setFixedWidth(312)
        inner = QWidget()
        inner.setObjectName('PageInner')
        sl = QVBoxLayout(inner)
        sl.setContentsMargins(0, 0, 8, 0)
        sl.setSpacing(12)
        side.setWidget(inner)
        isl = W.Card('Islands', None, T.G['globe'], padding=12)
        self.isl_box = QVBoxLayout()
        self.isl_box.setSpacing(4)
        isl.body.addLayout(self.isl_box)
        self.isl_group = QButtonGroup(self)
        self.isl_group.setExclusive(True)
        sl.addWidget(isl)
        lc = W.Card('Layers', None, T.G['layers'], padding=12)
        self.layer_rows = {}
        for key, text, note in (('relief', 'Relief shading', ''), ('contours', 'Height lines', 'Every 4 blocks'),
                                ('objects', 'Placed objects', 'Tinted by item category'),
                                ('icons', 'Object icons', 'When zoomed in close'), ('homes', 'Resident homes', ''),
                                ('grid', 'Chunk grid', '32 × 32 blocks')):
            row = W.ToggleRow(text, note)
            row.toggle.set_quiet(self.opts[key])
            row.toggle.toggled.connect(lambda on, k=key: self.set_opt(k, on))
            lc.body.addWidget(row)
            self.layer_rows[key] = row
        sl.addWidget(lc)
        rc = W.Card('Residents here', None, T.G['people'], padding=12)
        self.res_list = QListWidget()
        self.res_list.setIconSize(QSize(28, 28))
        self.res_list.setStyleSheet('QListWidget::item { padding: 4px 6px; border-radius: 8px; }'
                                    f'QListWidget::item:hover {{ background: {T.P["tilehi"]}; }}'
                                    f'QListWidget::item:selected {{ background: {T.P["sel"]}; color: {T.P["text"]}; }}')
        self.res_list.setMinimumHeight(180)
        self.res_list.itemClicked.connect(lambda it: self.fly_home(it.data(Qt.UserRole)))
        rc.body.addWidget(self.res_list)
        sl.addWidget(rc)
        sc = W.Card('This island', None, T.G['info'], padding=12)
        self.stats = W.label('', 'muted', wrap=True)
        sc.body.addWidget(self.stats)
        self.top_box = QGridLayout()
        self.top_box.setHorizontalSpacing(8)
        self.top_box.setVerticalSpacing(4)
        sc.body.addLayout(self.top_box)
        sc.body.addWidget(W.button('Export PNG…', T.G['export'], self.export))
        sl.addWidget(sc)
        sl.addStretch(1)
        lay.addWidget(side)
        self.terrain = None
        self.icons_item = self.grid_item = None
        self.markers = []

    # ---------- layout of floating widgets ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.place_floating)

    def place_floating(self):
        v = self.view
        self.zoombox.adjustSize()
        self.zoombox.move(v.width() - self.zoombox.width() - 14, 14)
        self.scalebar.move(14, v.height() - self.scalebar.height() - 10)
        self.overlay.adjustSize()
        self.overlay.move((v.width() - self.overlay.width()) // 2, (v.height() - self.overlay.height()) // 2)

    # ---------- islands ----------
    def save_changed(self):
        self.data, self.area = None, None
        for b in self.isl_group.buttons():
            self.isl_group.removeButton(b)
            b.deleteLater()
        st = self.app.save.stage_files() if self.app.save else {}
        for n in st:
            b = QPushButton(f'  {ps.name_of(ps.AREA_NAMES, n, "Area")}')
            b.setProperty('nav', 'true')
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(T.glyph_icon(T.G['map'], 'muted', 16, active_key='accent'))
            b.clicked.connect(lambda _=False, n=n: self.choose(n))
            self.isl_group.addButton(b)
            self.isl_box.addWidget(b)
        self.isl_buttons = dict(zip(st, self.isl_group.buttons()))

    def refresh(self):
        if not self.app.save:
            return
        st = self.app.save.stage_files()
        if self.pending is not None and self.pending[0] in st:
            self.area = self.pending[0]
        if self.area not in st:
            self.area = next(iter(st), None)
        if self.area is not None and self.area in getattr(self, 'isl_buttons', {}):
            self.isl_buttons[self.area].setChecked(True)
        self.ensure()

    def choose(self, area):
        if area == self.area and self.data:
            return
        self.area, self.highlight, self.pending = area, None, None
        self.ensure()

    def focus_home(self, v):
        self.pending = (v['home_area'], v['index'], v['home_xyz'])
        self.highlight = v['index']

    def message(self, text):
        if text:
            self.overlay.setText(text)
            self.overlay.show()
            self.place_floating()
        else:
            self.overlay.hide()

    def ensure(self):
        app, a = self.app, self.area
        if a is None:
            self.clear_scene()
            return self.message('This save has no island files.')
        key = (app.save.folder, a)
        if key in app.map_cache:
            self.show_island(app.map_cache[key])
            return
        self.clear_scene()
        self.message(f'Reading {ps.name_of(ps.AREA_NAMES, a, "the island")}…')
        if key in self.loading:
            return
        self.loading.add(key)
        path = app.save.stage_files()[a]
        from gui.maprender import load_island
        app.run_bg('map', key, lambda: load_island(path, a))

    def loaded(self, key, result, err):
        self.loading.discard(key)
        if err:
            if self.app.save and (self.app.save.folder, self.area) == key:
                self.message(f'Cannot read this island:\n{err}')
            return
        self.app.map_cache[key] = result
        if self.app.save and (self.app.save.folder, self.area) == key:
            self.show_island(result)

    def clear_scene(self):
        self.scene.clear()
        self.terrain = self.icons_item = self.grid_item = None
        self.markers = []
        self.data = None

    def show_island(self, d):
        fresh = d is not self.data
        if fresh:
            self.clear_scene()
            self.data = d
            self.scene.setSceneRect(QRectF(-200, -200, d.m.width + 400, d.m.height + 400))
            self.terrain = QGraphicsPixmapItem()
            self.terrain.setZValue(0)
            self.scene.addItem(self.terrain)
            self.icons_item = ObjectIcons(self)
            self.scene.addItem(self.icons_item)
            self.grid_item = GridOverlay(self)
            self.scene.addItem(self.grid_item)
        self.message('')
        self.update_terrain()
        self.update_markers()
        self.update_side()
        if self.pending and self.pending[0] == self.area:
            _, idx, (x, y, z) = self.pending
            self.pending = None
            ix, iz = d.m.to_pixel(x, z)
            if fresh:
                self.fit(True, animate=False)
            self.view.fly_to(QPointF(ix + 0.5, iz + 0.5), 7.0, 650)
        elif fresh:
            self.fit(True, animate=False)

    def update_terrain(self):
        d = self.data
        if not d:
            return
        o = self.opts
        key = (o['relief'], o['contours'], o['objects'], T.NAME)
        pm = d.composed.get(key)
        if pm is None:
            from gui.maprender import compose
            bg = T.c('mapbg')
            img = compose(d.layers, (bg.red(), bg.green(), bg.blue()), o['relief'], o['contours'], o['objects'])
            pm = d.composed[key] = QPixmap.fromImage(pil_to_qimage(img))
        self.terrain.setPixmap(pm)
        self.zoom_changed(self.view.zoom())
        self.icons_item.setVisible(o['icons'] and o['objects'])
        self.grid_item.setVisible(o['grid'])

    def update_markers(self):
        for mk in self.markers:
            self.scene.removeItem(mk)
        self.markers = []
        d, c = self.data, self.c
        if not d or not c or not self.opts['homes']:
            return
        for i, name, x, y, z in px.homes_on(c, self.area):
            ix, iz = d.m.to_pixel(x, z)
            mk = HomeMarker(self, i, name, QPointF(ix + 0.5, iz + 0.5))
            self.scene.addItem(mk)
            self.markers.append(mk)

    def update_side(self):
        d, c = self.data, self.c
        self.res_list.clear()
        if not d or not c:
            return
        homes = px.homes_on(c, self.area)
        for i, name, x, y, z in sorted(homes, key=lambda h: h[1]):
            it = QListWidgetItem(QIcon(self.app.assets.villager(i, 28, circle=True)), f'  {name}')
            it.setData(Qt.UserRole, i)
            it.setToolTip(f'X {x}  Y {y}  Z {z}')
            self.res_list.addItem(it)
        if not homes:
            it = QListWidgetItem('No resident has a home on this island.')
            it.setFlags(Qt.NoItemFlags)
            self.res_list.addItem(it)
        m = d.m
        x0, z0, x1, z1 = m.main_bbox()
        self.stats.setText(f'{m.name}\n{x1 - x0} × {z1 - z0} blocks · {m.chunks} chunks\n'
                           f'{len(m.placed):,} placed objects · {len(homes)} resident home{"s" if len(homes) != 1 else ""}')
        while self.top_box.count():
            w = self.top_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.top_box.addWidget(W.label('MOST PLACED', 'caps'), 0, 0, 1, 3)
        for n, (item, cnt) in enumerate(d.top, 1):
            ic = QLabel()
            ic.setPixmap(self.app.assets.item(item, 22))
            self.top_box.addWidget(ic, n, 0)
            nm = W.label(ps.item_name(item))
            nm.setToolTip(f'Item ID {item}')
            self.top_box.addWidget(nm, n, 1)
            self.top_box.addWidget(W.label(f'{cnt:,}', 'muted'), n, 2, Qt.AlignRight)
        self.top_box.setColumnStretch(1, 1)

    # ---------- interaction ----------
    def set_opt(self, key, on):
        self.opts[key] = on
        if key == 'homes':
            self.update_markers()
        else:
            self.update_terrain()

    def fit(self, island=True, animate=True):
        d = self.data
        if not d:
            return
        m = d.m
        x0, z0, x1, z1 = m.main_bbox() if island else (0, 0, m.width, m.height)
        vw, vh = max(50, self.view.viewport().width()), max(50, self.view.viewport().height())
        z = max(0.25, min(vw / (x1 - x0 + 24), vh / (z1 - z0 + 24)))
        c = QPointF((x0 + x1) / 2, (z0 + z1) / 2)
        if animate:
            self.view.fly_to(c, z)
        else:
            self.view.resetTransform()
            self.view.scale(z, z)
            self.view.centerOn(c)
            self.zoom_changed(z)

    def fly_home(self, index):
        d, c = self.data, self.c
        if not d or not c:
            return
        v = c.get_villager(index)
        if not v['home_xyz']:
            return
        self.highlight = index
        x, y, z = v['home_xyz']
        ix, iz = d.m.to_pixel(x, z)
        for mk in self.markers:
            mk.update()
        self.view.fly_to(QPointF(ix + 0.5, iz + 0.5), max(6.0, self.view.zoom()))

    def open_resident(self, index):
        self.app.show_page('Residents')
        self.app.pages['Residents'].select_resident(index)

    def zoom_changed(self, z):
        if self.terrain is not None:
            self.terrain.setTransformationMode(Qt.FastTransformation if z >= 1.6 else Qt.SmoothTransformation)
        self.i_zoom.setText(f'Zoom {z:.1f}×')
        self.scalebar.update()
        for mk in self.markers:
            mk.update()

    def hover(self, sx, sz):
        d = self.data
        if not d:
            return
        ix, iz = math.floor(sx), math.floor(sz)
        hit = d.m.info_at(ix, iz)
        if not hit:
            self.i_pos.setText('Outside the island')
            self.i_obj.setText('')
            return
        x, y, z, bid = hit
        what = 'sea water' if bid == d.m.WATER else f'block {bid}'
        self.i_pos.setText(f'X {x}   Y {y}   Z {z}   ·   {what}')
        part = d.part_at(ix, iz) if self.opts['objects'] else None
        if part:
            item = part[1]
            w, dd = part[4] - part[2] + 1, part[5] - part[3] + 1
            nm = ps.item_name(item) if item else f'object (variation {part[0]})'
            self.i_obj.setText(f'   ·   {nm}' + (f'  ·  ID {item}' if item else '') + f'  ·  {w}×{dd}')
        else:
            self.i_obj.setText('')

    def export(self):
        d = self.data
        if not d:
            return
        f, _ = QFileDialog.getSaveFileName(self, 'Export island map', f'pokopia_island_{self.area:02}.png', 'PNG image (*.png)')
        if not f:
            return
        from gui.maprender import compose
        bg = T.c('mapbg')
        o = self.opts
        img = compose(d.layers, (bg.red(), bg.green(), bg.blue()), o['relief'], o['contours'], o['objects'])
        m = d.m
        x0, z0, x1, z1 = m.main_bbox()
        x0, z0, x1, z1 = max(0, x0 - 8), max(0, z0 - 8), min(m.width, x1 + 8), min(m.height, z1 + 8)
        S = 4
        q = pil_to_qimage(img.crop((x0, z0, x1, z1))).scaled((x1 - x0) * S, (z1 - z0) * S)
        if o['homes'] and self.c:
            p = QPainter(q)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            for i, name, x, y, z in px.homes_on(self.c, self.area):
                ix, iz = m.to_pixel(x, z)
                cx, cy = (ix - x0 + 0.5) * S, (iz - z0 + 0.5) * S
                R = 18
                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#ffffff'))
                p.drawEllipse(QPointF(cx, cy - R - 6), R + 2.5, R + 2.5)
                pm = self.app.assets.villager(i, 2 * R, circle=True)
                p.drawPixmap(QRectF(cx - R, cy - 2 * R - 6, 2 * R, 2 * R), pm, QRectF(0, 0, pm.width(), pm.height()))
                p.setFont(T.font(8, QFont.Bold))
                w = QFontMetrics(p.font()).horizontalAdvance(name) + 12
                p.setBrush(QColor(12, 18, 26, 210))
                p.drawRoundedRect(QRectF(cx - w / 2, cy + 2, w, 16), 8, 8)
                p.setPen(QColor('#ffffff'))
                p.drawText(QRectF(cx - w / 2, cy + 2, w, 16), Qt.AlignCenter, name)
            p.end()
        q.save(f)
        self.app.toast(f'Map exported: {f}')
