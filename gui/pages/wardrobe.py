from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QLinearGradient, QPainter, QPixmap, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.assets import dpr
from gui.pages.base import Page
from gui.tiles import IconTile

OUTFIT_EMOJI = {
    'Familiar 1': '👕', 'Familiar 2': '👚', 'Pokémon Center': '🏥', 'Team Rocket': '🚀', 'Rock-solid': '🪨',
    'Ranger': '🌲', 'Ninja': '🥷', 'Psychic Master': '🔮', 'Black Belt': '🥋', 'Sailor': '⚓', 'Super Nerd': '🤓',
    'Roughneck': '🔧', 'Bird Keeper': '🐦', 'Red': '🧢', 'Fresh': '🌿', 'Cool': '😎', 'Rascal': '😜', 'Cozy': '🧶',
    'Sporty': '⚽', 'Chic': '👗', 'Professor': '🎓', 'Sightseer': '📸', 'Mermaid': '🐚', 'Preschooler': '🎒'}
HAIR_EMOJI = {
    'Short': '💇', 'Pigtails': '🎀', 'Buns': '🍡', 'Two-block cut': '✂️', 'Braided pigtails': '🎀', 'Locs': '🌀',
    'Curly': '🌀', 'Shaved': '🪒', 'Parted': '💇', 'Fluffy': '☁️', 'Mermaid': '🐚', 'Winged pigtails': '🪽',
    'Sideswept': '💨', 'Simple': '💇', 'Long bangs': '💁', 'Long': '💁', 'Crested': '👑', 'Ponytail': '🎀',
    'Messy short': '⚡', 'Side tails': '🎀'}

_cache = {}


def emoji_tile(emoji, size, tint):
    key = (emoji, size, tint, T.NAME, dpr())
    if key in _cache:
        return _cache[key]
    r = dpr()
    S = round(size * r)
    pm = QPixmap(S, S)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 0, S)
    a = T.mix('card2', tint, 0.30)
    b = T.mix('card2', tint, 0.12)
    g.setColorAt(0, a)
    g.setColorAt(1, b)
    p.setBrush(g)
    p.setPen(QPen(T.mix('line', tint, 0.35), max(1.0, S * 0.02)))
    p.drawEllipse(QRectF(S * 0.04, S * 0.04, S * 0.92, S * 0.92))
    f = QFont(T.EMOJI_FONT)
    f.setPixelSize(round(S * 0.5))
    p.setFont(f)
    p.drawText(QRectF(0, 0, S, S * 0.98), Qt.AlignCenter, emoji)
    p.end()
    pm.setDevicePixelRatio(r)
    _cache[key] = pm
    return pm


class WardrobePage(Page):
    title, nav, glyph = 'Wardrobe', 'Wardrobe', T.G['brush']
    subtitle = 'Unlock outfits and hairstyles for the mirror'
    scrollable = True
    GROUPS = (('outfits', 'Outfits', ps.OUTFITS, 'outfit', OUTFIT_EMOJI, 'sky'),
              ('hair', 'Hairstyles', ps.HAIRSTYLES, 'hairstyle', HAIR_EMOJI, 'heart'))

    def build(self):
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(14)
        self.tiles, self.cards, self.bars, self.group_btns = {}, {}, {}, {}
        for key, title, entries, kind, emoji, tint in self.GROUPS:
            card = W.Card(title, '', T.G['brush'] if key == 'outfits' else T.G['person'])
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedWidth(160)
            card.actions.addWidget(bar)
            b = W.button(f'Unlock all {title.lower()}', T.G['unlock'], accent=True,
                         slot=lambda e=entries, t=title: self.unlock([i for i, _ in e if i], f'Unlock all {t.lower()}'))
            card.actions.addWidget(b)
            g = QGridLayout()
            g.setSpacing(8)
            for n, (i, name) in enumerate(entries):
                t = IconTile(name, lambda s, em=emoji.get(name, '👕'), tn=tint: emoji_tile(em, s, tn), style='v', size=(118, 104))
                t.clicked.connect(lambda i=i, nm=f'{name} {kind}': self.toggle(i, nm))
                g.addWidget(t, n // 8, n % 8)
                self.tiles[(key, n)] = (i, name, t)
            for col in range(8):
                g.setColumnStretch(col, 0)
            card.body.addLayout(g)
            lay.addWidget(card)
            self.cards[key], self.bars[key], self.group_btns[key] = card, bar, b
        allc = W.Card('Everything', '', T.G['star'])
        self.all_btn = W.button('Unlock all', T.G['unlock'], lambda: self.unlock(ps.WARDROBE_IDS, 'Unlock all outfits & hairstyles'),
                                accent=True)
        allc.actions.addWidget(self.all_btn)
        allc.body.addWidget(W.label(
            'Click an outfit or hairstyle to unlock it; click a highlighted one to remove it again. Familiar 1/2 and the '
            'starting hairstyles (marked with a lock) are always there. Change clothes in the game before removing the '
            'outfit you are wearing. "Unlock all" also sets the unnamed wardrobe entries; that was tested in game with no '
            'side effects. IDs follow the in-game mirror order, spot-checked in game for 7 outfits and 5 hairstyles.',
            'muted', wrap=True))
        lay.addWidget(allc)
        lay.addStretch(1)
        self.allc = allc

    def refresh(self):
        c = self.c
        if not c:
            return
        for key, title, entries, kind, _, _ in self.GROUPS:
            have = [i for i, _ in entries if c.wardrobe_available(i)]
            self.cards[key].set_subtitle(f'{len(have)} of {len(entries)} available')
            self.bars[key].setRange(0, len(entries))
            self.bars[key].setValue(len(have))
            self.group_btns[key].setEnabled(len(have) < len(entries))
        for (key, n), (i, name, t) in self.tiles.items():
            default = i in ps.WARDROBE_DEFAULTS
            on = c.wardrobe_available(i)
            checked = ' Checked in game.' if i in ps.WARDROBE_CONFIRMED else ''
            if default:
                t.set_state(True, badge=(T.G['lock'], 'faint'), locked=True, tip=f'{name}: always available.')
                t.setCursor(Qt.ArrowCursor)
            else:
                t.set_state(on, tip=f'{name} (item ID {i}): {"unlocked, click to remove" if on else "click to unlock"}.{checked}')
        n, total = len(c.wardrobe_unlocked()), len(ps.WARDROBE_IDS)
        self.allc.set_subtitle(f'{n} of {total} wardrobe entries set in the save')
        self.all_btn.setEnabled(n < total)

    def unlock(self, ids, label):
        if self.app.need():
            self.app.do(label, lambda: self.c.unlock_wardrobe(ids))

    def toggle(self, i, name):
        if not self.app.need() or i in ps.WARDROBE_DEFAULTS:
            return
        if self.c.wardrobe_owned(i):
            self.app.do(f'Remove {name}', lambda: self.c.lock_wardrobe([i]))
        else:
            self.app.do(f'Unlock {name}', lambda: self.c.unlock_wardrobe([i]))
