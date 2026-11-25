# Linux port modifications by frinimini, 2026-11-25. See CREDITS.md.
"""Island map editor: textured terrain, placed objects, habitats, homes and the separate areas of each island file.

Tools: select / move objects, place objects, make habitats, paint ground blocks, ground height, pick.
Edits go into the island's own undo journal and the app's shared history; Save writes the island file
(after the usual automatic backup of the whole save folder).
"""
import math
import os
from collections import Counter, OrderedDict

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, QEasingCurve, Signal, QPoint
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QCursor)
from PySide6.QtWidgets import (QApplication, QCheckBox, QAbstractItemView, QDialog, QDialogButtonBox, QButtonGroup, QComboBox, QSpinBox, QFileDialog, QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView,
                               QGridLayout, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSlider, QTreeWidget, QTreeWidgetItem, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

import pokopia_extras as px
import pokopia_island as pi
import pokopia_items as pit
import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page

DETAIL_ZOOM = 3.0     # textured tiles from this many screen pixels per block
HIRES_ZOOM = 9.0      # 16-pixel textures from here, 8-pixel below
ICON_ZOOM = 5.0       # objects drawn one by one from here
LABEL_ZOOM = 9.0      # habitat names from here
MIN_ZOOM, MAX_ZOOM = 0.2, 64.0
TOOLS = [('select', 'Select and move', 'V'), ('place', 'Place objects', 'P'), ('habitat', 'Make a habitat', 'T'),
         ('paint', 'Paint ground', 'B'), ('height', 'Ground height', 'H'), ('pick', 'Pick', 'I')]
HEIGHT_MODES = [('raise', 'Raise', 'Each click or stroke adds one layer of ground'),
                ('lower', 'Lower', 'Each click or stroke takes one layer away'),
                ('flatten', 'Flatten', 'Raise or lower everything you brush to one height')]
ROT_NAMES = ['0°', '90°', '180°', '270°']
ZONE_GLYPH = {'island': 'map', 'center': 'home', 'dream': 'star', 'plot': 'pin'}


def pil_to_qimage(im):
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    return QImage(im.tobytes('raw', 'RGBA'), im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()


def tool_icon(kind, color, size=22):
    """Hand-drawn tool icons, so they do not depend on an icon font."""
    r = 2.0
    pm = QPixmap(int(size * r), int(size * r))
    pm.setDevicePixelRatio(r)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = size
    if kind == 'select':
        path = QPainterPath()
        path.moveTo(s * .28, s * .16)
        path.lineTo(s * .28, s * .80)
        path.lineTo(s * .44, s * .64)
        path.lineTo(s * .56, s * .88)
        path.lineTo(s * .66, s * .83)
        path.lineTo(s * .54, s * .60)
        path.lineTo(s * .76, s * .60)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)
    elif kind == 'place':
        top = QPolygonF([QPointF(s * .5, s * .14), QPointF(s * .84, s * .32), QPointF(s * .5, s * .5), QPointF(s * .16, s * .32)])
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 90))
        p.drawPolygon(top)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * .16, s * .32), QPointF(s * .16, s * .68))
        p.drawLine(QPointF(s * .84, s * .32), QPointF(s * .84, s * .52))
        p.drawLine(QPointF(s * .5, s * .5), QPointF(s * .5, s * .86))
        p.drawLine(QPointF(s * .16, s * .68), QPointF(s * .5, s * .86))
        p.drawLine(QPointF(s * .68, s * .74), QPointF(s * .94, s * .74))
        p.drawLine(QPointF(s * .81, s * .61), QPointF(s * .81, s * .87))
    elif kind == 'paint':
        p.setBrush(c)
        p.save()
        p.translate(s * .62, s * .38)
        p.rotate(45)
        p.drawRoundedRect(QRectF(-s * .09, -s * .34, s * .18, s * .36), 2, 2)
        p.restore()
        path = QPainterPath()
        path.moveTo(s * .38, s * .58)
        path.cubicTo(s * .18, s * .62, s * .26, s * .84, s * .12, s * .88)
        path.cubicTo(s * .38, s * .92, s * .52, s * .78, s * .46, s * .66)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == 'habitat':
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 60))
        p.drawRoundedRect(QRectF(s * .12, s * .5, s * .76, s * .36), 3, 3)
        p.setBrush(Qt.NoBrush)
        for x0 in (.26, .44, .62):
            p.drawLine(QPointF(s * x0, s * .62), QPointF(s * (x0 - .06), s * .18))
            p.drawLine(QPointF(s * x0, s * .62), QPointF(s * (x0 + .1), s * .26))
    elif kind in ('raise', 'height'):
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
        mount = QPolygonF([QPointF(s * .1, s * .86), QPointF(s * .4, s * .42), QPointF(s * .56, s * .62),
                           QPointF(s * .68, s * .5), QPointF(s * .92, s * .86)])
        p.drawPolygon(mount)
        p.drawLine(QPointF(s * .78, s * .12), QPointF(s * .78, s * .38))
        p.drawLine(QPointF(s * .68, s * .22), QPointF(s * .78, s * .12))
        p.drawLine(QPointF(s * .88, s * .22), QPointF(s * .78, s * .12))
    elif kind == 'level':
        p.drawLine(QPointF(s * .1, s * .62), QPointF(s * .9, s * .62))
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
        p.drawRect(QRectF(s * .1, s * .62, s * .8, s * .22))
        p.drawLine(QPointF(s * .3, s * .2), QPointF(s * .3, s * .48))
        p.drawLine(QPointF(s * .22, s * .4), QPointF(s * .3, s * .48))
        p.drawLine(QPointF(s * .38, s * .4), QPointF(s * .3, s * .48))
        p.drawLine(QPointF(s * .7, s * .48), QPointF(s * .7, s * .2))
        p.drawLine(QPointF(s * .62, s * .28), QPointF(s * .7, s * .2))
        p.drawLine(QPointF(s * .78, s * .28), QPointF(s * .7, s * .2))
    elif kind == 'pick':
        p.save()
        p.translate(s * .5, s * .5)
        p.rotate(45)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 80))
        p.drawRoundedRect(QRectF(-s * .07, -s * .1, s * .14, s * .5), 2, 2)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(-s * .13, -s * .42, s * .26, s * .3), 4, 4)
        p.restore()
    p.end()
    return pm


# ------------------------------------------------------------------------------------------------ scene items

def brush_offsets(shape, width, depth):
    """Cell offsets shared by the brush preview and terrain edits."""
    if shape in ('square', 'rectangle'):
        depth = width if shape == 'square' else depth
        return [(dx, dz) for dz in range(-(depth // 2), depth - depth // 2)
                for dx in range(-(width // 2), width - width // 2)]
    radius = (width - 1) / 2
    extent = math.ceil(radius)
    return [(dx, dz) for dz in range(-extent, extent + 1) for dx in range(-extent, extent + 1)
            if dx * dx + dz * dz <= radius * radius + radius * 0.8 + 0.01]



def column_layers(island, wx, wz):
    """Vertical contents, including hidden objects and contiguous terrain bands."""
    rows = [(o.y + o.h - 1, o.y, o.name, o.handle)
            for o in island.objects_in(wx, wz, wx, wz)]
    # Negative handles identify read-only discovery markers, never editable objects.
    rows += [(y, y, 'Glowing Block', -index - 1)
             for index, x, y, z, _ in island.glowing_blocks() if x == wx and z == wz]
    start, previous = 0, 0
    for y in range(129):
        cell = island.get_cell(wx, y, wz) if y < 128 else None
        block = (cell & pi.ID_MASK) if cell is not None else 0
        if block == 0x7ff:
            block = 0  # placed-object occupancy is represented by the object row
        if block != previous:
            if previous:
                rows.append((y - 1, start, pi.block_name(previous), None))
            start, previous = y, block
    return sorted(rows, key=lambda row: (-row[0], -row[1], row[2]))


class TerrainItem(QGraphicsItem):
    """Base image when zoomed out, textured chunk tiles when zoomed in; object footprints at mid zoom."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)
        self.tiles = {8: OrderedDict(), 16: OrderedDict()}
        self.limit = {8: 260, 16: 72}
        self.pending = False
        self.exporting = False

    def boundingRect(self):
        v = self.page.view_data
        return QRectF(0, 0, v.isl.width, v.isl.height) if v else QRectF()

    def drop_tiles(self, keys=None):
        for cache in self.tiles.values():
            if keys is None:
                cache.clear()
            else:
                for k in keys:
                    cache.pop(k, None)

    def tile(self, tex, key, build):
        cache = self.tiles[tex]
        pm = cache.get(key)
        if pm is not None:
            cache.move_to_end(key)
            return pm
        if not build:
            return None
        from gui.maprender import render_tile
        pm = QPixmap.fromImage(pil_to_qimage(render_tile(self.page.view_data.isl, key[0], key[1], tex)))
        cache[key] = pm
        while len(cache) > self.limit[tex]:
            cache.popitem(last=False)
        return pm

    def paint(self, p, opt, widget=None):
        v = self.page.view_data
        if not v:
            return
        s = p.worldTransform().m11()
        r = opt.exposedRect
        isl = v.isl
        o = self.page.opts
        if s < DETAIL_ZOOM or not o['textures']:
            p.setRenderHint(QPainter.SmoothPixmapTransform, s < 1.6)
            p.drawPixmap(r, v.base_pm, r)
        else:
            tex = 16 if s >= HIRES_ZOOM else 8
            p.setRenderHint(QPainter.SmoothPixmapTransform, s * 1.0 / tex < 1.0)
            budget = 999 if self.exporting else 10
            missing = False
            tx0, tz0 = max(0, int(r.left()) // 32), max(0, int(r.top()) // 32)
            tx1, tz1 = min(isl.width // 32 - 1, int(r.right()) // 32), min(isl.height // 32 - 1, int(r.bottom()) // 32)
            cache = self.tiles[tex]
            for tz in range(tz0, tz1 + 1):
                for tx in range(tx0, tx1 + 1):
                    key = (tx, tz)
                    if key not in v.tiles_with_data:
                        continue
                    pm = cache.get(key)
                    if pm is None and budget > 0:
                        pm = self.tile(tex, key, True)
                        budget -= 1
                    elif pm is not None:
                        cache.move_to_end(key)
                    tr = QRectF(tx * 32, tz * 32, 32, 32)
                    if pm is None:
                        missing = True
                        p.drawPixmap(tr, v.base_pm, tr)
                    else:
                        e = 0.75 / s
                        p.drawPixmap(tr.adjusted(0, 0, e, e), pm, QRectF(0, 0, pm.width(), pm.height()))
            if missing and not self.pending:
                self.pending = True
                QTimer.singleShot(15, self._more)
        if o['objects'] and s < ICON_ZOOM:
            p.setRenderHint(QPainter.SmoothPixmapTransform, s < 1.6)
            p.setOpacity(0.92)
            p.drawPixmap(r, v.objects_pm, r)
            p.setOpacity(1.0)
        if o['contours'] and s >= 1.0:
            p.setOpacity(0.55)
            p.drawPixmap(r, v.contour_pm(), r)
            p.setOpacity(1.0)
        if self.page.tool == 'height' and self.page.show_heights:
            p.setRenderHint(QPainter.SmoothPixmapTransform, s < 1.6)
            p.setOpacity(0.7)
            p.drawPixmap(r, v.heights_pm(), r)
            p.setOpacity(1.0)

    def _more(self):
        self.pending = False
        self.update()


class ObjectsItem(QGraphicsItem):
    """Placed objects drawn one by one (icons, connected fences, roof tiles) when zoomed in."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)
        self.setZValue(2)
        self._fence_ver = None
        self.fences = {}

    def boundingRect(self):
        v = self.page.view_data
        return QRectF(0, 0, v.isl.width, v.isl.height) if v else QRectF()

    def fence_map(self, isl):
        if self._fence_ver != (id(isl), isl.objects_version):
            from gui.maprender import object_style
            self.fences = {}
            self.styles = {}
            for o in isl.objects:
                st = object_style(o)
                self.styles[o.handle] = st
                if st == 'fence':
                    for dy in (-1, 0, 1):
                        self.fences[(o.x, o.z, o.y + dy)] = o.item
            self._fence_ver = (id(isl), isl.objects_version)
        return self.fences

    def paint(self, p, opt, widget=None):
        page = self.page
        v = page.view_data
        s = p.worldTransform().m11()
        if not v or s < ICON_ZOOM or not page.opts['objects']:
            return
        isl = v.isl
        from gui.maprender import look
        L = look()
        r = opt.exposedRect
        fences = self.fence_map(isl)
        styles = self.styles
        assets = page.app.assets
        icons = page.opts['icons']
        X0, Z0 = isl.x0, isl.z0
        objs = sorted((o for o in isl.objects_in(r.left() + X0 - 1, r.top() + Z0 - 1, r.right() + X0 + 1, r.bottom() + Z0 + 1)
                       if o.y <= isl.cut), key=lambda o: (o.y + o.h, o.w * o.dp))
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        thin = QPen(QColor(0, 0, 0, 90), 0)
        thin.setCosmetic(True)
        shadow = QColor(0, 0, 0, 55)
        cutpen = QPen(QColor(255, 255, 255, 170), 1.4, Qt.DashLine)
        cutpen.setCosmetic(True)
        for o in objs:
            x0, z0, x1, z1 = o.box
            rect = QRectF(x0 - X0, z0 - Z0, x1 - x0 + 1, z1 - z0 + 1)
            if isl.crosses_cut(o):
                p.setPen(cutpen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect.adjusted(0.05, 0.05, -0.05, -0.05))
                continue
            st = styles.get(o.handle, 'item')
            col = QColor(*L.item_color(o.item)) if o.item else QColor(160, 152, 140)
            if st == 'fence':
                cx, cz = o.x - X0 + 0.5, o.z - Z0 + 0.5
                pen = QPen(col.darker(130), 0.32, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if fences.get((o.x + dx, o.z + dz, o.y)) == o.item:
                        p.drawLine(QPointF(cx, cz), QPointF(cx + dx * 0.5, cz + dz * 0.5))
                pen = QPen(col.lighter(115), 0.18, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if fences.get((o.x + dx, o.z + dz, o.y)) == o.item:
                        p.drawLine(QPointF(cx, cz), QPointF(cx + dx * 0.5, cz + dz * 0.5))
                p.setPen(Qt.NoPen)
                p.setBrush(col.darker(140))
                p.drawRoundedRect(QRectF(cx - 0.2, cz - 0.2, 0.4, 0.4), 0.08, 0.08)
                continue
            if st in ('roof', 'struct'):
                p.setPen(thin)
                p.setBrush(col if st == 'roof' else QColor(176, 166, 150, 230))
                p.drawRect(rect)
                if st == 'roof' and s >= 10:
                    p.setPen(QPen(col.darker(125), 0))
                    for k in range(1, int(rect.height() * 3)):
                        yy = rect.top() + k / 3
                        p.drawLine(QPointF(rect.left(), yy), QPointF(rect.right(), yy))
                continue
            if st == 'flat':
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(col.red(), col.green(), col.blue(), 215))
                p.drawRect(rect.adjusted(0.04, 0.04, -0.04, -0.04))
                if icons and o.item and min(rect.width(), rect.height()) * s >= 18:
                    pm = assets.item(o.item, max(16, min(96, int(min(rect.width(), rect.height()) * s))))
                    p.setOpacity(0.85)
                    p.drawPixmap(rect.adjusted(0.08, 0.08, -0.08, -0.08), pm, QRectF(0, 0, pm.width(), pm.height()))
                    p.setOpacity(1.0)
                continue
            # items, plants and big objects
            side = min(rect.width(), rect.height())
            if st == 'big':
                p.setPen(QPen(QColor(255, 255, 255, 120), 0))
                p.setBrush(QColor(col.red(), col.green(), col.blue(), 120))
                p.drawRoundedRect(rect.adjusted(0.1, 0.1, -0.1, -0.1), 0.4, 0.4)
                side = min(max(rect.width(), rect.height()) * 0.8, side * 1.6)
            scale = 0.82 if st == 'plant' else 1.04
            size = side * scale
            if not icons or not o.item or size * s < 7:
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(rect.adjusted(0.12, 0.12, -0.12, -0.12), 0.2, 0.2)
                continue
            c = rect.center()
            p.setPen(Qt.NoPen)
            p.setBrush(shadow)
            p.drawEllipse(QPointF(c.x() + size * 0.06, c.y() + size * 0.30), size * 0.38, size * 0.16)
            pm = assets.item(o.item, max(16, min(128, int(size * s))))
            p.drawPixmap(QRectF(c.x() - size / 2, c.y() - size / 2, size, size), pm, QRectF(0, 0, pm.width(), pm.height()))


class HabitatsItem(QGraphicsItem):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setZValue(3)
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)

    def boundingRect(self):
        v = self.page.view_data
        return QRectF(0, 0, v.isl.width, v.isl.height) if v else QRectF()

    def paint(self, p, opt, widget=None):
        page = self.page
        v = page.view_data
        if not v or not page.opts['habitats']:
            return
        isl = v.isl
        s = p.worldTransform().m11()
        p.setRenderHint(QPainter.Antialiasing)
        acc = QColor(T.P['gold'])
        for h in isl.habitats:
            rect = QRectF(h.min[0] - isl.x0, h.min[2] - isl.z0, h.max[0] - h.min[0] + 1, h.max[2] - h.min[2] + 1)
            sel = page.sel_habitat is h
            pen = QPen(QColor(255, 255, 255, 230) if sel else acc, 2.4 if sel else 1.5, Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 60 if sel else 26))
            rad = min(0.6, rect.width() / 3)
            p.drawRoundedRect(rect, rad, rad)
        show = [h for h in (page.sel_habitat, page.hover_habitat) if h is not None and h in isl.habitats]
        if not show:
            return
        # labels in screen space
        tr = p.worldTransform()
        p.save()
        p.resetTransform()
        f = T.font(8.5, QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        for h in dict.fromkeys(show):
            pt = tr.map(QPointF((h.min[0] + h.max[0] + 1) / 2 - isl.x0, h.min[2] - isl.z0))
            text = h.name
            w = fm.horizontalAdvance(text) + 14
            lr = QRectF(pt.x() - w / 2, pt.y() - 22, w, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 16, 4, 205))
            p.drawRoundedRect(lr, 9, 9)
            p.setPen(QColor(T.P['gold']).lighter(130))
            p.drawText(lr, Qt.AlignCenter, text)
        p.restore()


class GridItem(QGraphicsItem):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setZValue(1.5)
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)

    def boundingRect(self):
        v = self.page.view_data
        return QRectF(0, 0, v.isl.width, v.isl.height) if v else QRectF()

    def paint(self, p, opt, widget=None):
        v = self.page.view_data
        if not v or not self.page.opts['grid']:
            return
        pen = QPen(QColor(255, 255, 255, 50), 0)
        pen.setCosmetic(True)
        p.setPen(pen)
        isl = v.isl
        s = p.worldTransform().m11()
        step = 1 if s >= 14 else 32
        r = opt.exposedRect.intersected(self.boundingRect())
        x0, x1 = int(r.left()) // step * step, int(r.right()) + 1
        z0, z1 = int(r.top()) // step * step, int(r.bottom()) + 1
        for x in range(x0, x1 + 1, step):
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        for z in range(z0, z1 + 1, step):
            p.drawLine(QPointF(r.left(), z), QPointF(r.right(), z))


class OverlayItem(QGraphicsItem):
    """Selection, hover, placement ghost, brush outline and box selection."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setZValue(8)

    def boundingRect(self):
        v = self.page.view_data
        return QRectF(-64, -64, v.isl.width + 128, v.isl.height + 128) if v else QRectF()

    def paint(self, p, opt, widget=None):
        page = self.page
        v = page.view_data
        if not v:
            return
        isl = v.isl
        X0, Z0 = isl.x0, isl.z0
        p.setRenderHint(QPainter.Antialiasing)
        acc = QColor(T.P['accent'])
        # selection
        for hnd in page.selection:
            o = isl.by_handle.get(hnd)
            if not o:
                continue
            x0, z0, x1, z1 = o.box
            if page.drag and page.drag.get('kind') == 'move':
                dx, dz = page.drag['dx'], page.drag['dz']
                x0, x1, z0, z1 = x0 + dx, x1 + dx, z0 + dz, z1 + dz
            rect = QRectF(x0 - X0, z0 - Z0, x1 - x0 + 1, z1 - z0 + 1)
            bad = page.drag and page.drag.get('kind') == 'move' and page.drag.get('bad')
            c = QColor(T.P['danger']) if bad else acc
            pen = QPen(c, 2.2)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 55))
            p.drawRoundedRect(rect, 0.15, 0.15)
        # hover
        if page.hover_obj is not None and page.tool in ('select', 'pick') and not page.drag:
            o = isl.by_handle.get(page.hover_obj)
            if o and o.handle not in page.selection:
                x0, z0, x1, z1 = o.box
                pen = QPen(QColor(255, 255, 255, 200), 1.4)
                pen.setCosmetic(True)
                p.setPen(pen)
                p.setBrush(QColor(255, 255, 255, 28))
                p.drawRoundedRect(QRectF(x0 - X0, z0 - Z0, x1 - x0 + 1, z1 - z0 + 1), 0.15, 0.15)
        # placement ghost
        g = page.ghost
        if g and page.tool == 'place':
            var, x, y, z, d, ok = g
            item, w, h, dp = pi.part_size(var)
            x0, z0, x1, z1 = pi.box_of(x, z, d, w, dp)
            rect = QRectF(x0 - X0, z0 - Z0, x1 - x0 + 1, z1 - z0 + 1)
            c = acc if ok else QColor(T.P['danger'])
            pen = QPen(c, 2)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
            p.drawRect(rect)
            if item:
                pm = page.app.assets.item(item, 64)
                side = min(rect.width(), rect.height()) * 0.95
                cc = rect.center()
                p.setOpacity(0.85 if ok else 0.45)
                p.drawPixmap(QRectF(cc.x() - side / 2, cc.y() - side / 2, side, side), pm, QRectF(0, 0, pm.width(), pm.height()))
                p.setOpacity(1.0)
            # facing arrow
            fx, fz = pi.local_to_world(x, z, d, 0, 0)
            ax, az = pi.local_to_world(x, z, d, 0, 1)
            pen = QPen(QColor(255, 255, 255, 200), 1.6)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(QPointF(fx - X0 + 0.5, fz - Z0 + 0.5), QPointF(fx - X0 + 0.5 - (ax - fx) * 0.45, fz - Z0 + 0.5 - (az - fz) * 0.45))
        if page.layer_cell is not None and page.tool == 'select':
            wx, wz = page.layer_cell
            p.save()
            pen = QPen(acc, 2)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 40))
            p.drawRect(QRectF(wx - X0, wz - Z0, 1, 1))
            p.restore()
        if page.opts['discoveries']:
            transform = p.worldTransform()
            p.save()
            p.resetTransform()
            icon = T.glyph_icon(T.G['star'], 'gold', 18)
            for _, wx, wy, wz, _ in isl.glowing_blocks():
                point = transform.map(QPointF(wx - X0 + 0.5, wz - Z0 + 0.5))
                if not page.view.viewport().rect().adjusted(-18, -18, 18, 18).contains(point.toPoint()):
                    continue
                p.setPen(QPen(QColor(T.P['gold']), 1.5))
                p.setBrush(QColor(10, 16, 24, 210))
                p.drawEllipse(point, 11, 11)
                icon.paint(p, QRect(round(point.x()) - 9, round(point.y()) - 9, 18, 18))
            p.restore()
        # brush
        b = page.brush_at
        if b and page.tool in ('paint', 'height') and not (page.drag and page.drag['kind'] in ('height_box')):
            cells = page.brush_cells(*b)
            path = QPainterPath()
            shape = page.height_brush_shape if page.tool == 'height' else page.brush_shape
            if shape in ('square', 'rectangle'):
                xs, zs = zip(*cells)
                path.addRect(QRectF(min(xs) - X0, min(zs) - Z0, max(xs) - min(xs) + 1, max(zs) - min(zs) + 1))
            else:
                for wx, wz in cells:
                    path.addRect(QRectF(wx - X0, wz - Z0, 1, 1))
            pen = QPen(QColor(255, 255, 255, 230), 1.5)
            pen.setCosmetic(True)
            p.setPen(pen)
            col = acc if page.tool == 'paint' else QColor(T.P['sky'] if page.height_mode != 'flatten' else T.P['gold'])
            p.setBrush(QColor(col.red(), col.green(), col.blue(), 70))
            p.drawPath(path.simplified())
            if page.tool == 'height':
                self.height_labels(p, isl, b)
        if page.tool == 'habitat' and page.stamp_ghost:
            ok, parts = page.stamp_ghost
            c = acc if ok else QColor(T.P['danger'])
            wpen = QPen(QColor(120, 200, 255), 1.4)
            wpen.setCosmetic(True)
            for x, z, bid in getattr(page, 'stamp_liquids', []):
                p.setPen(wpen)
                p.setBrush(QColor(60, 150, 230, 150) if bid != 386 else QColor(255, 120, 30, 150))
                p.drawRect(QRectF(x - X0, z - Z0, 1, 1))
            pen = QPen(c, 1.6)
            pen.setCosmetic(True)
            for var, x, y, z, d in parts:
                item, w, h, dp = pi.part_size(var)
                bx0, bz0, bx1, bz1 = pi.box_of(x, z, d, w, dp)
                rect = QRectF(bx0 - X0, bz0 - Z0, bx1 - bx0 + 1, bz1 - bz0 + 1)
                p.setPen(pen)
                p.setBrush(QColor(c.red(), c.green(), c.blue(), 60))
                p.drawRect(rect)
                if item:
                    pm = page.app.assets.item(item, 48)
                    side = min(rect.width(), rect.height()) * 0.92
                    cc = rect.center()
                    p.setOpacity(0.9 if ok else 0.5)
                    p.drawPixmap(QRectF(cc.x() - side / 2, cc.y() - side / 2, side, side), pm, QRectF(0, 0, pm.width(), pm.height()))
                    p.setOpacity(1.0)
        # box selection
        if page.drag and page.drag.get('kind') in ('box', 'height_box'):
            a, bpt = page.drag['a'], page.drag['b']
            rect = QRectF(a, bpt).normalized()
            if page.drag['kind'] in ('height_box'):
                ax, az = page.world(a)
                bx, bz = page.world(bpt)
                rect = QRectF(min(ax, bx) - isl.x0, min(az, bz) - isl.z0,
                              abs(bx - ax) + 1, abs(bz - az) + 1)
            pen = QPen(acc, 1.2, Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 40))
            p.drawRect(rect)


def _height_label_text(page, col):
    y = col[2]
    m = page.height_mode
    if m == 'flatten':
        return f'Y {y} → {page.flatten_y}' if y != page.flatten_y else f'Y {y} ✓'
    return f'Y {y} → {y + 1 if m == "raise" else y - 1}'


def _draw_tag(p, pt, text, color='#ffffff'):
    f = T.font(9, QFont.Bold)
    p.setFont(f)
    w = QFontMetrics(f).horizontalAdvance(text) + 16
    r = QRectF(pt.x() + 16, pt.y() - 30, w, 22)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(10, 16, 24, 225))
    p.drawRoundedRect(r, 11, 11)
    p.setPen(QColor(color))
    p.drawText(r, Qt.AlignCenter, text)


def _overlay_height_labels(self, p, isl, b):
    """Ground height of each block around the cursor, plus a tag saying what a click will do."""
    page = self.page
    tr = p.worldTransform()
    s = tr.m11()
    X0, Z0 = isl.x0, isl.z0
    p.save()
    p.resetTransform()
    if s >= 16:
        f = T.font(max(7, min(11, s * 0.28)), QFont.DemiBold)
        p.setFont(f)
        for wx, wz in page.brush_cells(*b):
            col = isl.column(wx, wz)
            if not col:
                continue
            c = tr.map(QPointF(wx - X0 + 0.5, wz - Z0 + 0.5))
            r = QRectF(c.x() - 20, c.y() - 10, 40, 20)
            p.setPen(QColor(0, 0, 0, 170))
            p.drawText(r.translated(1, 1), Qt.AlignCenter, str(col[2]))
            p.setPen(QColor('#ffffff'))
            p.drawText(r, Qt.AlignCenter, str(col[2]))
    col = isl.column(*b)
    if col:
        _draw_tag(p, tr.map(QPointF(b[0] - X0 + 0.5, b[1] - Z0 + 0.5)), _height_label_text(page, col),
                  T.P['gold'] if page.height_mode == 'flatten' else '#ffffff')
    p.restore()


OverlayItem.height_labels = _overlay_height_labels


class ZoneLabel(QGraphicsItem):
    """Name tag for one area of the island file, readable at any zoom; click to fly there."""

    def __init__(self, page, zone, pos):
        super().__init__()
        self.page, self.zone = page, zone
        self.setPos(pos)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(7)
        self.hover = False
        f = T.font(9, QFont.DemiBold)
        self.f = f
        self.w = QFontMetrics(f).horizontalAdvance(zone.title) + 40
        self.setToolTip(zone.note)

    def boundingRect(self):
        return QRectF(-self.w / 2, -34, self.w, 28)

    def compact(self):
        x0, z0, x1, z1 = self.zone.box
        return self.zone.kind != 'island' and (x1 - x0) * self.page.view.zoom() < self.w * 1.1

    def paint(self, p, opt, widget=None):
        if not self.page.opts['areas']:
            return
        p.setRenderHint(QPainter.Antialiasing)
        if self.compact() and not self.hover:
            glyph = T.G.get(ZONE_GLYPH.get(self.zone.kind, 'pin'), '')
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.setBrush(QColor(10, 16, 24, 225))
            p.drawEllipse(QPointF(0, -20), 13, 13)
            p.drawPixmap(QRectF(-8, -28, 16, 16), T.glyph_pixmap(glyph, 16, T.P['accent']), QRectF(0, 0, 32, 32))
            return
        r = self.boundingRect()
        p.setPen(QPen(QColor(T.P['accent']) if self.hover else QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor(10, 16, 24, 225))
        p.drawRoundedRect(r, 14, 14)
        glyph = T.G.get(ZONE_GLYPH.get(self.zone.kind, 'pin'), '')
        p.drawPixmap(QRectF(r.left() + 9, r.top() + 6, 16, 16), T.glyph_pixmap(glyph, 16, T.P['accent']),
                     QRectF(0, 0, 32, 32))
        p.setFont(self.f)
        p.setPen(QColor('#ffffff'))
        p.drawText(r.adjusted(30, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, self.zone.title)

    def hoverEnterEvent(self, e):
        self.hover = True
        self.setZValue(7.5)
        self.update()

    def hoverLeaveEvent(self, e):
        self.hover = False
        self.setZValue(7)
        self.update()

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        self.page.fly_zone(self.zone)


class HomeMarker(QGraphicsItem):
    """A resident portrait pin that keeps its screen size at every zoom."""
    R = 15

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
        return QRectF(-90, -self.R * 2 - 16, 180, self.R * 2 + 44)

    def paint(self, p, opt, widget=None):
        z = self.page.view.zoom()
        if self.page.tool not in ('select', 'pick') and not self.hover and z > ICON_ZOOM:
            p.setOpacity(0.55)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hl = self.index == self.page.highlight or self.hover
        if not hl and z < 3.5:
            # zoomed out: a small portrait dot, so neighbouring homes stay readable
            r = 7 if z < 1.5 else 9
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#ffffff'))
            p.drawEllipse(QPointF(0, -r), r + 1.6, r + 1.6)
            pm = self.page.app.assets.villager(self.index, 2 * r, circle=True)
            p.drawPixmap(QRectF(-r, -2 * r, 2 * r, 2 * r), pm, QRectF(0, 0, pm.width(), pm.height()))
            return
        R = self.R + (4 if hl else 0)
        cy = -R - 9
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
        if hl or z >= 22:
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
        if self.page.tool not in ('select', 'pick'):
            e.ignore()
            return
        e.accept()

    def mouseReleaseEvent(self, e):
        self.page.open_resident(self.index)


# ------------------------------------------------------------------------------------------------ the view
class MapView(QGraphicsView):
    zoomed = Signal(float)

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet('QGraphicsView { background: transparent; border: none; }')
        self.anim = None
        self.pan = None
        self.space = False


    def zoom(self):
        return self.transform().m11()

    def set_zoom(self, z, anchor=None):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
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
        self.set_zoom(self.zoom() * (1.2 ** steps), e.position().toPoint())

    def scene_pt(self, e):
        return self.mapToScene(e.position().toPoint())

    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self.space):
            self.pan = e.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        item = self.itemAt(e.position().toPoint())
        if isinstance(item, (ZoneLabel, HomeMarker)) and e.button() == Qt.LeftButton:
            if not (isinstance(item, HomeMarker) and self.page.tool not in ('select', 'pick')):
                return super().mousePressEvent(e)
        if not self.page.press(self.scene_pt(e), e):
            # nothing handled it: pan with the left button
            if e.button() in (Qt.LeftButton, Qt.RightButton):
                self.pan = e.position()
                self.viewport().setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self.pan is not None:
            d = e.position() - self.pan
            self.pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            self.page.minimap.update()
            return
        super().mouseMoveEvent(e)
        self.page.move(self.scene_pt(e), e)

    def mouseReleaseEvent(self, e):
        if self.pan is not None:
            self.pan = None
            self.viewport().setCursor(self.page.cursor_for_tool())
            return
        super().mouseReleaseEvent(e)
        self.page.release(self.scene_pt(e), e)

    def mouseDoubleClickEvent(self, e):
        if self.page.tool == 'select':
            self.fly_to(self.scene_pt(e), self.zoom() * 2)

    def leaveEvent(self, e):
        self.page.brush_at = None
        self.page.ghost = None
        self.page.overlay.update()
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self.space = True
            self.viewport().setCursor(Qt.OpenHandCursor)
            return
        if not self.page.key(e):
            k = e.key()
            if k in (Qt.Key_Plus, Qt.Key_Equal):
                self.set_zoom(self.zoom() * 1.4)
            elif k == Qt.Key_Minus:
                self.set_zoom(self.zoom() / 1.4)
            elif k == Qt.Key_0:
                self.page.fit(True)
            else:
                super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self.space = False
            self.viewport().setCursor(self.page.cursor_for_tool())
            return
        super().keyReleaseEvent(e)

    def fly_to(self, scene_pt, zoom, ms=420):
        if self.anim:
            self.anim.stop()
        c0 = self.mapToScene(self.viewport().rect().center())
        z0 = self.zoom()
        z1 = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
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
        bg = T.c('mapbg')
        p.fillRect(rect, bg)
        s = self.zoom()
        if s >= 0.5:
            # faint dots on the chunk grid so empty space still shows scale
            col = QColor(255, 255, 255, 16) if T.NAME == 'dark' else QColor(0, 0, 0, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            step = 32
            r = 1.2 / s
            x0, z0 = int(rect.left()) // step * step, int(rect.top()) // step * step
            for x in range(x0, int(rect.right()) + step, step):
                for z in range(z0, int(rect.bottom()) + step, step):
                    p.drawEllipse(QPointF(x, z), r, r)

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if hasattr(self.page, 'minimap'):
            self.page.minimap.update()
        if hasattr(self.page, 'stack_button'):
            self.page.position_stack_button()


class ToolBox(QFrame):
    """The floating tool bar; widens to show each tool's name and key while the mouse is over it."""

    def __init__(self, page):
        super().__init__(page.view)
        self.page = page
        self.anim = None

    def set_expanded(self, on):
        for b in self.page.tool_btns.values():
            b.setText(b.property('label') if on else '')
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if on else Qt.ToolButtonIconOnly)
            b.setMinimumWidth(190 if on else 0)
        self.adjustSize()
        self.raise_()

    def enterEvent(self, e):
        self.set_expanded(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.set_expanded(False)
        super().leaveEvent(e)


class ScaleBar(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.resize(180, 30)

    def paintEvent(self, e):
        z = self.view.zoom()
        target = 110 / z
        nice = min((1, 2, 5, 10, 20, 50, 100, 200, 500), key=lambda n: abs(n - target))
        w = nice * z
        if self.width() != int(w + 80):
            self.resize(int(w + 80), 30)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(10, 16, 24, 190))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w + 74, 26), 8, 8)
        p.setPen(QPen(QColor('#ffffff'), 2))
        p.drawLine(QPointF(10, 17), QPointF(10 + w, 17))
        p.drawLine(QPointF(10, 12), QPointF(10, 21))
        p.drawLine(QPointF(10 + w, 12), QPointF(10 + w, 21))
        p.setFont(T.font(8, QFont.Bold))
        p.drawText(QRectF(16 + w, 4, 64, 18), Qt.AlignVCenter | Qt.AlignLeft, f'{nice} block{"s" if nice > 1 else ""}')


class Minimap(QWidget):
    """Overview of the current area with the visible part outlined; click or drag to move there."""
    SIZE = 188

    def __init__(self, page):
        super().__init__(page.view)
        self.page = page
        self.setCursor(Qt.PointingHandCursor)
        self.resize(self.SIZE, self.SIZE)
        self.box = None

    def area(self):
        v = self.page.view_data
        if not v:
            return None
        isl = v.isl
        c = self.page.view.mapToScene(self.page.view.viewport().rect().center())
        z = isl.zone_at(int(c.x()) + isl.x0, int(c.y()) + isl.z0) or isl.zones[0]
        x0, z0, x1, z1 = z.box
        return QRectF(x0 - isl.x0 - 8, z0 - isl.z0 - 8, x1 - x0 + 17, z1 - z0 + 17)

    def geom(self):
        src = self.area()
        if src is None:
            return None, None, 1
        S = self.SIZE - 12
        f = min(S / src.width(), S / src.height())
        w, h = src.width() * f, src.height() * f
        tgt = QRectF((self.SIZE - w) / 2, (self.SIZE - h) / 2, w, h)
        return src, tgt, f

    def paintEvent(self, e):
        v = self.page.view_data
        if not v or not self.page.opts['minimap']:
            return
        src, tgt, f = self.geom()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(8, 13, 19, 225))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.SIZE - 1, self.SIZE - 1), 12, 12)
        p.drawPixmap(tgt, v.base_pm, src)
        p.setOpacity(0.8)
        p.drawPixmap(tgt, v.objects_pm, src)
        p.setOpacity(1)
        vr = self.page.view.mapToScene(self.page.view.viewport().rect()).boundingRect()
        rr = QRectF(tgt.left() + (vr.left() - src.left()) * f, tgt.top() + (vr.top() - src.top()) * f,
                    vr.width() * f, vr.height() * f).intersected(tgt.adjusted(-2, -2, 2, 2))
        p.setPen(QPen(QColor('#ffffff'), 1.5))
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRect(rr)

    def go(self, pos):
        src, tgt, f = self.geom()
        if src is None:
            return
        x = src.left() + (pos.x() - tgt.left()) / f
        z = src.top() + (pos.y() - tgt.top()) / f
        self.page.view.centerOn(QPointF(x, z))

    def mousePressEvent(self, e):
        self.go(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.go(e.position())


class IconGrid(QListWidget):
    """Icon palette (blocks or objects)."""

    def __init__(self, size=40):
        super().__init__()
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(size, size))
        self.setGridSize(QSize(size + 14, size + 14))
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setMinimumHeight(220)
        self.setStyleSheet(f'QListWidget {{ background: {T.P["tile"]}; border: 1px solid {T.P["line"]}; border-radius: 10px; padding: 4px; }}'
                           f'QListWidget::item {{ border-radius: 8px; }}'
                           f'QListWidget::item:hover {{ background: {T.P["tilehi"]}; }}'
                           f'QListWidget::item:selected {{ background: {T.P["sel"]}; border: 1px solid {T.P["accent"]}; }}')


# ------------------------------------------------------------------------------------------------ the page
class MapPage(Page):
    title, nav, glyph = 'Island Map', 'Island Map', T.G['map']
    subtitle = 'See and edit your islands: objects, ground, paths, habitats and homes'

    def build(self):
        self.area, self.pending, self.highlight, self.view_data = None, None, None, None
        self.loading = set()
        self.opts = dict(textures=True, contours=False, objects=True, icons=True, homes=True, habitats=True,
                         grid=False, areas=True, minimap=True, discoveries=True)
        self.tool = 'select'
        self.selection = []
        self.sel_habitat = None
        self.hover_habitat = None
        self.hover_obj = None
        self.ghost = None
        self.brush_at = None
        self.layer_cell = None
        self.layer_area = None
        self.layer_levels = []
        self.stack_height = None
        self.brush = 1
        self.height_brush = 3
        self.brush_shape = self.height_brush_shape = 'circle'
        self.brush_depth, self.height_brush_depth = 1, 3
        self.brush_controls = {}
        self.height_mode, self.flatten_y, self.show_heights = 'raise', 40, True
        self.recipes, self.recipe_sources, self.recipe = {}, set(), None
        self.stamp_rot, self.stamp_ghost, self.pick_cut, self.stamp_liquids = 0, None, False, []
        self.drag = None
        self.place_var, self.place_dir = None, 0
        self.paint_block = 3
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
        self.view.zoomed.connect(self.zoom_changed)
        ml.addWidget(self.view, 1)
        self.scalebar = ScaleBar(self.view)
        self.minimap = Minimap(self)
        self.stack_button = QToolButton(self.view.viewport())
        self.stack_button.setIcon(T.glyph_icon(T.G['layers'], 'accent', 20))
        self.stack_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.stack_button.setToolTip('Open the contents stacked at this tile')
        self.stack_button.clicked.connect(self.open_tile_contents)
        self.stack_button.hide()
        # tool bar
        self.toolbox = ToolBox(self)
        self.toolbox.setStyleSheet(f'QFrame#Tools {{ background: rgba(10,16,24,0.88); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; }}'
                                   f'QToolButton {{ border: none; border-radius: 10px; padding: 6px; background: transparent; color: #e9eff5; text-align: left; font-weight: 600; }}'
                                   f'QToolButton:checked {{ color: {T.P["onaccent"]}; }}'
                                   f'QToolButton:hover {{ background: rgba(255,255,255,0.08); }}'
                                   f'QToolButton:checked {{ background: {T.P["accent"]}; }}')
        self.toolbox.setObjectName('Tools')
        tb = QVBoxLayout(self.toolbox)
        tb.setContentsMargins(6, 6, 6, 6)
        tb.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_btns = {}
        for key, name, sc in TOOLS:
            b = QToolButton()
            ic = QIcon()
            ic.addPixmap(tool_icon(key, '#e9eff5'), QIcon.Normal, QIcon.Off)
            ic.addPixmap(tool_icon(key, T.P['onaccent']), QIcon.Normal, QIcon.On)
            b.setIcon(ic)
            b.setIconSize(QSize(22, 22))
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(f'{name}  ({sc})')
            b.setText(f'  {name}')
            b.setProperty('label', f'  {name}   {sc}')
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().verticalPolicy())
            b.clicked.connect(lambda _=False, k=key: self.set_tool(k))
            self.tool_group.addButton(b)
            self.tool_btns[key] = b
            tb.addWidget(b)
        self.tool_btns['select'].setChecked(True)
        # zoom buttons
        self.zoombox = QFrame(self.view)
        zb = QVBoxLayout(self.zoombox)
        zb.setContentsMargins(0, 0, 0, 0)
        zb.setSpacing(4)
        for glyph, tip, fn in ((T.G['add'], 'Zoom in (+)', lambda: self.view.set_zoom(self.view.zoom() * 1.5)),
                               (T.G['remove'], 'Zoom out (−)', lambda: self.view.set_zoom(self.view.zoom() / 1.5)),
                               (T.G['fit'], 'Fit the island (0)', lambda: self.fit(True)),
                               (T.G['globe'], 'Show the whole file, with every area', lambda: self.fit(False))):
            b = W.button('', glyph, fn, tip=tip)
            b.setFixedSize(36, 36)
            zb.addWidget(b)
        self.overlay_msg = W.label('', 'h3')
        self.overlay_msg.setParent(self.view)
        self.overlay_msg.setAlignment(Qt.AlignCenter)
        self.overlay_msg.setStyleSheet(f'background: {T.P["card"]}; border: 1px solid {T.P["line2"]}; border-radius: 12px; padding: 14px 22px;')
        self.overlay_msg.hide()
        self.hint = QLabel(self.view)
        self.hint.setStyleSheet('background: rgba(10,16,24,0.86); color: #e9eff5; border-radius: 10px; padding: 6px 12px;')
        self.hint.setAttribute(Qt.WA_TransparentForMouseEvents)
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
        side.setFixedWidth(330)
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
        zc = W.Card('Areas in this file', None, T.G['pin'], padding=12)
        self.zone_box = QVBoxLayout()
        self.zone_box.setSpacing(2)
        zc.body.addLayout(self.zone_box)
        self.zone_note = W.label('', 'muted', wrap=True)
        zc.body.addWidget(self.zone_note)
        sl.addWidget(zc)
        # tool panel
        self.tool_card = W.Card('Select', None, T.G['edit'], padding=12)
        self.tool_stack = QStackedWidget()
        self.tool_stack.currentChanged.connect(self._fit_stack)
        self.tool_card.body.addWidget(self.tool_stack)
        self.build_select_panel()
        self.build_place_panel()
        self.build_block_panel()
        self.build_height_panel()
        self.build_habitat_panel()
        sl.addWidget(self.tool_card)
        lc = W.Card('Map overlays', None, T.G['layers'], padding=12)
        self.layer_rows = {}
        for key, text, note in (('textures', 'Block textures', 'When zoomed in'), ('objects', 'Placed objects', ''),
                                ('icons', 'Object icons', 'When zoomed in close'), ('habitats', 'Habitats', ''),
                                ('homes', 'Resident homes', ''), ('areas', 'Area names', ''),
                                ('contours', 'Height lines', 'Every 4 blocks'), ('grid', 'Grid', 'Chunks, or blocks up close'),
                                ('minimap', 'Mini map', ''), ('discoveries', 'Glowing Blocks', 'Saved treasure spots, including buried ones')):
            row = W.ToggleRow(text, note)
            row.toggle.set_quiet(self.opts[key])
            row.toggle.toggled.connect(lambda on, k=key: self.set_opt(k, on))
            lc.body.addWidget(row)
            self.layer_rows[key] = row
        hc = W.Card('Height layers', None, T.G['layers'], padding=12)
        self.cut_row = W.ToggleRow('Limit visible height', 'Show this level and everything below')
        self.cut_row.toggle.toggled.connect(lambda on: self.apply_cut())
        hc.body.addWidget(self.cut_row)
        crow = QHBoxLayout()
        self.cut_slider = QSlider(Qt.Horizontal)
        self.cut_slider.setRange(1, 126)
        self.cut_slider.setValue(60)
        self.cut_lbl = W.label('Y 60', 'small')
        self.cut_lbl.setFixedWidth(44)
        self.cut_timer = QTimer(self, singleShot=True, interval=250, timeout=self.apply_cut)
        self.cut_slider.valueChanged.connect(lambda v: (self.cut_lbl.setText(f'Y {v}'), self.cut_timer.start()))
        crow.addWidget(self.cut_slider, 1)
        crow.addWidget(self.cut_lbl)
        hc.body.addLayout(crow)
        steps = QHBoxLayout()
        steps.addWidget(W.button('Lower level', T.G['down'], lambda: self.step_layer(-1), small=True))
        steps.addWidget(W.button('Higher level', T.G.get('up', T.G['chevron']), lambda: self.step_layer(1), small=True))
        hc.body.addLayout(steps)
        hc.body.addWidget(W.button('Show all heights', T.G['layers'], self.show_all_heights, small=True))
        self.cut_pick = W.button('Click a roof to look under it', T.G['pin'], self.start_pick_cut, small=True,
                                 tip='Then click a roof or ceiling on the map: everything from that height up is hidden')
        hc.body.addWidget(self.cut_pick)
        self.layer_summary = W.label('Click a map cell with Select to inspect its vertical contents.', 'muted', wrap=True)
        hc.body.addWidget(self.layer_summary)
        self.layer_tree = QTreeWidget()
        self.layer_tree.setColumnCount(1)
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.setIconSize(QSize(24, 24))
        self.layer_tree.setMinimumHeight(100)
        self.layer_tree.setMaximumHeight(220)
        self.layer_tree.setWordWrap(True)
        self.layer_tree.itemClicked.connect(self.choose_layer)
        self.layer_tree.hide()
        hc.body.addWidget(self.layer_tree)
        sl.insertWidget(1, hc)
        sl.addWidget(lc)
        rc = W.Card('Residents here', None, T.G['people'], padding=12)
        self.res_list = QListWidget()
        self.res_list.setIconSize(QSize(28, 28))
        self.res_list.setStyleSheet('QListWidget::item { padding: 4px 6px; border-radius: 8px; }'
                                    f'QListWidget::item:hover {{ background: {T.P["tilehi"]}; }}'
                                    f'QListWidget::item:selected {{ background: {T.P["sel"]}; color: {T.P["text"]}; }}')
        self.res_list.setMinimumHeight(170)
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
        self.terrain = self.objects_item = self.habitats_item = self.grid_item = self.overlay = None
        self.markers, self.zone_labels = [], []
        self._fit_stack()
        self.update_hint()

    # ---------- side panels ----------
    def _fit_stack(self, _=None):
        from PySide6.QtWidgets import QSizePolicy
        cur = self.tool_stack.currentWidget()
        for i in range(self.tool_stack.count()):
            w = self.tool_stack.widget(i)
            w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if w is cur else QSizePolicy.Ignored)
        self.tool_stack.adjustSize()

    def build_select_panel(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        head = QHBoxLayout()
        self.sel_icon = QLabel()
        self.sel_icon.setFixedSize(52, 52)
        self.sel_icon.setAlignment(Qt.AlignCenter)
        self.sel_icon.setStyleSheet(f'background: {T.P["tile"]}; border-radius: 12px;')
        head.addWidget(self.sel_icon, 0, Qt.AlignTop)
        hv = QVBoxLayout()
        hv.setSpacing(1)
        self.sel_name = W.label('Nothing selected', 'h3')
        self.sel_sub = W.label('Click an object, or Shift-drag a box around several', 'muted', wrap=True)
        hv.addWidget(self.sel_name)
        hv.addWidget(self.sel_sub)
        hv.addStretch(1)
        head.addLayout(hv, 1)
        v.addLayout(head)
        self.sel_info = W.label('', 'small', wrap=True)
        v.addWidget(self.sel_info)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.sel_btns = {}
        for n, (key, text, glyph, tip) in enumerate((
                ('rotate', 'Rotate', T.G['refresh'], 'Turn 90° (R)'),
                ('dup', 'Duplicate', T.G['copy'], 'Copy next to it (Ctrl+D)'),
                ('up', 'Up', T.G['chevron'], 'One block higher (Page Up)'),
                ('down', 'Down', T.G['down'], 'One block lower (Page Down)'),
                ('ground', 'To ground', T.G['pin'], 'Set down on the ground (G)'),
                ('delete', 'Delete', T.G['delete'], 'Remove from the island (Delete)'))):
            b = W.button(text, glyph, lambda k=key: self.sel_action(k), danger=key == 'delete', small=True, tip=tip)
            grid.addWidget(b, n // 2, n % 2)
            self.sel_btns[key] = b
        v.addLayout(grid)
        self.sel_hint = W.label('Drag a selected object to move it. Arrow keys nudge by one block. '
                                'Esc clears the selection.', 'muted', wrap=True)
        v.addWidget(self.sel_hint)
        self.tool_stack.addWidget(w)
        self.select_panel = w

    def build_place_panel(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.place_search = W.SearchField('Search objects')
        self.place_search.textChanged.connect(self.fill_place_grid)
        v.addWidget(self.place_search)
        self.place_grid = IconGrid(40)
        self.place_grid.setMinimumHeight(300)
        self.place_grid.currentItemChanged.connect(self.place_chosen)
        v.addWidget(self.place_grid)
        self.place_info = W.label('', 'small', wrap=True)
        v.addWidget(self.place_info)
        v.addWidget(W.label('Click to place, drag to place a row. R turns it. Right-click or Esc to stop.', 'muted', wrap=True))
        self.tool_stack.addWidget(w)
        self.place_panel = w
        self._place_filled = False

    def build_block_panel(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignTop)
        self.block_search = W.SearchField('Search blocks')
        self.block_search.textChanged.connect(self.fill_block_grid)
        v.addWidget(self.block_search)
        self.block_grid = IconGrid(36)
        self.block_grid.currentItemChanged.connect(self.block_chosen)
        v.addWidget(self.block_grid)
        self.build_brush_controls(v, height=False)
        self.block_info = W.label('', 'small', wrap=True)
        v.addWidget(self.block_info)
        self.block_hint = W.label('', 'muted', wrap=True)
        v.addWidget(self.block_hint)
        self.tool_stack.addWidget(w)
        self.block_panel = w
        self._blocks_filled = False

    def build_brush_controls(self, layout, height):
        shape = QComboBox()
        for label, value in (('Circle', 'circle'), ('Square', 'square'), ('Rectangle', 'rectangle')):
            shape.addItem(label, value)
        layout.addWidget(W.label('Brush shape', 'small'))
        layout.addWidget(shape)
        width, depth = QSpinBox(), QSpinBox()
        for spin in (width, depth):
            spin.setRange(1, 32)
            spin.setSuffix(' cells')
        width.setValue(self.height_brush if height else self.brush)
        depth.setValue(width.value())
        for label, spin in (('Width', width), ('Depth', depth)):
            row = QHBoxLayout()
            row.addWidget(W.label(label, 'small'))
            row.addWidget(spin, 1)
            layout.addLayout(row)
        count = W.label('', 'small', wrap=True)
        layout.addWidget(count)
        self.brush_controls[height] = (shape, width, depth, count)
        if height:
            self.hbrush_slider = width  # keyboard shortcuts use setValue
        else:
            self.brush_slider = width
        shape.currentIndexChanged.connect(lambda _: self.update_brush_controls(height))
        width.valueChanged.connect(self.set_height_brush if height else self.set_brush)
        depth.valueChanged.connect(lambda _: self.update_brush_controls(height))
        self.update_brush_controls(height)

    def update_brush_controls(self, height):
        shape, width, depth, count = self.brush_controls[height]
        selected = shape.currentData()
        rectangle = selected == 'rectangle'
        depth.setEnabled(rectangle)
        if not rectangle:
            depth.blockSignals(True)
            depth.setValue(width.value())
            depth.blockSignals(False)
        if height:
            self.height_brush_shape, self.height_brush_depth = selected, depth.value()
        else:
            self.brush_shape, self.brush_depth = selected, depth.value()
        cells = len(brush_offsets(selected, width.value(), depth.value()))
        count.setText(f'{width.value()} × {depth.value()} cells · {cells} cells in brush')
        getattr(self, 'overlay', None) and self.overlay.update()

    def build_height_panel(self):
        from PySide6.QtWidgets import QCheckBox, QSpinBox
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignTop)
        seg = QHBoxLayout()
        seg.setSpacing(4)
        self.height_btns = {}
        grp = QButtonGroup(self)
        for key, text, tip in HEIGHT_MODES:
            b = W.chip(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.set_height_mode(k))
            grp.addButton(b)
            seg.addWidget(b)
            self.height_btns[key] = b
        grp.setExclusive(True)
        self.height_btns['raise'].setChecked(True)
        v.addLayout(seg)
        frow = QHBoxLayout()
        frow.addWidget(W.label('Flatten to height', 'small'))
        self.flat_spin = QSpinBox()
        self.flat_spin.setRange(1, 126)
        self.flat_spin.setValue(self.flatten_y)
        self.flat_spin.setPrefix('Y ')
        self.flat_spin.valueChanged.connect(self.set_flatten_y)
        frow.addWidget(self.flat_spin)
        frow.addStretch(1)
        self.flat_row = QWidget()
        self.flat_row.setLayout(frow)
        v.addWidget(self.flat_row)
        self.build_brush_controls(v, height=True)
        self.lift_objects_check = QCheckBox('Move objects and placed items up')
        self.lift_objects_check.setToolTip(
            'When raising ground, lift objects in the way and anything stacked above them. '
            'Keeps their arrangement. Does not move loose drops or Glowing Blocks. '
            'Lowering ground leaves objects in place.')
        v.addWidget(self.lift_objects_check)
        self.heights_check = QCheckBox('Colour the map by height')
        self.heights_check.setChecked(True)
        self.heights_check.toggled.connect(self.set_show_heights)
        v.addWidget(self.heights_check)
        self.height_legend = QLabel()
        self.height_legend.setFixedHeight(26)
        v.addWidget(self.height_legend)
        self.height_hint = W.label('', 'muted', wrap=True)
        v.addWidget(self.height_hint)
        self.tool_stack.addWidget(w)
        self.height_panel = w
        self.set_height_mode('raise')

    def height_legend_pixmap(self):
        from gui.maprender import HEIGHT_RAMP
        W_, H_ = 280, 26
        pm = QPixmap(W_, H_)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        lo, hi = 24, 72
        for x in range(W_):
            yv = lo + (hi - lo) * x / (W_ - 1)
            r, g, b = HEIGHT_RAMP[int(yv)]
            p.fillRect(x, 0, 1, 12, QColor(r, g, b))
        p.setPen(QColor(T.P['muted']))
        p.setFont(T.font(7.5))
        for yv in (24, 31, 40, 50, 60, 72):
            x = (yv - lo) / (hi - lo) * (W_ - 1)
            p.drawText(QRectF(x - 18, 12, 36, 14), Qt.AlignCenter, f'Y {yv}' if yv != 31 else 'sea')
        p.end()
        return pm

    def set_height_mode(self, key):
        self.height_mode = key
        self.height_btns[key].setChecked(True)
        self.flat_row.setVisible(key == 'flatten')
        self.height_hint.setText({
            'raise': 'Click to add one layer of ground under the brush. Dragging adds one layer to every block you '
                     'pass over. Right-click lowers instead. Ground with objects standing on it is left alone.',
            'lower': 'Click to take one layer of ground away. Dragging lowers every block you pass over by one. '
                     'Right-click raises instead.',
            'flatten': 'Set the height above, or right-click the map to copy the height of that spot. Then drag: '
                       'every block under the brush is raised or lowered to it.',
        }[key])
        self.update_hint()
        getattr(self, 'overlay', None) and self.overlay.update()

    def set_flatten_y(self, y):
        self.flatten_y = y
        if self.tool == 'height':
            self.update_hint()
        getattr(self, 'overlay', None) and self.overlay.update()

    def set_height_brush(self, n):
        self.height_brush = n
        self.update_brush_controls(height=True)
        getattr(self, 'overlay', None) and self.overlay.update()

    def set_show_heights(self, on):
        self.show_heights = on
        getattr(self, 'terrain', None) and self.terrain.update()

    def build_habitat_panel(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.recipe_search = W.SearchField('Search habitats')
        self.recipe_search.textChanged.connect(self.fill_recipes)
        v.addWidget(self.recipe_search)
        self.recipe_list = QListWidget()
        self.recipe_list.setIconSize(QSize(30, 30))
        self.recipe_list.setMinimumHeight(260)
        self.recipe_list.setStyleSheet('QListWidget::item { padding: 3px 6px; border-radius: 8px; }'
                                       f'QListWidget::item:hover {{ background: {T.P["tilehi"]}; }}'
                                       f'QListWidget::item:selected {{ background: {T.P["sel"]}; color: {T.P["text"]}; }}')
        self.recipe_list.currentItemChanged.connect(self.recipe_chosen)
        v.addWidget(self.recipe_list)
        self.recipe_info = W.label('', 'small', wrap=True)
        v.addWidget(self.recipe_info)
        v.addWidget(W.label('Each habitat is built from the least it needs, packed close together. Water and '
                            'other liquids are dug into the ground next to it. Click the map to build it there; '
                            'R turns it. The game checks habitats again when it loads.', 'muted', wrap=True))
        self.tool_stack.addWidget(w)
        self.habitat_panel = w

    def load_recipes(self):
        """Minimum requirements per habitat, from data/habitat_recipes.json (tools/build_habitat_recipes.py)."""
        if self.recipes:
            return
        import json
        try:
            with open(os.path.join(pi.DATA, 'habitat_recipes.json'), encoding='utf-8') as f:
                rows = json.load(f)
        except (OSError, ValueError):
            rows = []
        self.recipes = {f'{r["dex"]}': r for r in rows}

    def recipe_needs(self, r):
        """Readable list of what a recipe places."""
        out = []
        for p in r['parts']:
            if p['kind'] == 'item':
                exact = ps.item_name(p['item']).lower() == p['label'].lower()
                out.append(f'{p["count"]} × {ps.item_name(p["item"])}' + ('' if exact else f' (for "{p["label"]}")'))
            elif p['kind'] == 'liquid':
                out.append(f'{p["count"]} × {p["label"].lower()} (dug into the ground)')
        return out

    def recipe_notes(self, r):
        return [p['note'] for p in r['parts'] if p['kind'] == 'note']

    def fill_recipes(self):
        self.load_recipes()
        q = self.recipe_search.text().strip().lower()
        self.recipe_list.blockSignals(True)
        cur = self.recipe['dex'] if self.recipe else None
        self.recipe_list.clear()
        sel = None
        have = set()
        if self.view_data:
            have = {h.type for h in self.view_data.isl.habitats}
        for key, r in sorted(self.recipes.items(), key=lambda kv: kv[1]['name'].lower()):
            needs = self.recipe_needs(r)
            if q and q not in r['name'].lower() and not any(q in n.lower() for n in needs):
                continue
            item = next((p['item'] for p in r['parts'] if p['kind'] == 'item'), 0)
            mark = '  ✓' if r.get('type') in have else ''
            it = QListWidgetItem(QIcon(self.app.assets.item(item, 30)) if item else QIcon(), f'  {r["name"]}{mark}')
            it.setToolTip('\n'.join(needs + self.recipe_notes(r))
                          + ('\nYou already have this habitat on this island.' if mark else ''))
            it.setData(Qt.UserRole, key)
            self.recipe_list.addItem(it)
            if key == cur:
                sel = it
        if sel:
            self.recipe_list.setCurrentItem(sel)
        self.recipe_list.blockSignals(False)

    def recipe_chosen(self, it, _=None):
        if not it:
            return
        self.recipe = self.recipes.get(it.data(Qt.UserRole))
        r = self.recipe
        if not r:
            return
        notes = self.recipe_notes(r)
        self.recipe_info.setText(f'{r["name"]}\n' + '\n'.join(self.recipe_needs(r))
                                 + (f'\nAlso: {"; ".join(notes)}' if notes else ''))
        if self.brush_at:
            self.stamp_ghost = self.stamp_parts(*self.brush_at)
            self.overlay and self.overlay.update()

    def recipe_layout(self, r):
        """Pieces of a recipe packed into a tight block: ([(variation, dx, dz, dir, on_table)], liquids [(dx, dz, block)],
        width, depth). Plated food goes on top of a table when there is one."""
        items = []
        table_var = None
        for p in r['parts']:
            if p['kind'] != 'item':
                continue
            for _ in range(p['count']):
                items.append((p['var'], p['label'].lower()))
            if 'table' in p['label'].lower() and table_var is None:
                table_var = p['var']
        food = [it for it in items if it[1] == 'plated food'] if table_var else []
        ground = [it for it in items if it not in food] if food else items
        sizes = [(var, pi.part_size(var)[1], pi.part_size(var)[3], lab) for var, lab in ground]
        sizes.sort(key=lambda t: -(t[1] * t[2]))
        area = sum(w * d for _, w, d, _ in sizes)
        row_w = max(max((w for _, w, _, _ in sizes), default=1), int(math.ceil(math.sqrt(area))))
        out, x, z, rowd = [], 0, 0, 0
        for var, w, d, lab in sizes:
            if x and x + w > row_w:
                x, z, rowd = 0, z + rowd, 0
            # direction 0: anchor at the box's south-west cell (box spans x..x+w-1, z-d+1..z)
            out.append((var, x, z + d - 1, 0, False))
            x += w
            rowd = max(rowd, d)
        width = max((dx + pi.part_size(v)[1] for v, dx, _, _, _ in out), default=1)
        depth = z + rowd
        if food:
            t = next(o for o in out if o[0] == table_var)
            for var, _ in food:
                out.append((var, t[1], t[2], 0, True))
        liquids = []
        k = 0
        for p in r['parts']:
            if p['kind'] == 'liquid':
                for _ in range(p['count']):
                    liquids.append((k % max(1, width), depth + k // max(1, width), p['block']))
                    k += 1
        if liquids:
            depth += (k - 1) // max(1, width) + 1
        return out, liquids, width, depth

    def stamp_parts(self, ax, az):
        """Pieces of the chosen recipe with the block's corner at (ax, az): (ok, [(var, x, y, z, dir)])."""
        r, isl = self.recipe, self.isl()
        self.stamp_liquids = []
        if not r or not isl:
            return False, []
        pieces, liquids, W_, D_ = self.recipe_layout(r)
        rot = self.stamp_rot % 4

        def turn(cx, cz):
            ww, dd = W_, D_
            for _ in range(rot):
                cx, cz = cz, (ww - 1) - cx
                ww, dd = dd, ww
            return cx, cz
        placed, ok = [], True
        tops = {}
        for var, dx, dz, d, on_table in pieces:
            _, w, h, dp = pi.part_size(var)
            bx0, bz0, bx1, bz1 = pi.box_of(dx, dz, d, w, dp)
            cx, cz = turn((bx0 + bx1) / 2, (bz0 + bz1) / 2)
            nd = (d + rot) % 4
            nx0, nz0, nx1, nz1 = pi.box_of(0, 0, nd, w, dp)
            x, z = ax + round(cx - (nx0 + nx1) / 2), az + round(cz - (nz0 + nz1) / 2)
            if on_table:
                y = tops.get((x, z))
                if y is None:
                    ok = False
                    y = 0
            else:
                y = isl.ground_y(var, x, z, nd)
                if y is None:
                    ok = False
                    y = 0
                else:
                    for c in isl._cells_of(var, x, y, z, nd):
                        tops[(c[0], c[2])] = max(tops.get((c[0], c[2]), 0), y + h)
            if isl.blocked(var, x, y, z, nd):
                ok = False
            placed.append((var, x, y, z, nd))
        cells = set()
        for var, x, y, z, d in placed:
            for c in isl._cells_of(var, x, y, z, d):
                if c[:3] in cells:
                    ok = False
                cells.add(c[:3])
        for dx, dz, bid in liquids:
            cx, cz = turn(dx, dz)
            x, z = ax + int(cx), az + int(cz)
            col = isl.column(x, z)
            if not col or col[0] != col[2] or any(True for _ in isl.objects_in(x, z, x, z)):
                ok = False
            self.stamp_liquids.append((x, z, bid))
        return ok, placed

    def stamp_here(self, wx, wz):
        ok, parts = self.stamp_parts(wx, wz)
        if not parts and not self.stamp_liquids:
            return
        if not ok:
            return self.app.toast('Not enough free, dry ground here for this habitat.', 'err')
        isl = self.isl()
        try:
            for x, z, bid in self.stamp_liquids:
                isl.set_liquid([(x, z)], bid)
            isl.refresh()
            for var, x, y, z, d in sorted(parts, key=lambda t: t[2]):
                isl.add_object(var, x, y, z, d)
        except pi.EditError as ex:
            return self.fail(ex)
        self.commit(f'Built a habitat: {self.recipe["name"]}')

    def fill_place_grid(self):
        q = self.place_search.text().strip().lower()
        self.place_grid.blockSignals(True)
        self.place_grid.clear()
        items = self.placeable()
        sel = None
        for item, var, (w, h, d) in items:
            name = ps.item_name(item)
            if q and q not in name.lower():
                continue
            it = QListWidgetItem(QIcon(self.app.assets.item(item, 40)), '')
            it.setData(Qt.UserRole, (item, var))
            it.setToolTip(f'{name}\n{w} × {d} blocks, {h} high')
            self.place_grid.addItem(it)
            if var == self.place_var:
                sel = it
        if sel:
            self.place_grid.setCurrentItem(sel)
        self.place_grid.blockSignals(False)
        self._place_filled = True

    def placeable(self):
        if not hasattr(self, '_placeable'):
            seen, out = set(), []
            px.map_part(0)
            for var, (base, item, w, h, d, _) in sorted(px._MAP_PARTS.items()):
                if item and item not in seen and ps.item_name(item) and not ps.item_name(item).startswith('Item '):
                    seen.add(item)
                    out.append((item, var, (max(1, w), max(1, h), max(1, d))))
            out.sort(key=lambda t: ps.item_name(t[0]).lower())
            self._placeable = out
        return self._placeable

    def place_chosen(self, it, _=None):
        if not it:
            return
        item, var = it.data(Qt.UserRole)
        self.place_var = var
        _, w, h, d = pi.part_size(var)
        self.place_info.setText(f'{ps.item_name(item)}  ·  {w} × {d}, {h} high  ·  turned {ROT_NAMES[self.place_dir]}')
        if self.tool != 'place':
            self.set_tool('place')

    def fill_block_grid(self):
        q = self.block_search.text().strip().lower()
        self.block_grid.blockSignals(True)
        self.block_grid.clear()
        sel = None
        rows = sorted(pi.paintable_blocks(), key=lambda t: (t[2], ps.item_name(t[1]).lower()))
        for bid, item, kind in rows:
            name = ps.item_name(item)
            if q and q not in name.lower():
                continue
            it = QListWidgetItem(QIcon(self.app.assets.item(item, 36)), '')
            it.setData(Qt.UserRole, bid)
            it.setToolTip(f'{name}\n{"Natural ground" if kind == pi.K_TERRAIN else "Building block, floor or road"}')
            self.block_grid.addItem(it)
            if bid == self.paint_block:
                sel = it
        if sel:
            self.block_grid.setCurrentItem(sel)
        self.block_grid.blockSignals(False)
        self._blocks_filled = True
        self.block_chosen(self.block_grid.currentItem())

    def block_chosen(self, it, _=None):
        if it:
            self.paint_block = it.data(Qt.UserRole)
        self.block_info.setText(f'Block: {pi.block_name(self.paint_block)}')

    def set_brush(self, n):
        self.brush = n
        self.update_brush_controls(height=False)
        getattr(self, 'overlay', None) and self.overlay.update()

    # ---------- tools ----------
    def set_tool(self, key):
        if key == 'place' and self.place_var is None and self._place_filled and self.place_grid.count():
            self.place_grid.setCurrentRow(0)
        self.tool = key
        self.tool_btns[key].setChecked(True)
        self.drag = None
        self.ghost = None
        names = dict((k, n) for k, n, _ in TOOLS)
        self.tool_card.title_lbl.setText(names[key])
        if key in ('select', 'pick'):
            self.tool_stack.setCurrentWidget(self.select_panel)
        elif key == 'height':
            self.tool_stack.setCurrentWidget(self.height_panel)
            self.height_legend.setPixmap(self.height_legend_pixmap())
            getattr(self, 'terrain', None) and self.terrain.update()
        elif key == 'habitat':
            self.tool_stack.setCurrentWidget(self.habitat_panel)
            self.fill_recipes()
        elif key == 'place':
            if not self._place_filled:
                self.fill_place_grid()
            self.tool_stack.setCurrentWidget(self.place_panel)
        else:
            if not self._blocks_filled:
                self.fill_block_grid()
            self.tool_stack.setCurrentWidget(self.block_panel)
            self.block_hint.setText('Click or drag to repaint the ground with this block, for paths, plazas and '
                                    'gardens. The seabed can be painted too.')
            self.block_info.setText(f'Block: {pi.block_name(self.paint_block)}')
        self.view.viewport().setCursor(self.cursor_for_tool())
        self.position_stack_button()
        self.stamp_ghost = None
        getattr(self, 'terrain', None) and self.terrain.update()
        self.update_hint()
        self.update_inspector()
        if self.overlay:
            self.overlay.update()
        for mk in self.markers:
            mk.update()

    def cursor_for_tool(self):
        return Qt.ArrowCursor if self.tool == 'select' else Qt.CrossCursor

    def update_hint(self):
        text = {'select': 'Click to select  ·  Shift-drag to box-select  ·  drag empty ground to pan',
                'place': 'Click to place  ·  R to turn  ·  right-click to stop',
                'paint': 'Click or drag to paint  ·  [ ] brush size',
                'height': {'raise': 'Click: one layer higher  ·  right-click: lower  ·  [ ] brush size',
                           'lower': 'Click: one layer lower  ·  right-click: raise  ·  [ ] brush size',
                           'flatten': f'Drag to flatten to Y {self.flatten_y}  ·  right-click: copy a height  ·  [ ] brush size'}[self.height_mode],
                'habitat': 'Pick a habitat, then click where its corner goes  ·  R to turn',
                'pick': 'Click an object or the ground to copy it into a tool'}[self.tool]
        if self.tool == 'height':
            text += '  ·  Shift-drag: apply to a rectangle'
        self.hint.setText(text)
        self.hint.adjustSize()
        self.place_floating()

    def brush_cells(self, wx, wz):
        if self.tool == 'height':
            offsets = brush_offsets(self.height_brush_shape, self.height_brush, self.height_brush_depth)
        else:
            offsets = brush_offsets(self.brush_shape, self.brush, self.brush_depth)
        return [(wx + dx, wz + dz) for dx, dz in offsets]

    # ---------- floating widgets ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.place_floating)

    def place_floating(self):
        v = self.view
        self.zoombox.adjustSize()
        self.zoombox.move(v.width() - self.zoombox.width() - 14, 14)
        self.toolbox.adjustSize()
        self.toolbox.move(14, 14)
        self.scalebar.move(14, v.height() - self.scalebar.height() - 12)
        self.minimap.move(v.width() - self.minimap.width() - 14, v.height() - self.minimap.height() - 14)
        self.minimap.setVisible(self.opts['minimap'] and self.view_data is not None)
        self.hint.adjustSize()
        self.hint.move((v.width() - self.hint.width()) // 2, v.height() - self.hint.height() - 14)
        self.overlay_msg.adjustSize()
        self.overlay_msg.move((v.width() - self.overlay_msg.width()) // 2, (v.height() - self.overlay_msg.height()) // 2)
        self.position_stack_button()

    # ---------- islands ----------
    def save_changed(self):
        self.view_data, self.area = None, None
        self.selection, self.sel_habitat = [], None
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
        self.clear_scene()

    @property
    def data(self):
        return self.view_data

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
        if area == self.area and self.view_data:
            return
        if area in getattr(self, 'isl_buttons', {}):
            self.isl_buttons[area].setChecked(True)
        self.area, self.highlight, self.pending = area, None, None
        self.selection, self.sel_habitat = [], None
        self.ensure()

    def focus_home(self, v):
        self.pending = (v['home_area'], v['index'], v['home_xyz'])
        self.highlight = v['index']

    def message(self, text):
        if text:
            self.overlay_msg.setText(text)
            self.overlay_msg.show()
            self.place_floating()
        else:
            self.overlay_msg.hide()

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
        cache = self.app.map_cache
        cache[key] = result
        # keep memory in check: unedited islands other than the newest two are dropped
        keep = [k for k in cache if cache[k].isl.edited]
        rest = [k for k in cache if k not in keep]
        for k in rest[:-2]:
            del cache[k]
        if self.app.save and key[0] == self.app.save.folder:
            self.app.save.islands[key[1]] = result.isl
        if self.app.save and (self.app.save.folder, self.area) == key:
            self.show_island(result)

    def clear_scene(self):
        self.scene.clear()
        self.terrain = self.objects_item = self.habitats_item = self.grid_item = self.overlay = None
        self.markers, self.zone_labels = [], []
        self.view_data = None
        self.update_layer_inspector()
        self.place_floating()

    def show_island(self, v):
        fresh = v is not self.view_data
        if fresh:
            self.clear_scene()
            self.view_data = v
            if self.app.save:
                self.app.save.islands[self.area] = v.isl
            self.prepare_view(v)
            isl = v.isl
            self.scene.setSceneRect(QRectF(-400, -400, isl.width + 800, isl.height + 800))
            self.terrain = TerrainItem(self)
            self.scene.addItem(self.terrain)
            self.grid_item = GridItem(self)
            self.scene.addItem(self.grid_item)
            self.objects_item = ObjectsItem(self)
            self.scene.addItem(self.objects_item)
            self.habitats_item = HabitatsItem(self)
            self.scene.addItem(self.habitats_item)
            self.overlay = OverlayItem(self)
            self.scene.addItem(self.overlay)
            for z in isl.zones:
                x0, z0, x1, z1 = z.box
                lab = ZoneLabel(self, z, QPointF((x0 + x1 + 1) / 2 - isl.x0, z0 - isl.z0 - 2))
                self.scene.addItem(lab)
                self.zone_labels.append(lab)
        self.message('')
        layer_area = (self.app.save.folder, self.area)
        if self.layer_area != layer_area:
            self.layer_area = layer_area
            self.layer_cell = None
        if fresh:
            self.cut_row.toggle.set_quiet(v.isl.cut < 127)
            self.cut_slider.setEnabled(v.isl.cut < 127)
            self.cut_slider.blockSignals(True)
            self.cut_slider.setValue(min(v.isl.cut, 126))
            self.cut_slider.blockSignals(False)
            self.cut_lbl.setText(f'Y {self.cut_slider.value()}' if v.isl.cut < 127 else 'All')
        self.update_layer_inspector()
        self.update_markers()
        self.update_side()
        self.update_zones()
        self.update_inspector()
        self.place_floating()
        if self.pending and self.pending[0] == self.area:
            _, idx, (x, y, z) = self.pending
            self.pending = None
            if fresh:
                self.fit(True, animate=False)
            self.view.fly_to(QPointF(x - v.isl.x0 + 0.5, z - v.isl.z0 + 0.5), 8.0, 650)
        elif fresh:
            self.fit(True, animate=False)
        self.restore_map_view()

    def prepare_view(self, v):
        """Qt pixmaps for an IslandView (made in the GUI thread)."""
        if getattr(v, 'base_pm', None) is None:
            v.base_pm = QPixmap.fromImage(pil_to_qimage(v.base))
            v.objects_pm = QPixmap.fromImage(pil_to_qimage(v.objects))
            isl = v.isl
            v.tiles_with_data = {(((ci & 63) * 32 - isl.x0) // 32, ((ci >> 6) * 32 - isl.z0) // 32) for ci, _ in isl.alloc}
            v._contour = None
            v.objects_seen = isl.objects_version

            def contour_pm():
                if v._contour is None:
                    from PIL import Image, ImageChops
                    hts = Image.frombytes('L', (isl.width, isl.height), bytes(isl.floor_h))
                    q = hts.point(lambda h: 255 if h == 255 else h // 4 * 4)
                    e1 = ImageChops.difference(q, ImageChops.offset(q, 1, 0))
                    e2 = ImageChops.difference(q, ImageChops.offset(q, 0, 1))
                    m = ImageChops.lighter(e1, e2).point(lambda d: 160 if 0 < d < 60 else 0)
                    img = Image.new('RGBA', m.size, (20, 26, 30, 0))
                    img.putalpha(m)
                    v._contour = QPixmap.fromImage(pil_to_qimage(img))
                return v._contour
            v.contour_pm = contour_pm
            v._heights = None

            def heights_pm():
                if v._heights is None:
                    from gui.maprender import render_heights
                    v._heights = QPixmap.fromImage(pil_to_qimage(render_heights(isl, 0, 0, isl.width, isl.height)))
                return v._heights
            v.heights_pm = heights_pm

    def update_zones(self):
        while self.zone_box.count():
            w = self.zone_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        v = self.view_data
        if not v:
            self.zone_note.setText('')
            return
        for z in v.isl.zones:
            b = QPushButton(f'  {z.title}')
            b.setProperty('nav', 'true')
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(T.glyph_icon(T.G.get(ZONE_GLYPH.get(z.kind, 'pin'), ''), 'muted', 16))
            b.setToolTip(f'{len(z.chunks)} chunks · {z.objects:,} objects — click to go there')
            b.clicked.connect(lambda _=False, z=z: self.fly_zone(z))
            self.zone_box.addWidget(b)
        n = len(v.isl.zones)
        self.zone_note.setText('Besides the island itself, the file holds separate areas far out in empty space. '
                               'Click one to go there.' if n > 1 else 'This file holds only the island.')

    def preferences(self):
        state = super().preferences()
        if not getattr(self, '_preferences_restored', False):
            return state
        state.update(tool=self.tool, options=dict(self.opts), area=self.area, stack_height=self.stack_height,
                     paint_block=self.paint_block, place_var=self.place_var, place_dir=self.place_dir,
                     stamp_rot=self.stamp_rot, recipe=self.recipe['dex'] if self.recipe else None,
                     height_mode=self.height_mode, flatten_y=self.flatten_y, show_heights=self.show_heights,
                     lift_objects=self.lift_objects_check.isChecked(),
                     cut_enabled=self.cut_row.toggle.isChecked(), cut_y=self.cut_slider.value(),
                     searches={name: getattr(self, name).text() for name in
                               ('place_search', 'block_search', 'recipe_search')},
                     brushes=[dict(shape=controls[0].currentData(), width=controls[1].value(), depth=controls[2].value())
                              for height, controls in sorted(self.brush_controls.items())])
        pending = getattr(self, '_pending_map_view', None)
        if pending:
            state['view'] = pending
        elif self.view_data:
            center = self.view.mapToScene(self.view.viewport().rect().center())
            state['view'] = dict(folder=self.app.save.folder, area=self.area, zoom=self.view.zoom(),
                                 center=[center.x(), center.y()])
        return state

    def restore_preferences(self):
        if getattr(self, '_preferences_restored', False):
            return
        state = self.app.settings.get('tools', {}).get(self.nav, {})
        super().restore_preferences()
        if not isinstance(state, dict):
            return
        for height, brush in enumerate(state.get('brushes', [])[:2] if isinstance(state.get('brushes'), list) else []):
            if not isinstance(brush, dict):
                continue
            shape, width, depth, _ = self.brush_controls[bool(height)]
            index = shape.findData(brush.get('shape'))
            if index >= 0:
                shape.setCurrentIndex(index)
            if type(brush.get('width')) is int:
                width.setValue(brush['width'])
            if type(brush.get('depth')) is int:
                depth.setValue(brush['depth'])
        options = state.get('options', {})
        if isinstance(options, dict):
            for key, row in self.layer_rows.items():
                if isinstance(options.get(key), bool):
                    row.toggle.setChecked(options[key])
        for key in ('paint_block', 'place_var', 'place_dir', 'stamp_rot'):
            if type(state.get(key)) is int:
                setattr(self, key, state[key])
        self.place_dir %= 4
        self.stamp_rot %= 4
        if type(state.get('flatten_y')) is int:
            self.flat_spin.setValue(state['flatten_y'])
        if state.get('height_mode') in dict((key, name) for key, name, _ in HEIGHT_MODES):
            self.set_height_mode(state['height_mode'])
        if isinstance(state.get('lift_objects'), bool):
            self.lift_objects_check.setChecked(state['lift_objects'])
        if isinstance(state.get('show_heights'), bool):
            self.heights_check.setChecked(state['show_heights'])
        searches = state.get('searches', {})
        if isinstance(searches, dict):
            for name in ('place_search', 'block_search', 'recipe_search'):
                if isinstance(searches.get(name), str):
                    getattr(self, name).setText(searches[name])
        self.stack_height = state.get('stack_height') if type(state.get('stack_height')) is int else None
        self.load_recipes()
        self.recipe = self.recipes.get(str(state.get('recipe')))
        tool = state.get('tool')
        if isinstance(tool, str) and tool in {key for key, _, _ in TOOLS}:
            self.set_tool(tool)
        self._pending_map_view = state.get('view') if isinstance(state.get('view'), dict) else None
        self._pending_map_cut = (state.get('cut_enabled') is True,
                                 state.get('cut_y') if type(state.get('cut_y')) is int else 60)
        enabled, height = self._pending_map_cut
        self.cut_slider.blockSignals(True)
        self.cut_slider.setValue(height)
        self.cut_slider.blockSignals(False)
        self.cut_row.toggle.set_quiet(enabled)
        self.cut_slider.setEnabled(enabled)
        self.cut_lbl.setText(f'Y {self.cut_slider.value()}' if enabled else 'All')
        area = state.get('area')
        if self.app.save and type(area) is int and area in self.app.save.stage_files() and area != self.area:
            self.choose(area)
        elif self.view_data:
            self.restore_map_view()

    def restore_map_view(self):
        pending_cut = getattr(self, '_pending_map_cut', None)
        if pending_cut is not None:
            self._pending_map_cut = None
            enabled, height = pending_cut
            self.cut_slider.blockSignals(True)
            self.cut_slider.setValue(height)
            self.cut_slider.blockSignals(False)
            self.cut_row.toggle.set_quiet(enabled)
            self.apply_cut()
        view = getattr(self, '_pending_map_view', None)
        if not view:
            return
        self._pending_map_view = None
        if view.get('folder') != self.app.save.folder or view.get('area') != self.area:
            return
        center, zoom = view.get('center'), view.get('zoom')
        if (isinstance(center, list) and len(center) == 2 and
                all(type(value) in (int, float) and math.isfinite(value) for value in center) and
                type(zoom) in (int, float) and math.isfinite(zoom) and zoom > 0):
            self.view.set_zoom(zoom)
            self.view.centerOn(*center)

    def show_all_heights(self):
        self.cut_timer.stop()
        self.cut_row.toggle.set_quiet(False)
        self.apply_cut()

    def show_height(self, height):
        self.cut_timer.stop()
        self.cut_slider.blockSignals(True)
        self.cut_slider.setValue(min(height, 126))
        self.cut_slider.blockSignals(False)
        self.cut_lbl.setText(f'Y {self.cut_slider.value()}')
        self.cut_row.toggle.set_quiet(height < 127)
        self.apply_cut()

    def step_layer(self, direction):
        island = self.isl()
        if not island:
            return
        current = island.cut
        levels = [y for y in self.layer_levels if (y - current) * direction > 0]
        height = (min(levels) if direction > 0 else max(levels)) if levels else current + direction
        self.show_height(max(1, min(127, height)))

    def update_layer_inspector(self):
        self.layer_tree.clear()
        self.layer_levels = []
        self.layer_entries = []
        self.stack_button.hide()
        island = self.isl()
        if not island or self.layer_cell is None:
            self.layer_tree.hide()
            self.layer_summary.setText('Click a map cell with Select to inspect its vertical contents.')
            return
        wx, wz = self.layer_cell
        rows = column_layers(island, wx, wz)
        self.layer_entries = rows
        self.position_stack_button()
        objects = sum(handle is not None and handle >= 0 for _, _, _, handle in rows)
        discoveries = sum(handle is not None and handle < 0 for _, _, _, handle in rows)
        terrain = len(rows) - objects - discoveries
        summary = f'{objects} objects · {terrain} terrain layers'
        if discoveries:
            summary += f' · {discoveries} glowing ' + ('spot' if discoveries == 1 else 'spots')
        self.layer_summary.setText(f'X {wx} · Z {wz}\n{summary}')
        group = None
        last_height = None
        for top, bottom, name, handle in rows:
            if top != last_height:
                hidden = ' · above view' if top > island.cut else ''
                group = QTreeWidgetItem(self.layer_tree, [f'Y {top}{hidden}'])
                group.setData(0, Qt.UserRole, (top, None))
                self.layer_levels.append(top)
                last_height = top
            span = f'Y {bottom}' if bottom == top else f'Y {bottom}–{top}'
            status = ' · hidden' if bottom > island.cut else ' · partly visible' if top > island.cut else ''
            item = QTreeWidgetItem(group, [f'{name} · {span}{status}'])
            item.setData(0, Qt.UserRole, (top, handle))
            item.setToolTip(0, 'Click to reveal this level and select the object, when present.')
            item.setIcon(0, self.layer_icon((top, bottom, name, handle)))
            if group.childCount() == 1:
                group.setIcon(0, item.icon(0))
        self.layer_tree.expandAll()
        self.layer_tree.setVisible(bool(rows))
        if not rows:
            self.layer_summary.setText(f'X {wx} · Z {wz}\nNo terrain or placed objects at this cell.')

    def layer_icon(self, row, size=24):
        island = self.isl()
        top, bottom, name, handle = row
        if handle is not None and handle < 0:
            return T.glyph_icon(T.G['star'], 'gold', size)
        if handle is not None:
            obj = island.by_handle.get(handle)
            return QIcon(self.app.assets.item(obj.item, size)) if obj and obj.item else T.glyph_icon(T.G['grid'], 'muted', size)
        block = island.get_cell(self.layer_cell[0], bottom, self.layer_cell[1]) & pi.ID_MASK
        item_id = pi.block_item(block)
        if item_id:
            return QIcon(self.app.assets.item(item_id, size))
        from gui.maprender import look
        texture = look().texture(block, size)
        if texture is not None:
            thumbnail = QPixmap.fromImage(pil_to_qimage(texture.convert('RGBA')))
        else:
            thumbnail = QPixmap(size, size)
            thumbnail.fill(QColor(*look().color(block)))
        return QIcon(thumbnail)

    def position_stack_button(self):
        island = self.isl()
        entries = getattr(self, 'layer_entries', [])
        if not island or self.layer_cell is None or self.tool != 'select' or len(entries) < 2:
            self.stack_button.hide()
            return
        wx, wz = self.layer_cell
        point = self.view.mapFromScene(QPointF(wx - island.x0 + 1, wz - island.z0))
        if not self.view.viewport().rect().contains(point):
            self.stack_button.hide()
            return
        self.stack_button.setText(str(len(entries)))
        self.stack_button.adjustSize()
        self.stack_button.move(point.x() + 3, max(0, point.y() - self.stack_button.height()))
        self.stack_button.show()
        self.stack_button.raise_()

    def open_tile_contents(self):
        island = self.isl()
        if not island or self.layer_cell is None:
            return
        wx, wz = self.layer_cell
        entries = column_layers(island, wx, wz)
        dialog = QDialog(self.app)
        dialog.setWindowTitle(f'Tile contents · X {wx} · Z {wz}')
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(W.label('Select an object to work with it on the map, or terrain to reveal its height.', 'muted', wrap=True))
        levels = QComboBox()
        levels.addItem('All heights', None)
        for height in sorted({row[0] for row in entries}, reverse=True):
            levels.addItem(f'Y {height}', height)
        layout.addWidget(levels)
        contents = QListWidget()
        contents.setViewMode(QListView.IconMode)
        contents.setResizeMode(QListView.Adjust)
        contents.setMovement(QListView.Static)
        contents.setSelectionMode(QAbstractItemView.SingleSelection)
        contents.setIconSize(QSize(48, 48))
        contents.setGridSize(QSize(164, 116))
        contents.setWordWrap(True)
        layout.addWidget(contents, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        select = buttons.addButton('Select on map', QDialogButtonBox.AcceptRole)
        select.setEnabled(False)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def fill():
            contents.clear()
            select.setEnabled(False)
            for row in entries:
                top, bottom, name, handle = row
                if levels.currentData() is not None and top != levels.currentData():
                    continue
                span = f'Y {bottom}' if bottom == top else f'Y {bottom}–{top}'
                item = QListWidgetItem(self.layer_icon(row, 48), f'{name}\n{span}')
                item.setData(Qt.UserRole, (top, handle))
                item.setToolTip(f'{name} · {span}')
                contents.addItem(item)

        def activate():
            item = contents.currentItem()
            if item is None:
                return
            height, handle = item.data(Qt.UserRole)
            self.select_layer(height, handle)
            dialog.accept()

        def change_height():
            self.stack_height = levels.currentData()
            fill()

        levels.setCurrentIndex(max(0, levels.findData(self.stack_height)))
        levels.currentIndexChanged.connect(change_height)
        contents.itemSelectionChanged.connect(lambda: select.setEnabled(contents.currentItem() is not None))
        contents.itemDoubleClicked.connect(lambda _: activate())
        select.clicked.connect(activate)
        fill()
        dialog.exec()

    def choose_layer(self, item, _column=0):
        if not self.isl():
            return
        value = item.data(0, Qt.UserRole)
        if not value:
            return
        self.select_layer(*value)

    def select_layer(self, height, handle):
        self.show_height(height)
        self.selection = [handle] if handle is not None and handle >= 0 else []
        self.sel_habitat = None
        self.update_inspector()
        self.overlay.update()
        self.habitats_item.update()

    def start_pick_cut(self):
        self.pick_cut = True
        self.hint.setText('Click a roof or ceiling: everything from that height up will be hidden  ·  Esc to cancel')
        self.hint.adjustSize()
        self.place_floating()
        self.view.viewport().setCursor(Qt.CrossCursor)

    def apply_cut(self):
        """Re-read the surface below the chosen height and redraw everything."""
        v = self.view_data
        on = self.cut_row.toggle.isChecked()
        self.cut_slider.setEnabled(on)
        self.cut_lbl.setText(f'Y {self.cut_slider.value()}' if on else 'All')
        if not v:
            return
        y = self.cut_slider.value() if on else 127
        if v.isl.cut == y:
            return
        from gui.maprender import render_base, render_objects
        v.isl.set_cut(y)
        v.base = render_base(v.isl)
        v.objects = render_objects(v.isl)
        v.base_pm = QPixmap.fromImage(pil_to_qimage(v.base))
        v.objects_pm = QPixmap.fromImage(pil_to_qimage(v.objects))
        v._contour = None
        v._heights = None
        self.terrain.drop_tiles()
        for it in (self.terrain, self.objects_item, self.overlay):
            it.update()
        self.minimap.update()
        self.update_layer_inspector()

    def fly_zone(self, z):
        v = self.view_data
        if not v:
            return
        isl = v.isl
        x0, z0, x1, z1 = z.box
        vw, vh = max(50, self.view.viewport().width()), max(50, self.view.viewport().height())
        zoom = max(MIN_ZOOM, min(vw / (x1 - x0 + 40), vh / (z1 - z0 + 40)))
        self.view.fly_to(QPointF((x0 + x1) / 2 - isl.x0, (z0 + z1) / 2 - isl.z0), zoom, 650)
        self.zone_note.setText(f'{z.title}: {z.note}' + (
            '\n\nTurn on "Look inside" under Layers (around Y 60) to see the rooms instead of the roof.'
            if z.kind == 'center' else ''))

    def update_markers(self):
        for mk in self.markers:
            self.scene.removeItem(mk)
        self.markers = []
        v, c = self.view_data, self.c
        if not v or not c or not self.opts['homes']:
            return
        for i, name, x, y, z in px.homes_on(c, self.area):
            mk = HomeMarker(self, i, name, QPointF(x - v.isl.x0 + 0.5, z - v.isl.z0 + 0.5))
            self.scene.addItem(mk)
            self.markers.append(mk)

    def update_side(self):
        v, c = self.view_data, self.c
        self.res_list.clear()
        if not v or not c:
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
        isl = v.isl
        x0, z0, x1, z1 = isl.main_box()
        main_objs = isl.zones[0].objects
        self.stats.setText(f'{isl.name}\n{x1 - x0 + 1} × {z1 - z0 + 1} blocks · {isl.chunks} chunks in the file\n'
                           f'{main_objs:,} placed objects · {len(isl.habitats)} habitat{"s" if len(isl.habitats) != 1 else ""}'
                           f' · {len(homes)} resident home{"s" if len(homes) != 1 else ""}')
        while self.top_box.count():
            w = self.top_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.top_box.addWidget(W.label('MOST PLACED', 'caps'), 0, 0, 1, 3)
        for n, (item, cnt) in enumerate(v.top, 1):
            ic = QLabel()
            ic.setPixmap(self.app.assets.item(item, 22))
            self.top_box.addWidget(ic, n, 0)
            nm = W.label(ps.item_name(item))
            nm.setToolTip(f'Item ID {item}')
            self.top_box.addWidget(nm, n, 1)
            self.top_box.addWidget(W.label(f'{cnt:,}', 'muted'), n, 2, Qt.AlignRight)
        self.top_box.setColumnStretch(1, 1)

    # ---------- inspector ----------
    def update_inspector(self):
        v = self.view_data
        isl = v.isl if v else None
        sel = [isl.by_handle[h] for h in self.selection if isl and h in isl.by_handle] if isl else []
        self.selection = [o.handle for o in sel]
        for b in self.sel_btns.values():
            b.setVisible(bool(sel))
        self.sel_hint.setVisible(bool(sel))
        if sel:
            if len(sel) == 1:
                o = sel[0]
                self.sel_icon.setPixmap(self.app.assets.item(o.item, 44) if o.item else T.glyph_pixmap(T.G['grid'], 26, T.P['muted']))
                self.sel_name.setText(o.name)
                self.sel_sub.setText((f'Item ID {o.item}  ·  ' if o.item else '') + f'{o.w} × {o.dp} blocks, {o.h} high')
                col = isl.column(o.x, o.z)
                above = o.y - (col[2] + 1) if col else 0
                hab = next((h for h in isl.habitats if h.min[0] <= o.x <= h.max[0] and h.min[2] <= o.z <= h.max[2]), None)
                self.sel_info.setText(f'X {o.x}   Y {o.y}   Z {o.z}   ·   turned {ROT_NAMES[o.dir]}'
                                      + (f'\n{above} block{"s" if above != 1 else ""} above the ground' if above > 0 else '')
                                      + (f'\nPart of the habitat "{hab.name}"' if hab else ''))
            else:
                cnt = Counter(o.name for o in sel)
                self.sel_icon.setPixmap(T.glyph_pixmap(T.G['grid'], 26, T.P['accent']))
                self.sel_name.setText(f'{len(sel)} objects')
                self.sel_sub.setText(', '.join(f'{n} × {k}' for k, n in cnt.most_common(3)) + ('…' if len(cnt) > 3 else ''))
                self.sel_info.setText('Moves, turns and deletes apply to all of them.')
            self.sel_btns['rotate'].setText('Rotate' if len(sel) == 1 else 'Rotate each')
            return
        self.sel_icon.setPixmap(QPixmap())
        h = self.sel_habitat
        if h and isl and h in isl.habitats:
            self.sel_icon.setPixmap(T.glyph_pixmap(T.G['home'], 26, T.P['gold']))
            self.sel_name.setText(h.name)
            w, d = h.max[0] - h.min[0] + 1, h.max[2] - h.min[2] + 1
            self.sel_sub.setText(f'Habitat  ·  {w} × {d} blocks')
            who = [name for i, name, x, y, z in (px.homes_on(self.c, self.area) if self.c else [])
                   if h.min[0] <= x <= h.max[0] and h.min[2] <= z <= h.max[2]]
            self.sel_info.setText((f'Home of {", ".join(who)}.\n' if who else '') +
                                  'Habitats form from the objects inside them. Move or remove those objects '
                                  'to change it; the game checks habitats again when it loads.')
            return
        self.sel_habitat = None
        self.sel_name.setText('Nothing selected')
        if self.tool == 'pick':
            self.sel_sub.setText('Click an object to place more like it, or the ground to paint with that block.')
        else:
            self.sel_sub.setText('Click an object or habitat, or Shift-drag a box around several objects.')
        self.sel_info.setText('')

    # ---------- interaction ----------
    def world(self, sp):
        v = self.view_data
        return math.floor(sp.x()) + v.isl.x0, math.floor(sp.y()) + v.isl.z0

    def press(self, sp, e):
        v = self.view_data
        if not v:
            return False
        isl = v.isl
        wx, wz = self.world(sp)
        btn = e.button()
        mods = e.modifiers()
        if self.pick_cut and btn == Qt.LeftButton:
            self.layer_cell = (wx, wz)
            self.pick_cut = False
            top = isl.top_at(wx, wz)
            self.update_hint()
            self.view.viewport().setCursor(self.cursor_for_tool())
            if top is None or top < 3:
                self.app.toast('Nothing to look under there.', 'info')
                return True
            self.cut_slider.blockSignals(True)
            self.cut_slider.setValue(top - 1)
            self.cut_lbl.setText(f'Y {top - 1}')
            self.cut_slider.blockSignals(False)
            self.cut_row.toggle.set_quiet(True)
            self.apply_cut()
            self.app.toast(f'Showing everything below Y {top}', 'info')
            return True
        if self.tool == 'select':
            if btn != Qt.LeftButton:
                return False
            discovery = None
            if self.opts['discoveries'] and not mods & Qt.ShiftModifier:
                candidates = [(x, z) for _, x, y, z, _ in isl.glowing_blocks()
                              if ((sp.x() - (x - isl.x0 + 0.5)) ** 2 +
                                  (sp.y() - (z - isl.z0 + 0.5)) ** 2) * self.view.zoom() ** 2 <= 121]
                discovery = min(candidates, key=lambda pos: (pos[0] - wx) ** 2 + (pos[1] - wz) ** 2) if candidates else None
            if discovery:
                wx, wz = discovery
            self.layer_cell = (wx, wz)
            self.update_layer_inspector()
            self.overlay.update()
            if discovery:
                self.selection = []
                self.sel_habitat = None
                self.update_inspector()
                return True
            if mods & Qt.ShiftModifier:
                self.drag = dict(kind='box', a=sp, b=sp, add=bool(mods & Qt.ControlModifier))
                return True
            o = isl.object_at(wx, wz) if self.opts['objects'] else None
            if o:
                if mods & Qt.ControlModifier:
                    if o.handle in self.selection:
                        self.selection.remove(o.handle)
                    else:
                        self.selection.append(o.handle)
                elif o.handle not in self.selection:
                    self.selection = [o.handle]
                self.sel_habitat = None
                if o.handle in self.selection:
                    self.drag = dict(kind='move', start=(wx, wz), dx=0, dz=0, grab=o.handle, bad=None, moved=False)
                self.update_inspector()
                self.overlay.update()
                self.habitats_item.update()
                return True
            # empty ground: habitat, or clear the selection and pan
            hab = None
            if self.opts['habitats']:
                hab = next((h for h in isl.habitats if h.min[0] <= wx <= h.max[0] and h.min[2] <= wz <= h.max[2]), None)
            changed = bool(self.selection) or hab is not self.sel_habitat
            if not mods & Qt.ControlModifier:
                self.selection = []
            self.sel_habitat = hab
            if changed:
                self.update_inspector()
                self.overlay.update()
                self.habitats_item.update()
            return False
        if self.tool == 'pick':
            if btn != Qt.LeftButton:
                return False
            o = isl.object_at(wx, wz)
            if o:
                self.place_var, self.place_dir = o.var, o.dir
                self._place_filled = False
                self.set_tool('place')
                self.place_info.setText(f'{o.name}  ·  turned {ROT_NAMES[o.dir]}')
                return True
            col = isl.column(wx, wz)
            if col and pi.block_kind(col[3]) in (pi.K_TERRAIN, pi.K_BUILD):
                self.paint_block = col[3]
                self._blocks_filled = False
                self.set_tool('paint')
                return True
            return True
        if self.tool == 'habitat':
            if btn == Qt.RightButton:
                self.set_tool('select')
                return True
            if btn == Qt.LeftButton:
                if not self.recipe:
                    self.app.toast('Pick a habitat from the list first.', 'info')
                else:
                    self.stamp_here(wx, wz)
                    self.stamp_ghost = self.stamp_parts(wx, wz)
                    self.overlay.update()
                return True
            return False
        if self.tool == 'place':
            if btn == Qt.RightButton:
                self.set_tool('select')
                return True
            if btn != Qt.LeftButton or self.place_var is None:
                return btn == Qt.LeftButton
            self.drag = dict(kind='place', done=set(), count=0)
            self.place_here(wx, wz)
            return True
        if self.tool in ('paint', 'height'):
            if btn not in (Qt.LeftButton, Qt.RightButton):
                return False
            if self.tool == 'paint' and btn != Qt.LeftButton:
                return False
            mode = self.height_mode
            if self.tool == 'height' and btn == Qt.RightButton:
                if mode == 'flatten':
                    col = isl.column(wx, wz)
                    if col:
                        self.flat_spin.setValue(col[2])
                        self.app.toast(f'Flatten height set to Y {col[2]}', 'info')
                    return True
                mode = 'lower' if mode == 'raise' else 'raise'
            if self.tool == 'height' and btn == Qt.LeftButton and mods & Qt.ShiftModifier:
                self.drag = dict(kind='height_box',
                                 mode=mode, a=sp, b=sp)
                self.overlay.update()
                return True
            self.drag = dict(kind='brush', mode=mode, done=set(), count=0)
            self.brush_apply(wx, wz)
            return True
        return False

    def move(self, sp, e):
        v = self.view_data
        if not v:
            return
        isl = v.isl
        wx, wz = self.world(sp)
        self.hover_info(wx, wz)
        d = self.drag
        if d and d['kind'] in ('height_box'):
            d['b'] = sp
            ax, az = self.world(d['a'])
            bx, bz = self.world(sp)
            self.hint.setText(f'{abs(bx-ax)+1} × {abs(bz-az)+1} cells  ·  Release to {d["mode"]}  ·  Esc to cancel')
            self.hint.adjustSize()
            self.overlay.update()
            return
        if self.tool == 'habitat':
            self.brush_at = (wx, wz)
            if self.recipe:
                self.stamp_ghost = self.stamp_parts(wx, wz)
                self.overlay.update()
            return
        if self.tool in ('paint', 'height'):
            self.brush_at = (wx, wz)
            if d and d['kind'] == 'brush':
                self.brush_apply(wx, wz)
            self.overlay.update()
            return
        if self.tool == 'place':
            if self.place_var is not None:
                y = isl.ground_y(self.place_var, wx, wz, self.place_dir)
                ok = y is not None and isl.blocked(self.place_var, wx, y, wz, self.place_dir) is None
                self.ghost = (self.place_var, wx, y or 0, wz, self.place_dir, ok)
                if d and d['kind'] == 'place':
                    self.place_here(wx, wz)
                self.overlay.update()
            return
        if d and d['kind'] == 'box':
            d['b'] = sp
            self.overlay.update()
            return
        if d and d['kind'] == 'move':
            dx, dz = wx - d['start'][0], wz - d['start'][1]
            if (dx, dz) != (d['dx'], d['dz']):
                d['dx'], d['dz'], d['moved'] = dx, dz, True
                d['bad'] = self.check_move(dx, dz, follow=True)
                self.overlay.update()
            return
        if self.tool in ('select', 'pick'):
            o = isl.object_at(wx, wz) if self.opts['objects'] else None
            h = o.handle if o else None
            if h != self.hover_obj:
                self.hover_obj = h
                self.overlay.update()

    def release(self, sp, e):
        d = self.drag
        self.drag = None
        v = self.view_data
        if not d or not v:
            return
        isl = v.isl
        if d['kind'] in ('height_box'):
            ax, az = self.world(d['a'])
            bx, bz = self.world(sp)
            cells = [(x, z)
                     for x in range(max(isl.x0, min(ax, bx)), min(isl.x0 + isl.width - 1, max(ax, bx)) + 1)
                     for z in range(max(isl.z0, min(az, bz)), min(isl.z0 + isl.height - 1, max(az, bz)) + 1)]
            lift = self.lift_objects_check.isChecked()
            try:
                if d['mode'] == 'raise':
                    n = isl.raise_ground(cells, lift_objects=lift)
                elif d['mode'] == 'lower':
                    n = isl.lower_ground(cells)
                else:
                    n = isl.level_ground(cells, self.flatten_y, lift_objects=lift)
                if n:
                    self.commit(f'{d["mode"].capitalize()} ground in rectangle ({len(cells)} cells, {n} blocks)')
                else:
                    self.app.toast('No ground changed in this rectangle.', 'info')
            except pi.EditError as ex:
                self.fail(ex)
            self.update_hint()
            self.overlay.update()
        elif d['kind'] == 'box':
            a, b = d['a'], d['b']
            x0, x1 = sorted((a.x(), b.x()))
            z0, z1 = sorted((a.y(), b.y()))
            hits = [o.handle for o in isl.objects_in(x0 + isl.x0, z0 + isl.z0, x1 + isl.x0, z1 + isl.z0) if o.y <= isl.cut]
            self.selection = list(dict.fromkeys((self.selection if d['add'] else []) + hits))
            self.sel_habitat = None
            self.update_inspector()
            self.overlay.update()
        elif d['kind'] == 'move':
            if d['moved'] and (d['dx'] or d['dz']):
                if d['bad']:
                    self.app.toast(f'Not moved: {d["bad"]}', 'err')
                else:
                    self.do_move(d['dx'], d['dz'], follow=True, label='Moved')
            self.overlay.update()
        elif d['kind'] == 'place':
            if d['count']:
                name = ps.item_name(pi.part_size(self.place_var)[0])
                self.commit(f'Placed {d["count"]} × {name}' if d['count'] > 1 else f'Placed {name}')
        elif d['kind'] == 'brush':
            if d['count']:
                bn = pi.block_name(self.paint_block)
                n = d['count']
                label = f'Painted {n} blocks of {bn}' if self.tool == 'paint' else {
                    'raise': f'Raised the ground ({n} blocks)', 'lower': f'Lowered the ground ({n} blocks)',
                    'flatten': f'Flattened the ground to Y {self.flatten_y} ({n} blocks)'}[d['mode']]
                self.commit(label)

    def key(self, e):
        k = e.key()
        mods = e.modifiers()
        if not mods & (Qt.ControlModifier | Qt.AltModifier):
            for key, _, sc in TOOLS:
                if k == ord(sc) and not (self.tool == 'select' and self.selection and sc in 'R'):
                    self.set_tool(key)
                    return True
        if k == Qt.Key_Escape and self.pick_cut:
            self.pick_cut = False
            self.update_hint()
            return True
        if self.tool == 'habitat' and k == Qt.Key_R:
            self.stamp_rot = (self.stamp_rot + 1) % 4
            if self.brush_at or self.stamp_ghost:
                c = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
                wx, wz = self.world(c)
                self.stamp_ghost = self.stamp_parts(wx, wz)
                self.overlay.update()
            return True
        if k == Qt.Key_Escape:
            if self.tool != 'select':
                self.set_tool('select')
            else:
                self.selection, self.sel_habitat = [], None
                self.update_inspector()
                self.overlay.update()
                self.habitats_item and self.habitats_item.update()
            return True
        if k in (Qt.Key_BracketLeft, Qt.Key_BracketRight):
            step = 1 if k == Qt.Key_BracketRight else -1
            if self.tool == 'height':
                self.hbrush_slider.setValue(self.height_brush + step)
            else:
                self.brush_slider.setValue(self.brush + step)
            return True
        if self.tool == 'place' and k == Qt.Key_R:
            self.place_dir = (self.place_dir + 1) % 4
            if self.ghost:
                var, x, y, z, _, _ = self.ghost
                isl = self.view_data.isl
                y = isl.ground_y(var, x, z, self.place_dir) or 0
                self.ghost = (var, x, y, z, self.place_dir, isl.blocked(var, x, y, z, self.place_dir) is None)
                self.overlay.update()
            if self.place_var is not None:
                self.place_info.setText(f'{ps.item_name(pi.part_size(self.place_var)[0])}  ·  turned {ROT_NAMES[self.place_dir]}')
            return True
        if self.tool == 'select' and self.selection:
            if k == Qt.Key_Delete or k == Qt.Key_Backspace:
                self.sel_action('delete')
            elif k == Qt.Key_R:
                self.sel_action('rotate')
            elif k == Qt.Key_G:
                self.sel_action('ground')
            elif k == Qt.Key_D and mods & Qt.ControlModifier:
                self.sel_action('dup')
            elif k == Qt.Key_PageUp:
                self.sel_action('up')
            elif k == Qt.Key_PageDown:
                self.sel_action('down')
            elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                dx = {Qt.Key_Left: -1, Qt.Key_Right: 1}.get(k, 0)
                dz = {Qt.Key_Up: -1, Qt.Key_Down: 1}.get(k, 0)
                why = self.check_move(dx, dz)
                if why:
                    self.app.toast(f'Not moved: {why}', 'err')
                else:
                    self.do_move(dx, dz, label='Nudged')
            else:
                return False
            return True
        return False

    # ---------- edits ----------
    def isl(self):
        return self.view_data.isl if self.view_data else None

    def commit(self, label):
        isl = self.isl()
        if isl and isl.commit(label):
            self.app.save.islands[self.area] = isl
            self.app.save.note_commit(self.area)
            self.app.toast(label, 'info')
            self.after_edit()
            self.app.update_chrome()

    def fail(self, ex):
        isl = self.isl()
        if isl:
            isl.rollback()
        self.app.toast(str(ex), 'err')
        self.after_edit()

    def after_edit(self):
        """Redraw what the last edits changed."""
        v = self.view_data
        if not v:
            return
        isl = v.isl
        cols = isl.refresh() | getattr(isl, 'last_dirty', set())
        isl.last_dirty = set()
        if cols:
            self.redraw_columns(cols)
        if v.objects_seen != isl.objects_version:
            v.objects_seen = isl.objects_version
            from gui.maprender import render_objects
            v.objects = render_objects(isl)
            v.objects_pm = QPixmap.fromImage(pil_to_qimage(v.objects))
            v.refresh_top()
            self.objects_item.update()
            self.update_side()
        self.selection = [h for h in self.selection if h in isl.by_handle]
        self.update_layer_inspector()
        self.update_inspector()
        self.terrain.update()
        self.overlay.update()
        self.minimap.update()

    def redraw_columns(self, cols):
        v = self.view_data
        isl = v.isl
        xs = [x - isl.x0 for x, _ in cols]
        zs = [z - isl.z0 for _, z in cols]
        x0, x1 = max(0, min(xs) - 2), min(isl.width, max(xs) + 3)
        z0, z1 = max(0, min(zs) - 2), min(isl.height, max(zs) + 3)
        from gui.maprender import render_region
        img = pil_to_qimage(render_region(isl, x0, z0, x1, z1))
        p = QPainter(v.base_pm)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(x0, z0, img)
        p.end()
        keys = {(tx, tz) for tx in range((x0 - 1) // 32, (x1 + 1) // 32 + 1) for tz in range((z0 - 1) // 32, (z1 + 1) // 32 + 1)}
        self.terrain.drop_tiles(keys)
        v._contour = None
        if getattr(v, '_heights', None) is not None:
            from gui.maprender import render_heights
            hp = QPainter(v._heights)
            hp.setCompositionMode(QPainter.CompositionMode_Source)
            hp.drawImage(x0, z0, pil_to_qimage(render_heights(isl, x0, z0, x1, z1)))
            hp.end()

    def brush_apply(self, wx, wz):
        d = self.drag
        isl = self.isl()
        cells = [c for c in self.brush_cells(wx, wz) if c not in d['done']]
        if not cells:
            return
        d['done'].update(cells)
        try:
            if self.tool == 'paint':
                n = isl.paint(cells, self.paint_block)
            elif d['mode'] == 'raise':
                n = isl.raise_ground(cells, None, lift_objects=self.lift_objects_check.isChecked())
            elif d['mode'] == 'lower':
                n = isl.lower_ground(cells)
            else:
                n = isl.level_ground(cells, self.flatten_y, None, lift_objects=self.lift_objects_check.isChecked())
        except pi.EditError as ex:
            self.drag = None
            return self.fail(ex)
        d['count'] += n
        if n:
            cols = isl.refresh()
            if cols:
                self.redraw_columns(cols)
                self.terrain.update()

    def place_here(self, wx, wz):
        d = self.drag
        isl = self.isl()
        if (wx, wz) in d['done']:
            return
        d['done'].add((wx, wz))
        var, dr = self.place_var, self.place_dir
        y = isl.ground_y(var, wx, wz, dr)
        if y is None or isl.blocked(var, wx, y, wz, dr):
            if d['count'] == 0 and len(d['done']) == 1:
                self.app.toast(f'Cannot place here: {isl.blocked(var, wx, y or 0, wz, dr) or "outside the island"}', 'err')
            return
        try:
            isl.add_object(var, wx, y, wz, dr)
        except pi.EditError as ex:
            return self.app.toast(str(ex), 'err')
        d['count'] += 1
        self.after_edit_light()

    def after_edit_light(self):
        """Cheap redraw during a stroke (objects image rebuilt at the end)."""
        v = self.view_data
        isl = v.isl
        cols = isl.refresh()
        if cols:
            self.redraw_columns(cols)
        from gui.maprender import render_objects
        v.objects = render_objects(isl)
        v.objects_pm = QPixmap.fromImage(pil_to_qimage(v.objects))
        v.objects_seen = isl.objects_version
        self.terrain.update()
        self.objects_item.update()

    def moves_for(self, dx, dz, follow=False, dy=0, rotate=False):
        isl = self.isl()
        objs = [isl.by_handle[h] for h in self.selection if h in isl.by_handle]
        lift = 0
        if follow and (dx or dz) and self.drag and self.drag.get('grab') in isl.by_handle:
            g = isl.by_handle[self.drag['grab']]
            a, b = isl.column(g.x, g.z), isl.column(g.x + dx, g.z + dz)
            if a and b:
                lift = b[2] - a[2]
        out = []
        for o in objs:
            x, z, d = o.x + dx, o.z + dz, o.dir
            if rotate:
                d = (o.dir + 1) % 4
                ox0, oz0, ox1, oz1 = o.box
                nx0, nz0, nx1, nz1 = pi.box_of(o.x, o.z, d, o.w, o.dp)
                x += round(((ox0 + ox1) - (nx0 + nx1)) / 2 - 0.01)
                z += round(((oz0 + oz1) - (nz0 + nz1)) / 2 - 0.01)
            out.append((o.handle, x, o.y + dy + lift, z, d))
        return out

    def check_move(self, dx, dz, follow=False, dy=0, rotate=False):
        isl = self.isl()
        moves = self.moves_for(dx, dz, follow, dy, rotate)
        for hnd, x, y, z, d in moves:
            o = isl.by_handle[hnd]
            why = isl.blocked(o.var, x, y, z, d, ignore=self.selection)
            if why:
                return why
        return None

    def do_move(self, dx, dz, follow=False, dy=0, rotate=False, label='Moved'):
        isl = self.isl()
        moves = self.moves_for(dx, dz, follow, dy, rotate)
        if not moves:
            return
        try:
            isl.move_objects(moves)
        except pi.EditError as ex:
            return self.fail(ex)
        what = isl.by_handle[moves[0][0]].name if len(moves) == 1 else f'{len(moves)} objects'
        self.commit(f'{label} {what}')

    def sel_action(self, key):
        isl = self.isl()
        if not isl or not self.selection:
            return
        objs = [isl.by_handle[h] for h in self.selection if h in isl.by_handle]
        what = objs[0].name if len(objs) == 1 else f'{len(objs)} objects'
        if key == 'delete':
            try:
                for o in sorted(objs, key=lambda o: -o.index):
                    isl.remove_object(o.handle)
            except pi.EditError as ex:
                return self.fail(ex)
            self.selection = []
            self.commit(f'Removed {what}')
        elif key == 'rotate':
            why = self.check_move(0, 0, rotate=True)
            if why:
                return self.app.toast(f'Cannot turn: {why}', 'err')
            self.do_move(0, 0, rotate=True, label='Turned')
        elif key in ('up', 'down'):
            dy = 1 if key == 'up' else -1
            why = self.check_move(0, 0, dy=dy)
            if why:
                return self.app.toast(f'Cannot move {key}: {why}', 'err')
            self.do_move(0, 0, dy=dy, label='Raised' if dy > 0 else 'Lowered')
        elif key == 'ground':
            moves = []
            for o in objs:
                y = isl.ground_y(o.var, o.x, o.z, o.dir)
                if y is not None and y != o.y:
                    moves.append((o.handle, o.x, y, o.z, o.dir))
            if not moves:
                return self.app.toast('Already on the ground.', 'info')
            for hnd, x, y, z, d in moves:
                why = isl.blocked(isl.by_handle[hnd].var, x, y, z, d, ignore=self.selection)
                if why:
                    return self.app.toast(f'Cannot set down: {why}', 'err')
            try:
                isl.move_objects(moves)
            except pi.EditError as ex:
                return self.fail(ex)
            self.commit(f'Set down {what}')
        elif key == 'dup':
            x0 = min(o.box[0] for o in objs)
            x1 = max(o.box[2] for o in objs)
            z0 = min(o.box[1] for o in objs)
            z1 = max(o.box[3] for o in objs)
            for dx, dz in ((x1 - x0 + 1, 0), (0, z1 - z0 + 1), (-(x1 - x0 + 1), 0), (0, -(z1 - z0 + 1)), (1, 1)):
                if all(isl.blocked(o.var, o.x + dx, o.y, o.z + dz, o.dir) is None for o in objs):
                    try:
                        new = isl.duplicate_objects([o.handle for o in objs], dx, dz)
                    except pi.EditError as ex:
                        return self.fail(ex)
                    self.selection = new
                    self.commit(f'Duplicated {what}')
                    return
            self.app.toast('No free space next to the selection for a copy.', 'err')

    def island_changed(self, area):
        """Undo / redo touched an island: redraw it if it is the one on screen."""
        v = self.view_data
        if v and area == self.area:
            self.after_edit()

    # ---------- hover / info ----------
    def hover_info(self, wx, wz):
        v = self.view_data
        isl = v.isl
        col = isl.column(wx, wz)
        if not col:
            z = isl.zone_at(wx, wz)
            self.i_pos.setText(f'{z.title}' if z else 'Outside the island')
            self.i_obj.setText('')
            return
        th, tid, fh, fid = col
        if th != fh:
            what = f'{pi.block_name(tid)} ({th - fh} deep) over {pi.block_name(fid)}'
        else:
            what = pi.block_name(fid)
        self.i_pos.setText(f'X {wx}   Y {fh}   Z {wz}   ·   {what}')
        o = isl.object_at(wx, wz) if self.opts['objects'] else None
        parts = []
        if o:
            parts.append(o.name + (f'  ·  ID {o.item}' if o.item else '') + f'  ·  {o.w}×{o.dp}')
        h = None
        if self.opts['habitats']:
            h = next((h for h in isl.habitats if h.min[0] <= wx <= h.max[0] and h.min[2] <= wz <= h.max[2]), None)
            if h:
                parts.append(f'habitat: {h.name}')
        if h is not self.hover_habitat:
            self.hover_habitat = h
            self.habitats_item.update()
        z = isl.zone_at(wx, wz)
        if z and z.kind != 'island':
            parts.append(z.title)
        self.i_obj.setText(('   ·   ' + '   ·   '.join(parts)) if parts else '')

    # ---------- layers / view ----------
    def set_opt(self, key, on):
        self.opts[key] = on
        if key == 'homes':
            self.update_markers()
        elif key == 'minimap':
            self.place_floating()
        elif key == 'areas':
            for z in self.zone_labels:
                z.setVisible(on)
        for it in (self.terrain, self.objects_item, self.habitats_item, self.grid_item, self.overlay):
            if it:
                it.update()
        self.minimap.update()

    def fit(self, island=True, animate=True):
        v = self.view_data
        if not v:
            return
        isl = v.isl
        if island:
            x0, z0, x1, z1 = isl.main_box()
            x0, z0, x1, z1 = x0 - isl.x0, z0 - isl.z0, x1 - isl.x0 + 1, z1 - isl.z0 + 1
        else:
            x0, z0, x1, z1 = -40, -60, isl.width + 40, isl.height + 30
        vw, vh = max(50, self.view.viewport().width()), max(50, self.view.viewport().height())
        z = max(MIN_ZOOM, min(vw / (x1 - x0 + 24), vh / (z1 - z0 + 24)))
        c = QPointF((x0 + x1) / 2, (z0 + z1) / 2)
        if animate:
            self.view.fly_to(c, z)
        else:
            self.view.resetTransform()
            self.view.scale(z, z)
            self.view.centerOn(c)
            self.zoom_changed(z)

    def fly_home(self, index):
        v, c = self.view_data, self.c
        if not v or not c:
            return
        vv = c.get_villager(index)
        if not vv['home_xyz']:
            return
        self.highlight = index
        x, y, z = vv['home_xyz']
        for mk in self.markers:
            mk.update()
        self.view.fly_to(QPointF(x - v.isl.x0 + 0.5, z - v.isl.z0 + 0.5), max(8.0, self.view.zoom()))

    def open_resident(self, index):
        self.app.show_page('Residents')
        self.app.pages['Residents'].select_resident(index)

    def zoom_changed(self, z):
        for lab in self.zone_labels:
            lab.update()
        self.i_zoom.setText(f'Zoom {z:.1f}×')
        self.scalebar.update()
        self.minimap.update()
        self.position_stack_button()
        for mk in self.markers:
            mk.update()

    def export(self):
        v = self.view_data
        if not v:
            return
        f, _ = QFileDialog.getSaveFileName(self, 'Export island map', f'pokopia_island_{self.area:02}.png', 'PNG image (*.png)')
        if not f:
            return
        isl = v.isl
        x0, z0, x1, z1 = isl.main_box()
        src = QRectF(x0 - isl.x0 - 8, z0 - isl.z0 - 8, x1 - x0 + 17, z1 - z0 + 17)
        S = 6
        img = QImage(int(src.width() * S), int(src.height() * S), QImage.Format_ARGB32)
        img.fill(T.c('mapbg'))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self.terrain.exporting = True
        sel, self.selection = self.selection, []
        try:
            self.scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
        finally:
            self.terrain.exporting = False
            self.selection = sel
        p.end()
        img.save(f)
        self.app.toast(f'Map exported: {f}')
