# Linux port modifications by frinimini, 2026-11-25. See CREDITS.md.
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QFrame
from PySide6.QtCore import Qt


class Page(QWidget):
    """One sidebar destination. Subclasses fill `build()` and `refresh()`."""
    title = ''
    nav = ''
    glyph = ''
    subtitle = ''
    scrollable = False

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.dirty = True
        self.setObjectName('Page')
        if self.scrollable:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            inner = QWidget()
            inner.setObjectName('PageInner')
            sa.setWidget(inner)
            outer.addWidget(sa)
            self.root = inner
            self.scroll = sa
        else:
            self.root = self
            self.scroll = None
        self.build()

    @property
    def c(self):
        return self.app.save.common if self.app.save else None

    @property
    def P(self):
        from gui import theme
        return theme.P

    def build(self):
        pass

    def refresh(self):
        pass

    def focus_search(self):
        pass

    def subtitle_text(self):
        return self.subtitle

    def preferences(self):
        """View/tool preferences, separate from the opened save's values."""
        previous = self.app.settings.get('tools', {}).get(self.nav, {})
        if not getattr(self, '_preferences_restored', False):
            return previous if isinstance(previous, dict) else {}
        state = {}
        for name in ('q', 'flag_q'):
            widget = getattr(self, name, None)
            if widget is not None:
                state[name] = widget.text()
        for name in ('missing', 'unused_chip'):
            widget = getattr(self, name, None)
            if widget is not None:
                state[name] = widget.isChecked()
        browser = getattr(self, 'browser', None)
        if browser is not None:
            state['browser'] = browser.preferences()
        if self.nav == 'Mods':
            state['load_dir'] = self.load_dir()
            state['choices'] = {card.mod.id: dict(option=card.pick.currentText() if card.pick else None,
                                                 live=card.live.currentText() if hasattr(card, 'live') else None,
                                                 experimental=card.exp.currentText() if getattr(card, 'exp', None) else None)
                                for card in self.cards}
        if self.nav == 'Photos':
            state['photo'] = getattr(self, '_pending_photo', None) if self.cur() is None else self.cur()
        if self.nav == 'Collection':
            state['kind'] = self.kind
        if self.nav == 'Residents':
            state['island'] = self.island.currentData()
        if self.nav == 'Item Catalog':
            state['amount'] = self.amount.value()
        table = getattr(self, 'tv', None)
        if table is not None:
            header = table.horizontalHeader() if hasattr(table, 'horizontalHeader') else table.header()
            state['header'] = bytes(header.saveState().toBase64()).decode('ascii')
        if self.scroll:
            state['scroll'] = self.scroll.verticalScrollBar().value()
        return state

    def restore_preferences(self):
        if getattr(self, '_preferences_restored', False):
            return
        self._preferences_restored = True
        state = self.app.settings.get('tools', {}).get(self.nav, {})
        if not isinstance(state, dict):
            return
        for name in ('q', 'flag_q'):
            widget = getattr(self, name, None)
            if widget is not None and isinstance(state.get(name), str):
                widget.setText(state[name])
        for name in ('missing', 'unused_chip'):
            widget = getattr(self, name, None)
            if widget is not None and isinstance(state.get(name), bool):
                widget.setChecked(state[name])
        browser = getattr(self, 'browser', None)
        if browser is not None and isinstance(state.get('browser'), dict):
            browser.restore_preferences(state['browser'])
        if self.nav == 'Collection' and isinstance(state.get('kind'), str) and state['kind'] in self.chips:
            self.set_kind(state['kind'])
        if self.nav == 'Photos' and type(state.get('photo')) is int:
            self._pending_photo = max(0, state['photo'])
            self.refresh()
        if self.nav == 'Residents':
            index = self.island.findData(state.get('island'))
            if index >= 0:
                self.island.setCurrentIndex(index)
        if self.nav == 'Item Catalog':
            if type(state.get('amount')) is int:
                self.amount.setValue(state['amount'])
            category = self.browser.category
            for index in range(self.cats.count()):
                if self.cats.item(index).data(Qt.UserRole) == category:
                    self.cats.setCurrentRow(index)
                    break
        if self.nav == 'Collection':
            self.fill()
        if self.nav == 'Advanced':
            self.fill_flags()
        if self.nav == 'Mods':
            self.fill_where(select=state.get('load_dir'))
            choices = state.get('choices', {})
            if isinstance(choices, dict):
                for card in self.cards:
                    choice = choices.get(card.mod.id, {})
                    if not isinstance(choice, dict):
                        continue
                    for name, key in (('pick', 'option'), ('live', 'live'), ('exp', 'experimental')):
                        box = getattr(card, name, None)
                        if box is not None and isinstance(choice.get(key), str):
                            index = box.findText(choice[key])
                            if index >= 0:
                                box.setCurrentIndex(index)
        table = getattr(self, 'tv', None)
        if table is not None and isinstance(state.get('header'), str):
            from PySide6.QtCore import QByteArray
            header = table.horizontalHeader() if hasattr(table, 'horizontalHeader') else table.header()
            header.restoreState(QByteArray.fromBase64(state['header'].encode('ascii', errors='ignore')))
        if self.scroll and type(state.get('scroll')) is int:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(state['scroll']))
