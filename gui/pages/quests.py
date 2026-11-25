"""Quests page: the island's quest log as the save holds it, and a way to finish a quest that got stuck.

Layout: one progress tile per area on top (click to filter), the quest list on the left (reads like the game's
quest log: title, area, what it gives) and a detail panel on the right that says what completing the quest here
will and will not do before anything is changed."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar,
                               QStyle, QStyledItemDelegate, QVBoxLayout)

import struct

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page

OPEN = (ps.QUEST_UNLOCKED, ps.QUEST_ACTIVE)
STATE_FILTERS = (('open', 'In progress', OPEN),
                 ('done', 'Done', (ps.QUEST_DONE,)),
                 ('todo', 'Not started', (ps.QUEST_NOT_STARTED,)),
                 ('all', 'All', tuple(ps.QUEST_STATES)))
HEAD, ROW = 1, 2  # list item kinds


def state_key(st):
    return 'accent' if st == ps.QUEST_DONE else 'warn' if st in OPEN else 'faint'


def state_text(st):
    return ps.QUEST_STATES.get(st, f'State {st}')


def quest_title(q):
    return ps.quest_name(q) or 'Untitled quest'


class QuestDelegate(QStyledItemDelegate):
    """Two-line quest rows (status mark, title, type tag / number, rewards) and area header rows. The area and state
    words are only written out when the list does not already say them (one area, one state)."""

    def __init__(self, page):
        super().__init__()
        self.page = page

    def paint(self, p, opt, idx):
        d = idx.data(Qt.UserRole)
        r = QRectF(opt.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if d[0] == HEAD:
            p.setFont(T.font(8.5, QFont.DemiBold))
            p.setPen(T.c('muted'))
            p.drawText(r.adjusted(12, 0, -12, -4), Qt.AlignLeft | Qt.AlignBottom, d[1].upper())
            p.drawText(r.adjusted(12, 0, -12, -4), Qt.AlignRight | Qt.AlignBottom, d[2])
            p.restore()
            return
        _, q, st = d
        sel = bool(opt.state & QStyle.State_Selected)
        bg = T.c('sel') if sel else T.c('tilehi') if opt.state & QStyle.State_MouseOver else None
        if bg is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r.adjusted(2, 1, -2, -1), 9, 9)
        # status mark: filled check for done, ring with dot in progress, empty ring not started
        c = QRectF(r.x() + 14, r.center().y() - 9, 18, 18)
        col = T.c(state_key(st))
        if st == ps.QUEST_DONE:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(c)
            p.setPen(QPen(QColor(T.P['card']), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            o = c.topLeft()
            p.drawPolyline([o + QPointF(5, 9.5), o + QPointF(8, 12.5), o + QPointF(13, 6)])
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(col, 2))
            p.drawEllipse(c.adjusted(1, 1, -1, -1))
            if st in OPEN:
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(c.adjusted(5.5, 5.5, -5.5, -5.5))
        x = c.right() + 14
        # type tag on the right
        kind = ps.quest_type(q)
        f_tag = T.font(7.5, QFont.DemiBold)
        fm_tag = QFontMetrics(f_tag)
        tw = fm_tag.horizontalAdvance(kind) + 16
        tag = QRectF(r.right() - tw - 12, r.y() + 9, tw, 18)
        tcol = T.c('sky' if kind == 'Request' else 'accent' if kind == 'Main story' else 'muted')
        fill = QColor(tcol)
        fill.setAlpha(30)
        p.setPen(QPen(tcol, 1))
        p.setBrush(fill)
        p.drawRoundedRect(tag, 9, 9)
        p.setFont(f_tag)
        p.setPen(tcol)
        p.drawText(tag, Qt.AlignCenter, kind)
        # title
        name = ps.quest_name(q)
        f_title = T.font(10, QFont.DemiBold)
        p.setFont(f_title)
        f_title.setItalic(not name)
        p.setFont(f_title)
        p.setPen(T.c('text') if name else T.c('muted'))
        tr = QRectF(x, r.y() + 6, tag.x() - x - 10, 22)
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f_title).elidedText(quest_title(q), Qt.ElideRight, int(tr.width())))
        # second line
        bits = [f'#{q}']
        if self.page.state == 'all':
            bits.append(state_text(st))
        gives = ps.quest_summary(q)
        if gives:
            bits.append(gives)
        f_sub = T.font(8.5)
        p.setFont(f_sub)
        p.setPen(T.c('muted'))
        sr = QRectF(x, r.y() + 28, r.right() - x - 12, 18)
        p.drawText(sr, Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f_sub).elidedText('  ·  '.join(bits), Qt.ElideRight, int(sr.width())))
        p.restore()

    def sizeHint(self, opt, idx):
        return QSize(200, 34 if idx.data(Qt.UserRole)[0] == HEAD else 54)


class AreaTile(QFrame):
    """Clickable progress tile for one area (or all of them)."""
    clicked = Signal()

    def __init__(self, name):
        super().__init__()
        self.setObjectName('SubCard')
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)
        self.name = W.label(name, 'h3')
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.info = W.label('', 'small')
        lay.addWidget(self.name)
        lay.addWidget(self.bar)
        lay.addWidget(self.info)
        self.set_selected(False)

    def set_counts(self, done, total, open_):
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(done)
        self.info.setText(f'{done} of {total} done' + (f'  ·  {open_} open' if open_ else ''))

    def set_selected(self, on):
        border = T.P['accent'] if on else T.P['line']
        self.setStyleSheet(f'QFrame#SubCard {{ border: {2 if on else 1}px solid {border}; }}')

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class QuestsPage(Page):
    title, nav, glyph = 'Quests', 'Quests', T.G['list']
    subtitle = 'Your quest log for every area. Finish a quest that got stuck.'

    @property
    def unlocked(self):
        return self.app.adv_unlocked

    def build(self):
        self.area, self.state, self.shown = 0, 'open', []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # area overview
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = []
        for n, name in enumerate(['All areas'] + [a[2] for a in ps.QUEST_AREAS]):
            t = AreaTile(name)
            t.clicked.connect(lambda n=n: self.set_area(n))
            tiles.addWidget(t, 1)
            self.tiles.append(t)
        root.addLayout(tiles)

        body = QHBoxLayout()
        body.setSpacing(14)
        # quest list
        left = W.Card(padding=12)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.q = W.SearchField('Search titles, numbers or rewards (Surf, bed...)')
        self.q.setMinimumWidth(240)
        self.q.setMaximumWidth(340)
        self.q.textChanged.connect(lambda *_: self.fill())
        bar.addWidget(self.q, 1)
        bar.addSpacing(6)
        self.state_chips = {}
        for key, label, _ in STATE_FILTERS:
            ch = W.chip(label, slot=lambda k=key: self.set_state(k))
            bar.addWidget(ch)
            self.state_chips[key] = ch
        bar.addStretch(1)
        left.body.addLayout(bar)
        self.list = QListWidget()
        self.list.setItemDelegate(QuestDelegate(self))
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setMouseTracking(True)
        self.list.setStyleSheet('QListWidget { background: transparent; border: none; }')
        self.list.itemSelectionChanged.connect(self.on_select)
        left.body.addWidget(self.list, 1)
        self.empty = W.label('', 'muted', wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        left.body.addWidget(self.empty, 1)
        body.addWidget(left, 1)

        # detail panel
        d = W.Card(padding=18, spacing=8)
        d.setFixedWidth(380)
        self.d_kind = W.label('', 'caps')
        self.d_title = W.label('Select a quest', 'h2', wrap=True)
        self.d_sub = W.label('Pick one from the list to see what it does.', 'muted', wrap=True)
        for w in (self.d_kind, self.d_title, self.d_sub):
            d.body.addWidget(w)
        d.body.addWidget(W.hline())
        self.d_gives_h = W.label('COMPLETING IT HERE', 'caps')
        self.d_gives = W.label('', wrap=True)
        self.d_gives.setTextFormat(Qt.RichText)
        self.d_left_h = W.label('LEFT TO THE GAME', 'caps')
        self.d_left = W.label('', 'muted', wrap=True)
        for w in (self.d_gives_h, self.d_gives, self.d_left_h, self.d_left):
            d.body.addWidget(w)
        d.body.addStretch(1)
        # lock: shown in place of the buttons until the user agrees
        self.lock = QFrame()
        self.lock.setObjectName('SubCard')
        ll = QVBoxLayout(self.lock)
        ll.setContentsMargins(12, 10, 12, 10)
        ll.setSpacing(6)
        warn = W.label('Quests normally move on by themselves. Edit one only when it is stuck, and keep a backup: '
                       'the game may still expect the parts the editor cannot do. Not yet tested in game.',
                       'small', wrap=True)
        ll.addWidget(warn)
        self.gate = W.ToggleRow('Let me edit quests')
        self.gate.toggle.toggled.connect(self.set_gate)
        ll.addWidget(self.gate)
        d.body.addWidget(self.lock)
        self.rewards = W.ToggleRow('Also give what the quest gives', 'Off: only the quest\'s state changes.')
        self.rewards.toggle.set_quiet(True)
        self.rewards.toggle.toggled.connect(lambda *_: self.show_detail())
        d.body.addWidget(self.rewards)
        self.b_done = W.button('Complete quest', T.G['check'], self.complete, accent=True)
        d.body.addWidget(self.b_done)
        self.b_active = W.button('Mark in progress', T.G['play'], self.start, flat=True)
        self.b_reset = W.button('Mark not started', T.G['undo'], self.reset, flat=True)
        self.b_reset.setToolTip('Only the state changes; what the quest already gave stays. Use Undo to take it back.')
        d.body.addLayout(W.hbox(self.b_active, self.b_reset, spacing=6))
        body.addWidget(d)
        root.addLayout(body, 1)

        self.note = W.label('Titles of Pokémon requests come from the game files. Other quests have no title in the '
                            'game files; the Withered Wasteland ones show names a player (MrGrangerplays) mapped while '
                            'playing, which may be off.', 'small', wrap=True)
        root.addWidget(self.note)
        self.state_chips[self.state].setChecked(True)
        self.tiles[0].set_selected(True)
        self.current = []   # quests shown in the detail panel; kept when an edit moves them out of the list

    # ---------- filters ----------
    def set_area(self, n):
        self.area = 0 if n == self.area else n
        for k, t in enumerate(self.tiles):
            t.set_selected(k == self.area)
        self.fill()

    def set_state(self, key):
        self.state = key
        for k, ch in self.state_chips.items():
            ch.setChecked(k == key)
        self.fill()

    def set_gate(self, on):
        self.app.adv_unlocked = on
        for p in self.app.pages.values():
            if p is not self:
                p.dirty = True
        self.show_detail()

    # ---------- state ----------
    def refresh(self):
        self.gate.toggle.set_quiet(self.app.adv_unlocked)
        c = self.c
        if not c:
            return
        tot = [0, 0, 0]
        for n, (lo, hi, _) in enumerate(ps.QUEST_AREAS, 1):
            ids = [q for q in ps.QUESTS if lo <= q <= hi]
            done = sum(c.quest_state(q) == ps.QUEST_DONE for q in ids)
            open_ = sum(c.quest_state(q) in OPEN for q in ids)
            self.tiles[n].set_counts(done, len(ids), open_)
            tot = [tot[0] + done, tot[1] + len(ids), tot[2] + open_]
        self.tiles[0].set_counts(*tot)
        for key, label, states in STATE_FILTERS:
            n = sum(c.quest_state(q) in states for q in ps.QUESTS)
            self.state_chips[key].setText(f'{label}  {n}')
        self.fill()

    def matches(self, q, text):
        if not text:
            return True
        if text.lstrip('#') == str(q):
            return True
        hay = ' '.join((ps.quest_name(q), ps.quest_area(q), ps.quest_type(q), ps.quest_summary(q),
                        ' '.join(ps.describe_effect(k, v) for k, v in ps.quest_effects(q) if k != 'other'))).lower()
        return all(w in hay for w in text.split())

    def fill(self):
        c = self.c
        if not c:
            return
        states = dict((k, s) for k, _, s in STATE_FILTERS)[self.state]
        areas = ps.QUEST_AREAS if not self.area else [ps.QUEST_AREAS[self.area - 1]]
        text = self.q.text().strip().lower()
        keep = set(self.current)
        scroll = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        shown = []
        for lo, hi, name in areas:
            rows = [(q, c.quest_state(q)) for q in sorted(ps.QUESTS) if lo <= q <= hi]
            rows = [(q, st) for q, st in rows if st in states and self.matches(q, text)]
            if not rows:
                continue
            if len(areas) > 1:
                h = QListWidgetItem()
                h.setData(Qt.UserRole, (HEAD, name, f'{len(rows)} quest{"s" if len(rows) != 1 else ""}'))
                h.setFlags(Qt.NoItemFlags)
                self.list.addItem(h)
            for q, st in rows:
                it = QListWidgetItem()
                it.setData(Qt.UserRole, (ROW, q, st))
                it.setToolTip(f'Quest {q}: {quest_title(q)}')
                self.list.addItem(it)
                if q in keep:
                    it.setSelected(True)
                shown.append(q)
        self.list.blockSignals(False)
        self.list.verticalScrollBar().setValue(scroll)
        self.shown = shown
        has = bool(shown)
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            where = 'here' if self.area else 'anywhere'
            self.empty.setText(f'No quests match "{self.q.text().strip()}".' if text else
                               f'Nothing in progress {where}.\nEvery quest you have started is finished.'
                               if self.state == 'open' else 'No quests in this list.')
        self.show_detail()

    def selected(self):
        return [it.data(Qt.UserRole)[1] for it in self.list.selectedItems() if it.data(Qt.UserRole)[0] == ROW]

    def on_select(self):
        self.current = self.selected()
        self.show_detail()

    # ---------- detail panel ----------
    def saved_state(self, q):
        """State in the file as opened, to tell edits made here apart from the game's own progress."""
        return struct.unpack_from('<H', self.c.orig_data, ps.QUEST_OFS + 2 * q)[0]

    def show_detail(self):
        c, ids = self.c, list(self.current)
        live = self.unlocked
        self.lock.setVisible(not live)
        for w in (self.rewards, self.b_done, self.b_active, self.b_reset):
            w.setVisible(live)
        if not c or not ids:
            self.d_kind.setText('')
            self.d_title.setText('Select a quest')
            self.d_sub.setText('Pick one from the list to see where it stands and what it gives.'
                               if self.shown else '')
            for w in (self.d_gives_h, self.d_gives, self.d_left_h, self.d_left):
                w.setVisible(False)
            for b in (self.b_done, self.b_active, self.b_reset):
                b.setEnabled(False)
            return
        states = [c.quest_state(q) for q in ids]
        rewards = self.rewards.toggle.isChecked()
        if len(ids) == 1:
            q, st = ids[0], states[0]
            src = ps.quest_name_source(q)
            self.d_kind.setText(f'{ps.quest_type(q).upper()}  ·  #{q}')
            self.d_title.setText(quest_title(q))
            note = {'game': '', 'player': ' Name mapped by a player, may be off.',
                    '': ' The game files give this step no title.'}[src]
            was = self.saved_state(q)
            edited = (f'<br><span style="color:{T.P["warn"]}">Changed here from {state_text(was).lower()}: '
                      'save to keep it, or Undo.</span>') if was != st else ''
            self.d_sub.setText(f'{ps.quest_area(q)}  ·  <span style="color:{T.P[state_key(st)]}">'
                               f'{state_text(st)}</span>.{note}{edited}')
            self.d_sub.setTextFormat(Qt.RichText)
        else:
            self.d_kind.setText(f'{len(ids)} QUESTS')
            self.d_title.setText(f'{len(ids)} quests selected')
            counts = {s: states.count(s) for s in set(states)}
            self.d_sub.setText(',  '.join(f'{n} {state_text(s).lower()}' for s, n in sorted(counts.items())))
            self.d_sub.setTextFormat(Qt.PlainText)
        # what completing gives (start commands too, for quests that have not started)
        moves, recipes, flags, left = [], [], [], 0
        for q, st in zip(ids, states):
            if st == ps.QUEST_DONE:
                continue
            eff = (ps.quest_effects(q, 'start') if st < ps.QUEST_ACTIVE else []) + ps.quest_effects(q)
            for k, v in eff:
                if k == 'other':
                    left += 1
                elif k == 'move' and v in ps.PUBLIC_SKILLS:
                    moves.append(f'Learn <b>{ps.name_of(ps.SKILL_NAMES, v, "move")}</b>')
                elif k == 'recipe':
                    recipes.append(f'Crafting recipe: <b>{ps.describe_effect(k, v)[7:]}</b>')
                elif k in ('flag', 'unflag'):
                    label = ps.KNOWN_FLAGS.get(v)
                    flags.append(f'Story flag {v} {"on" if k == "flag" else "off"}' + (f' ({label})' if label else ''))
                else:
                    left += 1
        all_done = all(s == ps.QUEST_DONE for s in states)
        self.d_gives_h.setVisible(True)
        self.d_gives.setVisible(True)
        if all_done:
            by_game = all(self.saved_state(q) == ps.QUEST_DONE for q in ids)
            self.d_gives_h.setText('DONE')
            self.d_gives.setText(('The game finished ' if by_game else 'Completed here. Nothing more to give for ')
                                 + ('this quest.' if len(ids) == 1 else 'these quests.'))
        elif not rewards:
            self.d_gives_h.setText('COMPLETING IT HERE')
            self.d_gives.setText('Only the state changes to Done (rewards switched off below).')
        else:
            self.d_gives_h.setText('COMPLETING IT HERE GIVES')
            uniq = list(dict.fromkeys(moves + recipes + flags))
            self.d_gives.setText('<br>'.join(f'•&nbsp; {g}' for g in uniq[:10])
                                 + (f'<br>… and {len(uniq) - 10} more' if len(uniq) > 10 else '')
                                 if uniq else 'Nothing the editor can give: only the state changes.')
        self.d_left_h.setVisible(not all_done and left > 0)
        self.d_left.setVisible(not all_done and left > 0)
        self.d_left.setText(f'{left} step{"s" if left != 1 else ""} only the game can carry out, such as a resident '
                            'moving in, a building or a scene. Completing the quest here skips '
                            f'{"it" if left == 1 else "them"}.')
        self.b_done.setText('Complete quest' if len(ids) == 1 else f'Complete {len(ids)} quests')
        self.b_done.setEnabled(live and not all_done)
        self.b_active.setEnabled(live and any(s != ps.QUEST_ACTIVE for s in states))
        self.b_reset.setEnabled(live and any(s != ps.QUEST_NOT_STARTED for s in states))

    # ---------- edits ----------
    def _what(self, ids):
        return f'quest {ids[0]} ({quest_title(ids[0])})' if len(ids) == 1 else f'{len(ids)} quests'

    def _ready(self):
        if not self.app.need():
            return None
        if not self.unlocked:
            self.app.toast('Switch on "Let me edit quests" first.', 'err')
            return None
        return list(self.current) or None

    def complete(self):
        ids = self._ready()
        if not ids:
            return
        rewards = self.rewards.toggle.isChecked()
        left = []

        def go():
            for q in ids:
                left.extend(self.c.complete_quest(q, rewards))
        if self.app.do(f'Complete {self._what(ids)}', go) and left:
            self.app.toast(f'Done. {len(left)} step{"s" if len(left) > 1 else ""} only the game can do '
                           f'{"was" if len(left) == 1 else "were"} skipped. Ctrl+Z undoes it.', 'info')

    def start(self):
        ids = self._ready()
        if ids:
            self.app.do(f'Mark {self._what(ids)} in progress', lambda: [self.c.start_quest(q) for q in ids])

    def reset(self):
        ids = self._ready()
        if ids:
            self.app.do(f'Mark {self._what(ids)} not started',
                        lambda: [self.c.set_quest_state(q, ps.QUEST_NOT_STARTED) for q in ids])
