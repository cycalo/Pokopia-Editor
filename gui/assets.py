"""Pixmaps: item icons, resident portraits, move and emote icons, generated placeholders, the app icon."""
import ctypes, os, sys
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QIcon, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPixmap, QPen, QRadialGradient)

import pokopia_extras as px
import pokopia_items as pi
import pokopia_save as ps
from gui import theme as T

try:
    from PIL import Image
except ImportError:
    Image = None

HERE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # bundle dir in the exe
APP_ICON = os.path.join(HERE, 'data', 'app.ico')
APP_PNG = os.path.join(HERE, 'data', 'app.png')


def set_app_id():
    """Own taskbar identity, so Windows shows the app icon instead of Python's."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Pokopia.SaveEditor.2')
    except Exception:
        pass


def app_icon():
    ic = QIcon()
    for p in (APP_ICON, APP_PNG):
        if os.path.isfile(p):
            ic.addFile(p)
    return ic


def dpr():
    s = QGuiApplication.primaryScreen()
    return s.devicePixelRatio() if s else 1.0


def initials(name):
    words = [w for w in name.replace('’', "'").replace('(', ' ').split() if w[:1].isalnum()]
    if not words:
        return '?'
    if len(words) == 1:
        return words[0][:2].capitalize()
    return (words[0][0] + words[1][0]).upper()


class Assets:
    def __init__(self):
        self.icons = px.Icons()
        self._img = {}      # path -> cropped QImage
        self._pm = {}       # (kind, key, size, dpr) -> QPixmap

    # ---------- loading ----------
    def _image(self, path):
        if path in self._img:
            return self._img[path]
        img = None
        if path and Image is not None:
            try:
                im = Image.open(path).convert('RGBA')
                bb = im.getchannel('A').getbbox()
                if bb:
                    im = im.crop(bb)
                data = im.tobytes('raw', 'RGBA')
                img = QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()
            except Exception:
                img = None
        elif path:
            q = QImage(path)
            img = q if not q.isNull() else None
        self._img[path] = img
        return img

    def _fit(self, img, size, scale=1.0):
        r = dpr()
        S = round(size * r)
        pm = QPixmap(S, S)
        pm.fill(Qt.transparent)
        if img is not None:
            f = min(S * scale / img.width(), S * scale / img.height(), 3.0 * r)
            w, h = max(1, round(img.width() * f)), max(1, round(img.height() * f))
            sc = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p = QPainter(pm)
            p.drawImage((S - w) // 2, (S - h) // 2, sc)
            p.end()
        pm.setDevicePixelRatio(r)
        return pm

    def _cached(self, key, make):
        k = key + (dpr(), T.NAME)
        pm = self._pm.get(k)
        if pm is None:
            pm = self._pm[k] = make()
        return pm

    # ---------- public ----------
    def item(self, item_id, size):
        """Item icon, or a generated tile in the item's category colour."""
        if not item_id:
            return None
        path = self.icons.item_path(item_id, fallback=False)
        if path:
            return self._cached(('item', item_id, size), lambda: self._fit(self._image(path), size))
        return self._cached(('itemph', item_id, size), lambda: self.placeholder(item_id, size))

    def has_item_icon(self, item_id):
        return self.icons.has_item_icon(item_id)

    def villager(self, index, size, circle=False):
        path = self.icons.villager_path(index)

        def make():
            if path:
                pm = self._fit(self._image(path), size, 0.92 if circle else 1.0)
            else:
                pm = self.silhouette(ps.name_of(ps.VILLAGER_NAMES, index, 'Resident'), size)
            return self._circle(pm, size) if circle else pm
        return self._cached(('vil', index, size, circle), make)

    def skill(self, skill_id, size):
        path = self.icons.skill_path(skill_id)
        return self._cached(('skill', skill_id, size), lambda: self._fit(self._image(path), size) if path else
                            self.glyph_tile(T.G['play'], size, T.P['sky']))

    def reaction(self, reaction_id, size):
        path = self.icons.reaction_path(reaction_id)
        return self._cached(('react', reaction_id, size), lambda: self._fit(self._image(path), size) if path else
                            self.glyph_tile(T.G['emoji'], size, T.P['heart']))

    def app(self, size):
        return self._cached(('app', 0, size), lambda: self._fit(QImage(APP_PNG) if os.path.isfile(APP_PNG) else None, size))

    # ---------- generated ----------
    def placeholder(self, item_id, size):
        """Rounded tile: category colour, category emoji and the name's initials."""
        cat = pi.category(item_id)
        col = QColor(pi.CAT_COLOR.get(cat, '#9aa5b1'))
        r = dpr()
        S = round(size * r)
        pm = QPixmap(S, S)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        m = S * 0.08
        rect = QRectF(m, m, S - 2 * m, S - 2 * m)
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, col.lighter(125))
        g.setColorAt(1, col.darker(115))
        p.setPen(QPen(col.darker(135), max(1.0, S * 0.025)))
        p.setBrush(g)
        p.drawRoundedRect(rect, S * 0.22, S * 0.22)
        # soft shine
        shine = QPainterPath()
        shine.addRoundedRect(QRectF(rect.x() + S * 0.06, rect.y() + S * 0.05, rect.width() - S * 0.12, rect.height() * 0.38),
                             S * 0.16, S * 0.16)
        p.fillPath(shine, QColor(255, 255, 255, 40))
        f = QFont(T.EMOJI_FONT)
        name = ps.item_name(item_id)
        if size >= 30:
            f.setPixelSize(round(S * 0.36))
            p.setFont(f)
            p.drawText(QRectF(0, S * 0.12, S, S * 0.48), Qt.AlignCenter, pi.CAT_GLYPH.get(cat, '❔'))
            f2 = QFont(T.UI_FONT)
            f2.setPixelSize(round(S * 0.21))
            f2.setWeight(QFont.Bold)
            p.setFont(f2)
            p.setPen(QColor(255, 255, 255, 235))
            p.drawText(QRectF(0, S * 0.56, S, S * 0.30), Qt.AlignCenter, initials(name))
        else:
            f.setPixelSize(round(S * 0.5))
            p.setFont(f)
            p.drawText(QRectF(0, 0, S, S), Qt.AlignCenter, pi.CAT_GLYPH.get(cat, '❔'))
        p.end()
        pm.setDevicePixelRatio(r)
        return pm

    def silhouette(self, name, size):
        r = dpr()
        S = round(size * r)
        pm = QPixmap(S, S)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        col = T.c('faint')
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QRectF(S * 0.34, S * 0.14, S * 0.32, S * 0.32))
        p.drawRoundedRect(QRectF(S * 0.22, S * 0.5, S * 0.56, S * 0.4), S * 0.2, S * 0.2)
        f = QFont(T.UI_FONT)
        f.setPixelSize(max(8, round(S * 0.18)))
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(T.c('card'))
        p.drawText(QRectF(0, S * 0.5, S, S * 0.4), Qt.AlignCenter, initials(name))
        p.end()
        pm.setDevicePixelRatio(r)
        return pm

    def glyph_tile(self, glyph, size, color):
        r = dpr()
        S = round(size * r)
        pm = QPixmap(S, S)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(color)
        bg = QColor(col)
        bg.setAlpha(50)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, S, S), S * 0.25, S * 0.25)
        gp = T.glyph_pixmap(glyph, round(size * 0.6), col, r)
        p.drawPixmap(QRectF(S * 0.2, S * 0.2, S * 0.6, S * 0.6), gp, QRectF(0, 0, gp.width(), gp.height()))
        p.end()
        pm.setDevicePixelRatio(r)
        return pm

    def _circle(self, pm, size):
        """Portrait in a soft circle with a rim (map markers, resident headers)."""
        r = dpr()
        S = round(size * r)
        out = QPixmap(S, S)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QRadialGradient(QPointF(S / 2, S * 0.4), S * 0.6)
        g.setColorAt(0, T.mix('card2', 'sky', 0.25))
        g.setColorAt(1, T.c('card2'))
        p.setBrush(g)
        p.setPen(QPen(T.c('line2'), max(1.0, S * 0.03)))
        p.drawEllipse(QRectF(S * 0.02, S * 0.02, S * 0.96, S * 0.96))
        clip = QPainterPath()
        clip.addEllipse(QRectF(S * 0.04, S * 0.04, S * 0.92, S * 0.92))
        p.setClipPath(clip)
        p.drawPixmap(QRectF(0, 0, S, S), pm, QRectF(0, 0, pm.width(), pm.height()))
        p.end()
        out.setDevicePixelRatio(r)
        return out
