from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel

from gui import theme as T
from gui import widgets as W


class WelcomePage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.addStretch(2)
        logo = QLabel()
        logo.setPixmap(app.assets.app(128))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        lay.addSpacing(10)
        t = W.label('Pokopia Save Editor', 'h1')
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        s = W.label('Open your Pokopia save to edit your bag, residents, moves, emotes and wardrobe, and to explore '
                    'your islands and photos. Every save is backed up before it is overwritten.', 'muted', wrap=True)
        s.setAlignment(Qt.AlignCenter)
        s.setFixedWidth(540)
        lay.addLayout(W.hbox(None, s, None))
        lay.addSpacing(14)
        row = W.hbox(None, W.button('Find my save…', T.G['search'], app.open_dialog, accent=True), None)
        lay.addLayout(row)
        tip = W.label('Supports Eden, Yuzu, Suyu, Sudachi, Citron, Torzu and Ryujinx saves of Pokopia 2.0.x.', 'small')
        tip.setAlignment(Qt.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(tip)
        lay.addStretch(3)
