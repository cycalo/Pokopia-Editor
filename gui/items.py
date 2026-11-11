"""Item browser shared by the Bag and Item Catalog pages: search, categories, filters, grid/list, drag source."""
import html
from PySide6.QtCore import (QAbstractListModel, QByteArray, QMimeData, QModelIndex, QPoint, QRect, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QListView, QStyle, QStyledItemDelegate, QVBoxLayout,
                               QWidget, QHBoxLayout, QListWidget, QListWidgetItem, QButtonGroup)

import pokopia_items as pi
import pokopia_save as ps
from gui import theme as T
from gui import widgets as W

ITEM_MIME = 'application/x-pokopia-item'
SLOT_MIME = 'application/x-pokopia-slots'
ID_ROLE = Qt.UserRole + 1


def item_tooltip(i, catalog=None, extra=''):
    name = html.escape(ps.item_name(i))
    cat = pi.category(i)
    lines = [f'<b>{name}</b>', f'<span style="color:{T.P["muted"]}">Item ID {i}  ·  {pi.CAT_LABEL[cat]}</span>']
    size = pi.placeable(i)
    if size:
        lines.append(f'Placeable, {size[0]}×{size[2]} blocks, {size[1]} high')
    d = pi.duplicate_count(i)
    if d > 1:
        lines.append(f'{d} items share this name')
    if catalog is not None:
        lines.append('In your item catalog' if i in catalog else
                     f'<span style="color:{T.P["muted"]}">Not obtained yet</span>')
    if not pi.has_icon(i):
        lines.append(f'<span style="color:{T.P["faint"]}">No game icon available: generated tile</span>')
    if extra:
        lines.append(extra)
    return '<br>'.join(lines)


def drag_pixmap(assets, item_id, count=None, size=52):
    src = assets.item(item_id, size)
    pm = QPixmap(src.size())
    pm.setDevicePixelRatio(src.devicePixelRatio())
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setOpacity(0.92)
    p.drawPixmap(0, 0, src)
    if count:
        f = T.font(8.5, QFont.Bold)
        p.setFont(f)
        t = str(count)
        w = QFontMetrics(f).horizontalAdvance(t) + 10
        r = QRectF(size - w, size - 17, w, 16)
        p.setBrush(T.c('badge', 230))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 8, 8)
        p.setPen(T.c('text'))
        p.drawText(r, Qt.AlignCenter, t)
    p.end()
    return pm


class ItemModel(QAbstractListModel):
    def __init__(self, browser):
        super().__init__()
        self.b = browser
        self.ids = []

    def set_ids(self, ids):
        self.beginResetModel()
        self.ids = ids
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ids)

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        i = self.ids[idx.row()]
        if role == Qt.DisplayRole:
            return ps.item_name(i)
        if role == ID_ROLE:
            return i
        if role == Qt.ToolTipRole:
            return item_tooltip(i, self.b.catalog)
        return None

    def flags(self, idx):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled if idx.isValid() else Qt.NoItemFlags

    def mimeTypes(self):
        return [ITEM_MIME]

    def mimeData(self, idxs):
        md = QMimeData()
        if idxs:
            md.setData(ITEM_MIME, QByteArray(str(self.ids[idxs[0].row()]).encode()))
        return md

    def supportedDragActions(self):
        return Qt.CopyAction


class ItemDelegate(QStyledItemDelegate):
    def __init__(self, browser):
        super().__init__()
        self.b = browser

    def sizeHint(self, opt, idx):
        if self.b.mode == 'list':
            return QSize(200, 42)
        g = self.b.view.gridSize()
        if g.isValid() and g.width() > 0:
            return g
        s = self.b.icon_size
        return QSize(s + 44, s + 50)

    def paint(self, p, opt, idx):
        i = idx.data(ID_ROLE)
        r = QRectF(opt.rect).adjusted(3, 3, -3, -3)
        sel = bool(opt.state & QStyle.State_Selected)
        hover = bool(opt.state & QStyle.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        bg = T.c('sel') if sel else T.c('tilehi') if hover else T.c('tile')
        p.setBrush(bg)
        p.setPen(QPen(T.c('selline') if sel else T.c('line'), 1.6 if sel else 1))
        p.drawRoundedRect(r, 10, 10)
        name = ps.item_name(i)
        cat = pi.category(i)
        if self.b.mode == 'list':
            s = 30
            p.drawPixmap(int(r.x() + 7), int(r.center().y() - s / 2), self.b.assets.item(i, s))
            f = T.font(9.5, QFont.DemiBold if sel else QFont.Normal)
            p.setFont(f)
            p.setPen(T.c('text'))
            tr = QRectF(r.x() + s + 16, r.y(), r.width() - s - 150, r.height())
            p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(f).elidedText(name, Qt.ElideRight, int(tr.width())))
            f2 = T.font(8)
            p.setFont(f2)
            lab = pi.CAT_LABEL[cat]
            w = QFontMetrics(f2).horizontalAdvance(lab) + 14
            pr = QRectF(r.right() - w - 54, r.center().y() - 9, w, 18)
            col = QColor(pi.CAT_COLOR[cat])
            bgc = QColor(col)
            bgc.setAlpha(45)
            p.setBrush(bgc)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(pr, 9, 9)
            p.setPen(col if T.NAME == 'dark' else col.darker(140))
            p.drawText(pr, Qt.AlignCenter, lab)
            p.setPen(T.c('muted'))
            p.drawText(QRectF(r.right() - 50, r.y(), 44, r.height()), Qt.AlignVCenter | Qt.AlignRight, f'#{i}')
        else:
            s = self.b.icon_size
            p.drawPixmap(int(r.center().x() - s / 2), int(r.y() + 8), self.b.assets.item(i, s))
            f = T.font(8 if s < 50 else 8.5, QFont.DemiBold if sel else QFont.Normal)
            p.setFont(f)
            p.setPen(T.c('text') if sel else T.mix('text', 'muted', 0.25))
            tr = QRectF(r.x() + 4, r.y() + s + 10, r.width() - 8, r.height() - s - 12)
            fm = QFontMetrics(f)
            lines = self._two_lines(name, fm, int(tr.width()))
            p.drawText(tr, Qt.AlignHCenter | Qt.AlignTop, '\n'.join(lines))
        # catalog dot
        if self.b.catalog is not None and i in self.b.catalog:
            p.setBrush(T.c('accent'))
            p.setPen(QPen(T.c('card'), 1.5))
            d = 8
            p.drawEllipse(QRectF(r.right() - d - 5, r.y() + 5, d, d))
        # duplicate count
        if self.b.dedupe:
            n = pi.duplicate_count(i)
            if n > 1:
                f3 = T.font(7.5, QFont.Bold)
                p.setFont(f3)
                t = f'×{n}'
                w = QFontMetrics(f3).horizontalAdvance(t) + 8
                br = QRectF(r.x() + 5, r.y() + 5, w, 14)
                p.setBrush(T.c('badge', 220))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(br, 7, 7)
                p.setPen(T.c('muted'))
                p.drawText(br, Qt.AlignCenter, t)
        p.restore()

    @staticmethod
    def _two_lines(text, fm, w):
        if fm.horizontalAdvance(text) <= w:
            return [text]
        words, first = text.split(' '), ''
        for n in range(len(words), 0, -1):
            cand = ' '.join(words[:n])
            if fm.horizontalAdvance(cand) <= w:
                first = cand
                rest = ' '.join(words[n:])
                return [first, fm.elidedText(rest, Qt.ElideRight, w)] if rest else [first]
        return [fm.elidedText(text, Qt.ElideRight, w)]


class ItemView(QListView):
    slots_dropped = Signal(list)

    def __init__(self, browser):
        super().__init__()
        self.b = browser
        self.setMouseTracking(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)   # keeps the column count stable
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.drop_hint = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit_grid()

    def fit_grid(self):
        if self.viewMode() != QListView.IconMode:
            self.setGridSize(QSize())
            return
        s = self.b.icon_size
        w = max(1, self.viewport().width() - 2)
        n = max(1, w // (s + 44))
        g = QSize(w // n, s + 50)
        if g != self.gridSize():
            self.setGridSize(g)

    def startDrag(self, actions):
        idx = self.currentIndex()
        if not idx.isValid():
            return
        i = idx.data(ID_ROLE)
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData([idx]))
        pm = drag_pixmap(self.b.assets, i, None, 52)
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(26, 26))
        drag.exec(Qt.CopyAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(SLOT_MIME):
            e.acceptProposedAction()
            self.drop_hint = True
            self.viewport().update()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(SLOT_MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.drop_hint = False
        self.viewport().update()

    def dropEvent(self, e):
        self.drop_hint = False
        self.viewport().update()
        if e.mimeData().hasFormat(SLOT_MIME):
            src, sel = bytes(e.mimeData().data(SLOT_MIME)).decode().split(';')
            slots = [int(s) for s in sel.split(',') if s] or [int(src)]
            e.acceptProposedAction()
            self.slots_dropped.emit(slots)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.drop_hint:
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(self.viewport().rect()).adjusted(4, 4, -4, -4)
            p.setBrush(T.c('danger', 30))
            p.setPen(QPen(T.c('danger'), 2, Qt.DashLine))
            p.drawRoundedRect(r, 12, 12)
            p.setPen(T.c('danger'))
            p.setFont(T.font(11, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, 'Drop here to remove from the bag')


class ItemBrowser(QWidget):
    """Search + category filter + options + item grid. `compact` uses a category dropdown (narrow panels);
    otherwise the category is set from outside (Item Catalog's category list)."""
    picked = Signal(int)
    activated = Signal(int)

    def __init__(self, app, compact=True, icon_size=40):
        super().__init__()
        self.app, self.assets, self.compact = app, app.assets, compact
        self.icon_size = icon_size
        self.mode = 'grid'
        self.category = None
        self.catalog = None
        self.only_icons = self.only_catalog = False
        self.dedupe = True
        self.sort = 'name'
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.q = W.SearchField('Search items by name or ID')
        self.q.textChanged.connect(self.refilter)
        lay.addWidget(self.q)
        row = QHBoxLayout()
        row.setSpacing(6)
        if compact:
            self.cat_box = QComboBox()
            self.cat_box.setMinimumWidth(170)
            self.cat_box.currentIndexChanged.connect(self._cat_from_box)
            row.addWidget(self.cat_box, 1)
        self.sort_box = QComboBox()
        self.sort_box.addItems(['Sort: Name', 'Sort: ID', 'Sort: Category'])
        self.sort_box.setFixedWidth(128)
        self.sort_box.currentIndexChanged.connect(self._sort_changed)
        row.addWidget(self.sort_box, 0 if compact else 0)
        if not compact:
            row.addStretch(1)
        self.vgrid = W.button('', T.G['grid'], lambda: self.set_mode('grid'), tip='Icon grid', checkable=True, flat=True)
        self.vlist = W.button('', T.G['list'], lambda: self.set_mode('list'), tip='List', checkable=True, flat=True)
        grp = QButtonGroup(self)
        grp.addButton(self.vgrid)
        grp.addButton(self.vlist)
        self.vgrid.setChecked(True)
        row.addWidget(self.vgrid)
        row.addWidget(self.vlist)
        lay.addLayout(row)
        opts = QHBoxLayout()
        opts.setSpacing(6)
        self.c_icons = W.chip('With icon', slot=self._opts)
        self.c_catalog = W.chip('In my catalog', slot=self._opts)
        self.c_dedupe = W.chip('One per name', slot=self._opts)
        self.c_dedupe.setChecked(True)
        self.c_icons.setToolTip('Only items that have a game icon')
        self.c_catalog.setToolTip('Only items your item catalog marks as obtained (read from the save)')
        self.c_dedupe.setToolTip('Some names exist many times (e.g. 100 jump rope trophies). Show each name once.')
        for c in (self.c_icons, self.c_catalog, self.c_dedupe):
            opts.addWidget(c)
        opts.addStretch(1)
        self.count = W.label('', 'small')
        opts.addWidget(self.count)
        lay.addLayout(opts)
        self.model = ItemModel(self)
        self.view = ItemView(self)
        self.view.setModel(self.model)
        self.view.setItemDelegate(ItemDelegate(self))
        self.view.selectionModel().currentChanged.connect(self._current)
        self.view.doubleClicked.connect(lambda idx: self.activated.emit(idx.data(ID_ROLE)))
        self.view.activated.connect(lambda idx: self.activated.emit(idx.data(ID_ROLE)))
        lay.addWidget(self.view, 1)
        self.empty = W.label('No items match. Try another category or clear the filters.', 'muted', wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        lay.addWidget(self.empty)
        self.set_mode('grid')
        self.fill_categories()

    # ---------- configuration ----------
    def fill_categories(self):
        if not self.compact:
            return
        counts = pi.category_counts()
        self.cat_box.blockSignals(True)
        self.cat_box.clear()
        self.cat_box.addItem(f'All categories  ({sum(counts.values()):,})', None)
        for key, label, color, glyph in pi.CATEGORIES:
            if counts.get(key):
                self.cat_box.addItem(f'{glyph}  {label}  ({counts[key]:,})', key)
        self.cat_box.blockSignals(False)

    def _cat_from_box(self, n):
        self.category = self.cat_box.itemData(n)
        self.refilter()

    def set_category(self, key):
        self.category = key
        self.refilter()

    def _sort_changed(self, n):
        self.sort = ('name', 'id', 'cat')[n]
        self.refilter()

    def _opts(self):
        self.only_icons = self.c_icons.isChecked()
        self.only_catalog = self.c_catalog.isChecked()
        self.dedupe = self.c_dedupe.isChecked()
        self.refilter()

    def set_mode(self, mode):
        self.mode = mode
        v = self.view
        if mode == 'grid':
            v.setViewMode(QListView.IconMode)
            v.setResizeMode(QListView.Adjust)
            v.setMovement(QListView.Static)
            v.setWrapping(True)
            v.setSpacing(0)
        else:
            v.setViewMode(QListView.ListMode)
            v.setWrapping(False)
            v.setSpacing(0)
        # QListView.setViewMode resets the drag and drop settings
        v.setDragEnabled(True)
        v.setAcceptDrops(True)
        v.viewport().setAcceptDrops(True)
        v.setDragDropMode(QAbstractItemView.DragDrop)
        v.setDefaultDropAction(Qt.CopyAction)
        v.setUniformItemSizes(True)
        v.fit_grid()
        self.vgrid.setChecked(mode == 'grid')
        self.vlist.setChecked(mode == 'list')
        self.model.set_ids(list(self.model.ids))

    def save_changed(self):
        c = self.app.save.common if self.app.save else None
        self.catalog = c.catalog_items() if c else None
        self.refilter()

    # ---------- filtering ----------
    def refilter(self):
        q = self.q.text().strip().lower().lstrip('#')
        cur = self.current_id()
        ids = []
        cat, cata = self.category, self.catalog
        for i in pi.browsable_ids():
            if cat and pi.category(i) != cat:
                continue
            if self.only_icons and not pi.has_icon(i):
                continue
            if self.only_catalog and (cata is None or i not in cata):
                continue
            if q:
                if q.isdigit():
                    if str(i) != q and q not in ps.ITEM_NAMES[i].lower():
                        continue
                elif q not in ps.ITEM_NAMES[i].lower():
                    continue
            if self.dedupe and not q.isdigit() and not pi.is_first_of_name(i):
                continue
            ids.append(i)
        if self.sort == 'name':
            ids.sort(key=lambda i: (ps.ITEM_NAMES[i].lower(), i))
        elif self.sort == 'cat':
            ids.sort(key=lambda i: (pi.CAT_INDEX[pi.category(i)], ps.ITEM_NAMES[i].lower(), i))
        self.model.set_ids(ids)
        self.count.setText(f'{len(ids):,} items')
        self.empty.setVisible(not ids)
        self.view.setVisible(bool(ids))
        if cur in ids:
            self.select(cur)

    def select(self, item_id):
        try:
            row = self.model.ids.index(item_id)
        except ValueError:
            return
        idx = self.model.index(row)
        self.view.setCurrentIndex(idx)
        self.view.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def current_id(self):
        idx = self.view.currentIndex()
        return idx.data(ID_ROLE) if idx.isValid() else 0

    def _current(self, idx, _prev):
        if idx.isValid():
            self.picked.emit(idx.data(ID_ROLE))

    def focus_search(self):
        self.q.setFocus()
        self.q.selectAll()


class CategoryList(QListWidget):
    """Vertical category picker for the Item Catalog page."""
    chosen = Signal(object)

    def __init__(self):
        super().__init__()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet('QListWidget::item { padding: 5px 8px; border-radius: 8px; border: none; margin: 0; }'
                           f'QListWidget::item:selected {{ background: {T.P["sel"]}; color: {T.P["text"]}; }}'
                           f'QListWidget::item:hover:!selected {{ background: {T.P["tilehi"]}; }}')
        self.setIconSize(QSize(14, 14))
        counts = pi.category_counts()
        it = QListWidgetItem(f'All items   {sum(counts.values()):,}')
        it.setData(Qt.UserRole, None)
        it.setIcon(self._dot(T.P['accent']))
        self.addItem(it)
        for key, label, color, glyph in pi.CATEGORIES:
            if counts.get(key):
                it = QListWidgetItem(f'{label}   {counts[key]:,}')
                it.setData(Qt.UserRole, key)
                it.setIcon(self._dot(color))
                it.setToolTip(f'{glyph}  {label}')
                self.addItem(it)
        self.setCurrentRow(0)
        self.currentItemChanged.connect(lambda it, _: it and self.chosen.emit(it.data(Qt.UserRole)))

    @staticmethod
    def _dot(color):
        pm = QPixmap(28, 28)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(1, 1, 12, 12))
        p.end()
        from PySide6.QtGui import QIcon
        return QIcon(pm)
