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
