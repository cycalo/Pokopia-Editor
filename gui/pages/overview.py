import datetime, os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QVBoxLayout, QWidget)

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page


class ClickTile(W.StatTile):
    def __init__(self, glyph, caption, color, on_click):
        super().__init__(glyph, caption, color)
        self.on_click = on_click
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.on_click:
            self.on_click()


class OverviewPage(Page):
    title, nav, glyph = 'Overview', 'Overview', T.G['home']
    subtitle = 'Your save at a glance'
    scrollable = True

    def build(self):
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(14)
        # hero
        hero = QFrame()
        hero.setObjectName('Hero')
        hero.setStyleSheet(f'QFrame#Hero {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, '
                           f'stop:0 {T.mix("card", "sky", 0.20).name()}, stop:0.55 {T.mix("card", "accent", 0.10).name()}, '
                           f'stop:1 {T.P["card"]}); }}')
        h = QHBoxLayout(hero)
        h.setContentsMargins(22, 18, 22, 18)
        h.setSpacing(18)
        self.avatar = QLabel()
        self.avatar.setPixmap(self.app.assets.villager(78, 92, circle=True))
        h.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(W.label('PLAYER', 'caps'))
        self.name_lbl = W.label('', 'big')
        col.addWidget(self.name_lbl)
        self.meta = W.label('', 'muted')
        col.addWidget(self.meta)
        h.addLayout(col, 1)
        rn = QVBoxLayout()
        rn.setSpacing(6)
        rn.addWidget(W.label('Rename', 'caps'))
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.setMinimumWidth(240)
        self.name.returnPressed.connect(self.apply_name)
        rn.addLayout(W.hbox(self.name, W.button('Rename', T.G['edit'], self.apply_name)))
        rn.addWidget(W.label('Up to 24 UTF-8 bytes. Every copy of the name is updated.', 'small'))
        h.addLayout(rn)
        lay.addWidget(hero)
        # stat tiles
        g = QGridLayout()
        g.setSpacing(12)
        a = self.app
        spec = [('Residents', T.G['people'], 'accent', 'Residents'), ('Bag', T.G['bag'], 'sky', 'Bag'),
                ('Moves', T.G['play'], 'warn', 'Moves & Emotes'), ('Emotes', T.G['smile'], 'heart', 'Moves & Emotes'),
                ('Wardrobe', T.G['brush'], 'gold', 'Wardrobe'), ('Islands', T.G['map'], 'sky', 'Island Map'),
                ('Photos', T.G['camera'], 'accent', 'Photos'), ('Play time', T.G['clock'], 'muted', None)]
        self.tiles = {}
        for n, (name, glyph, color, target) in enumerate(spec):
            t = ClickTile(glyph, name, color, (lambda t=target: a.show_page(t)) if target else None)
            if target:
                t.setToolTip(f'Open {target}')
            g.addWidget(t, n // 4, n % 4)
            g.setColumnStretch(n % 4, 1)
            self.tiles[name] = t
        lay.addLayout(g)
        # lower row
        row = QHBoxLayout()
        row.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        qa = W.Card('Quick actions', 'One click each, and each one can be undone.', T.G['bulb'])
        self.quick = {}
        for key, glyph, text in (('friend', T.G['heart'], f'Max friendship for everyone ({ps.FRIENDSHIP_MAX})'),
                                 ('emotes', T.G['smile'], 'Learn every emote'),
                                 ('wardrobe', T.G['brush'], 'Unlock all outfits & hairstyles'),
                                 ('stacks', T.G['bag'], 'Fill every bag stack to 99')):
            b = W.button(text, glyph, lambda k=key: self.quick_action(k))
            b.setStyleSheet('text-align: left; padding: 9px 14px;')
            qa.body.addWidget(b)
            self.quick[key] = b
        left.addWidget(qa)
        sf = W.Card('Save folder', None, T.G['folder'])
        self.folder = W.label('', sel=True, wrap=True)
        sf.body.addWidget(self.folder)
        self.ver = W.label('', 'small', wrap=True)
        sf.body.addWidget(self.ver)
        self.emu = W.Pill('')
        sf.body.addWidget(self.emu, 0, Qt.AlignLeft)
        sf.body.addLayout(W.hbox(W.button('Open in Explorer', T.G['folder'], self.open_folder),
                                 W.button('Reload from disk', T.G['refresh'], a.reload), None))
        left.addWidget(sf)
        left.addStretch(1)
        row.addLayout(left, 1)
        pc = self.pc = W.Card('Pending changes', '', T.G['history'])
        self.hist = QListWidget()
        self.hist.setMinimumHeight(220)
        self.hist.setStyleSheet(f'QListWidget::item {{ padding: 7px 6px; border-bottom: 1px solid {T.P["line"]}; }}')
        pc.body.addWidget(self.hist, 1)
        self.empty_hist = W.label('Edits you make on any page show up here, and stay undoable until you save.',
                                  'muted', wrap=True)
        pc.body.addWidget(self.empty_hist)
        pc.body.addStretch(1)
        pc.body.addLayout(W.hbox(W.button('Undo', T.G['undo'], a.undo), W.button('Redo', T.G['redo'], a.redo), None,
                                 W.button('Review all changes', T.G['list'], a.review)))
        row.addWidget(pc, 1)
        lay.addLayout(row)
        lay.addStretch(1)

    def apply_name(self):
        if self.app.need():
            self.app.do('Rename player', lambda: setattr(self.c, 'player_name', self.name.text()))

    def open_folder(self):
        if self.app.save:
            os.startfile(self.app.save.folder)

    def quick_action(self, key):
        c, a = self.c, self.app
        if not a.need():
            return
        if key == 'friend':
            low = [i for i in c.villagers() if c.get_villager(i)['friendship'] < ps.FRIENDSHIP_MAX]
            a.do(f'Max friendship for {len(low)} residents', lambda: [c.set_friendship(i, ps.FRIENDSHIP_MAX) for i in low])
        elif key == 'emotes':
            a.do('Learn all emotes', lambda: [c.learn_reaction(i) for i in ps.PUBLIC_REACTIONS])
        elif key == 'wardrobe':
            a.do('Unlock all outfits & hairstyles', lambda: c.unlock_wardrobe(ps.WARDROBE_IDS))
        elif key == 'stacks':
            low = [s for s in c.filled_slots() if c.get_slot(s)[1] < 99]
            a.do(f'{len(low)} bag stacks to 99', lambda: [c.set_count(s, 99) for s in low])

    def refresh(self):
        c, app = self.c, self.app
        if not c:
            return
        self.name.setText(c.player_name)
        self.name_lbl.setText(c.player_name or 'Player')
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(c.path))
        pt = c.play_seconds
        self.meta.setText(f'Last saved {mt:%d %b %Y, %H:%M}   ·   {ps.fmt_playtime(pt) if pt is not None else "?"} played')
        vs = [c.get_villager(i) for i in c.villagers()]
        maxed = sum(v['friendship'] >= ps.FRIENDSHIP_MAX for v in vs)
        self.tiles['Residents'].set(len(vs), f'{maxed} at max friendship', maxed / len(vs) if vs else 0)
        filled = len(c.filled_slots())
        self.tiles['Bag'].set(filled, f'of {ps.INV_COUNT} slots filled', filled / ps.INV_COUNT)
        mv = sum(c.skill(i)[1] for i in ps.PUBLIC_SKILLS)
        ex = sum(c.extra(k) for k in ps.EXTRAS)
        self.tiles['Moves'].set(mv, f'of {len(ps.PUBLIC_SKILLS)} learned · {ex} of {len(ps.EXTRAS)} extras', mv / len(ps.PUBLIC_SKILLS))
        em = sum(c.reaction_learned(i) for i in ps.PUBLIC_REACTIONS)
        self.tiles['Emotes'].set(em, f'of {len(ps.PUBLIC_REACTIONS)} learned', em / len(ps.PUBLIC_REACTIONS))
        entries = ps.OUTFITS + ps.HAIRSTYLES
        have = sum(c.wardrobe_available(i) for i, _ in entries)
        self.tiles['Wardrobe'].set(have, f'of {len(entries)} outfits & hairstyles', have / len(entries))
        st = app.save.stage_files()
        names = [ps.name_of(ps.AREA_NAMES, n, 'Area') for n in st]
        self.tiles['Islands'].set(len(st), ', '.join(names))
        self.tiles['Islands'].setToolTip('\n'.join(names))
        a = app.album
        self.tiles['Photos'].set(len(a) if a is not None else ('…' if app.album_state == 'loading' else '-'),
                                 'in the album' if a is not None else app.album_state)
        self.tiles['Play time'].set(ps.fmt_playtime(pt) if pt is not None else '-', 'read from the save')
        self.folder.setText(app.save.folder.replace(os.sep, os.sep + '​'))
        self.ver.setText(f'Game save version {ps.VERSION:#010x} (Pokopia 2.0.x). Only G00\\CMNDAT.BIN is ever written; '
                         'islands, photos and the game\'s own backup slot are copied untouched.')
        if app.emus:
            self.emu.set(f'●  {", ".join(app.emus)} is running. Close it before overwriting the save.', 'pillwarn')
        else:
            self.emu.set('●  No emulator running. Safe to overwrite.', 'pillok')
        h = c.history
        self.hist.clear()
        for n, lbl in enumerate(h, 1):
            it = QListWidgetItem(f'{n}.   {lbl}')
            self.hist.addItem(it)
        self.hist.scrollToBottom()
        self.hist.setVisible(bool(h))
        self.empty_hist.setVisible(not h)
        self.pc.set_subtitle(f'{len(h)} edit{"s" if len(h) != 1 else ""} not saved yet' if h else 'Nothing changed yet')
        self.quick['friend'].setEnabled(maxed < len(vs))
        self.quick['emotes'].setEnabled(em < len(ps.PUBLIC_REACTIONS))
        self.quick['wardrobe'].setEnabled(len(c.wardrobe_unlocked()) < len(ps.WARDROBE_IDS))
        self.quick['stacks'].setEnabled(any(c.get_slot(s)[1] < 99 for s in c.filled_slots()))
