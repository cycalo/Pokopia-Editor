"""Colours, fonts, the Qt style sheet and Fluent glyph icons."""
import ctypes
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap, QGuiApplication

PALETTES = {
    'dark': dict(
        bg='#0e161f', side='#111c27', card='#16212d', card2='#1c2937', line='#26364a', line2='#31445c',
        text='#e9eff5', muted='#8c9db0', faint='#5f7185', accent='#41d392', accent2='#2fb87a', onaccent='#05170e',
        sky='#5bb8f2', warn='#f2b84b', danger='#f26d6d', sel='#1d3a4e', selline='#41d392', tile='#1a2633',
        tilefill='#213142', tilehi='#2a3d52', shadow='#05090d', mapbg='#0b1219', badge='#0b141c',
        heart='#ff6f91', gold='#f6c343'),
    'light': dict(
        bg='#f2f5ef', side='#e8eee3', card='#ffffff', card2='#f5f8f2', line='#dbe3d4', line2='#c9d5c0',
        text='#1b2820', muted='#627166', faint='#94a296', accent='#1fa266', accent2='#178a55', onaccent='#ffffff',
        sky='#2b95dc', warn='#b7791f', danger='#d64545', sel='#ddf3e7', selline='#1fa266', tile='#eef3ea',
        tilefill='#ffffff', tilehi='#e3ecdc', shadow='#9aa89a', mapbg='#dfe8ee', badge='#ffffff',
        heart='#e84a72', gold='#d99a00'),
}

NAME = 'dark'
P = dict(PALETTES[NAME])

UI_FONT = 'Segoe UI Variable Text'
DISPLAY_FONT = 'Segoe UI Variable Display'
ICON_FONT = 'Segoe Fluent Icons'
EMOJI_FONT = 'Segoe UI Emoji'

# Fluent icon code points used in the app
G = dict(
    home='', bag='', grid='', people='', smile='', brush='', map='',
    camera='', history='', settings='', open='', save='', saveas='',
    undo='', redo='', search='', close='', add='', remove='',
    delete='', check='', lock='', unlock='', warn='', info='', list='',
    heart='', heartfill='', sun='', moon='', refresh='', export='',
    folder='', star='', pin='', layers='', flag='', copy='', swap='',
    sort='', bulb='', more='', zoomin='', zoomout='', fit='', person='',
    clock='', play='', tag='', gift='', globe='', photo='', shield='',
    compare='', restore='', bell='', filter='', edit='', down='',
    chevron='', back='', next='', emoji='', world='',
)


def set_theme(name):
    global NAME, P
    NAME = name if name in PALETTES else 'dark'
    P.clear()
    P.update(PALETTES[NAME])


def c(key, alpha=None):
    col = QColor(P[key])
    if alpha is not None:
        col.setAlpha(alpha)
    return col


def mix(a, b, t):
    """Blend two colours (keys or QColor), t=0 -> a."""
    a = QColor(P[a]) if isinstance(a, str) and a in P else QColor(a)
    b = QColor(P[b]) if isinstance(b, str) and b in P else QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def font(size=10, weight=QFont.Normal, display=False):
    f = QFont(DISPLAY_FONT if display else UI_FONT)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def available_icon_font():
    fams = set(QFontDatabase.families())
    for f in (ICON_FONT, 'Segoe MDL2 Assets'):
        if f in fams:
            return f
    return None


_icon_cache = {}


def glyph_pixmap(glyph, size, color, dpr=None):
    dpr = dpr or QGuiApplication.primaryScreen().devicePixelRatio()
    key = (glyph, size, QColor(color).name(QColor.HexArgb), dpr)
    pm = _icon_cache.get(key)
    if pm is None:
        pm = QPixmap(round(size * dpr), round(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        fam = available_icon_font()
        if fam:
            p = QPainter(pm)
            p.setRenderHint(QPainter.TextAntialiasing)
            f = QFont(fam)
            f.setPixelSize(round(size * 0.82))
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
            p.end()
        _icon_cache[key] = pm
    return pm


def glyph_icon(glyph, color_key='text', size=18, active_key=None, disabled_key='faint'):
    ic = QIcon()
    ic.addPixmap(glyph_pixmap(glyph, size, P.get(color_key, color_key)), QIcon.Normal, QIcon.Off)
    ic.addPixmap(glyph_pixmap(glyph, size, P.get(active_key or color_key, active_key or color_key)), QIcon.Normal, QIcon.On)
    ic.addPixmap(glyph_pixmap(glyph, size, P.get(disabled_key, disabled_key)), QIcon.Disabled, QIcon.Off)
    if active_key:
        ic.addPixmap(glyph_pixmap(glyph, size, P[active_key]), QIcon.Active, QIcon.Off)
    return ic


def clear_icon_cache():
    _icon_cache.clear()


def arrow_files():
    """Small chevron PNGs for combo boxes and spin boxes (style sheets need image files)."""
    import os, tempfile
    d = os.path.join(tempfile.gettempdir(), 'pokopia_editor_ui')
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, glyph in (('down', '\ue70d'), ('up', '\ue70e')):
        f = os.path.join(d, f'{name}_{NAME}.png')
        pm = glyph_pixmap(glyph, 20, P['muted'], dpr=1.0)
        pm.save(f)
        out[name] = f.replace(os.sep, '/')
    return out


def stylesheet():
    p = P
    arrows = arrow_files()
    return f"""
* {{ font-family: "{UI_FONT}", "Segoe UI"; font-size: 10pt; color: {p['text']}; outline: none; }}
QMainWindow, QDialog, #Root {{ background: {p['bg']}; }}
QWidget#Page, QWidget#PageInner, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QStackedWidget {{ background: transparent; }}
#Sidebar {{ background: {p['side']}; border-right: 1px solid {p['line']}; }}
#Header, #StatusBar {{ background: transparent; }}
#StatusBar {{ border-top: 1px solid {p['line']}; background: {p['side']}; }}
QFrame#Card {{ background: {p['card']}; border: 1px solid {p['line']}; border-radius: 14px; }}
QFrame#SubCard {{ background: {p['card2']}; border: 1px solid {p['line']}; border-radius: 10px; }}
QFrame#Hero {{ border-radius: 16px; border: 1px solid {p['line']}; }}
QLabel {{ background: transparent; }}
QLabel[role="h1"] {{ font-family: "{DISPLAY_FONT}"; font-size: 19pt; font-weight: 700; }}
QLabel[role="h2"] {{ font-family: "{DISPLAY_FONT}"; font-size: 12.5pt; font-weight: 650; }}
QLabel[role="h3"] {{ font-size: 10.5pt; font-weight: 600; }}
QLabel[role="big"] {{ font-family: "{DISPLAY_FONT}"; font-size: 21pt; font-weight: 700; }}
QLabel[role="muted"] {{ color: {p['muted']}; }}
QLabel[role="small"] {{ color: {p['muted']}; font-size: 8.5pt; }}
QLabel[role="caps"] {{ color: {p['muted']}; font-size: 8pt; font-weight: 700; }}
QLabel[role="accent"] {{ color: {p['accent']}; font-weight: 600; }}
QLabel[role="warn"] {{ color: {p['warn']}; }}
QLabel[role="danger"] {{ color: {p['danger']}; }}
QLabel[role="pill"] {{ background: {p['card2']}; border: 1px solid {p['line']}; border-radius: 10px; padding: 2px 9px;
    color: {p['muted']}; font-size: 8.5pt; font-weight: 600; }}
QLabel[role="pillok"] {{ background: {p['sel']}; border: 1px solid {p['accent']}; border-radius: 10px; padding: 2px 9px;
    color: {p['accent']}; font-size: 8.5pt; font-weight: 600; }}
QLabel[role="pillwarn"] {{ background: transparent; border: 1px solid {p['warn']}; border-radius: 10px; padding: 2px 9px;
    color: {p['warn']}; font-size: 8.5pt; font-weight: 600; }}

QPushButton {{ background: {p['card2']}; border: 1px solid {p['line']}; border-radius: 9px; padding: 6px 14px;
    min-height: 20px; }}
QPushButton:hover {{ background: {p['tilehi']}; border-color: {p['line2']}; }}
QPushButton:pressed {{ background: {p['sel']}; }}
QPushButton:disabled {{ color: {p['faint']}; background: {p['card2']}; border-color: {p['line']}; }}
QPushButton:focus {{ border-color: {p['accent']}; }}
QPushButton[accent="true"] {{ background: {p['accent']}; color: {p['onaccent']}; border: 1px solid {p['accent']}; font-weight: 650; }}
QPushButton[accent="true"]:hover {{ background: {p['accent2']}; border-color: {p['accent2']}; }}
QPushButton[accent="true"]:disabled {{ background: {p['line']}; color: {p['faint']}; border-color: {p['line']}; }}
QPushButton[danger="true"] {{ color: {p['danger']}; }}
QPushButton[danger="true"]:hover {{ border-color: {p['danger']}; }}
QPushButton[flat="true"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[flat="true"]:hover {{ background: {p['tilehi']}; }}
QPushButton[small="true"] {{ padding: 3px 10px; font-size: 9pt; border-radius: 8px; min-height: 16px; }}
QPushButton[icononly="true"] {{ padding: 6px; min-width: 22px; }}
QPushButton[chip="true"] {{ background: {p['card2']}; border: 1px solid {p['line']}; border-radius: 13px;
    padding: 4px 11px; font-size: 9pt; min-height: 16px; }}
QPushButton[chip="true"]:hover {{ border-color: {p['line2']}; background: {p['tilehi']}; }}
QPushButton[chip="true"]:checked {{ background: {p['sel']}; border-color: {p['accent']}; color: {p['accent']}; }}
QPushButton[nav="true"] {{ background: transparent; border: none; border-radius: 10px; text-align: left;
    padding: 9px 12px; font-size: 10.5pt; color: {p['muted']}; }}
QPushButton[nav="true"]:hover {{ background: {p['tilehi']}; color: {p['text']}; }}
QPushButton[nav="true"]:checked {{ background: {p['sel']}; color: {p['text']}; font-weight: 600; }}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background: {p['card2']}; border: 1px solid {p['line']}; border-radius: 9px;
    padding: 5px 9px; selection-background-color: {p['accent']}; selection-color: {p['onaccent']}; }}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{ border-color: {p['line2']}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p['accent']}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {p['faint']}; }}
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; border: none; background: transparent; subcontrol-origin: border; }}
QSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 3px 0 0; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 3px 3px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {p['tilehi']}; border-radius: 5px; }}
QSpinBox::up-arrow {{ image: url("{arrows['up']}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{arrows['down']}"); width: 10px; height: 10px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url("{arrows['down']}"); width: 11px; height: 11px; margin-right: 6px; }}
QComboBox::down-arrow:on {{ image: url("{arrows['up']}"); }}
QComboBox QAbstractItemView {{ background: {p['card']}; border: 1px solid {p['line2']}; border-radius: 8px; padding: 4px;
    selection-background-color: {p['sel']}; selection-color: {p['text']}; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {p['line2']}; background: {p['card2']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
QCheckBox:disabled {{ color: {p['faint']}; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['line2']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['line2']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QAbstractItemView {{ background: transparent; border: none; selection-background-color: {p['sel']};
    selection-color: {p['text']}; alternate-background-color: {p['card2']}; }}
QTableView, QTreeView, QListView {{ background: transparent; border: none; gridline-color: {p['line']}; }}
QTableView::item, QTreeView::item {{ border-bottom: 1px solid {p['line']}; padding: 0 6px; }}
QTreeView::item {{ min-height: 34px; }}
QTreeView::item:hover {{ background: {p['tilehi']}; }}
QTableView::item:selected, QTreeView::item:selected {{ background: {p['sel']}; color: {p['text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {p['card']}; color: {p['muted']}; border: none; border-bottom: 1px solid {p['line']};
    padding: 8px 8px; font-size: 8.5pt; font-weight: 700; }}
QHeaderView::section:hover {{ color: {p['text']}; }}
QHeaderView::down-arrow, QHeaderView::up-arrow {{ width: 0; height: 0; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QTextBrowser, QTextEdit {{ background: {p['card2']}; border: 1px solid {p['line']}; border-radius: 10px; padding: 8px; }}
QToolTip {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['line2']}; border-radius: 8px; padding: 6px 9px; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['line2']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 7px; }}
QMenu::item:selected {{ background: {p['sel']}; }}
QMenu::item:disabled {{ color: {p['faint']}; }}
QMenu::separator {{ height: 1px; background: {p['line']}; margin: 5px 6px; }}
QMenu::icon {{ padding-left: 8px; }}
QSlider::groove:horizontal {{ height: 6px; background: {p['line']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {p['card']}; border: 2px solid {p['accent']}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 9px; }}
QSlider::handle:horizontal:hover {{ background: {p['accent']}; }}
QProgressBar {{ background: {p['line']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 3px; }}
QSplitter::handle {{ background: transparent; }}
"""


def dark_titlebar(widget, dark):
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        # Windows 11: caption colour matching the sidebar
        col = QColor(P['side'])
        cref = ctypes.c_int(col.red() | col.green() << 8 | col.blue() << 16)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cref), ctypes.sizeof(cref))
    except Exception:
        pass
