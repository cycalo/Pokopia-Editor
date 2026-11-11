from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QMenu, QVBoxLayout, QWidget

import pokopia_save as ps
from gui import theme as T
from gui import widgets as W
from gui.pages.base import Page
from gui.tiles import IconTile, RadialWheel, SlotGrid

MOVE_MIME = 'application/x-pokopia-move'
EMOTE_MIME = 'application/x-pokopia-emote'


def move_name(i):
    return ps.name_of(ps.SKILL_NAMES, i, 'Move')


def emote_name(i):
    return ps.name_of(ps.REACTION_NAMES, i, 'Emote')


class MovesPage(Page):
    title, nav, glyph = 'Moves & Emotes', 'Moves & Emotes', T.G['smile']
    subtitle = 'Learn moves and emotes, unlock extras, arrange both wheels'
    scrollable = True

    def build(self):
        a = self.app
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(14)
        top = QHBoxLayout()
        top.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        # moves
        mc = W.Card('Moves', 'Click a move to learn or unlearn it. Unlearning also switches off its extras.', T.G['play'])
        g = QGridLayout()
        g.setSpacing(8)
        self.move_t = {}
        for n, i in enumerate(ps.PUBLIC_SKILLS):
            t = IconTile(move_name(i), lambda s, i=i: a.assets.skill(i, s), style='h', size=(None, 64),
                         mime=MOVE_MIME if i in ps.WHEEL_SKILLS else None, payload=i)
            t.clicked.connect(lambda i=i: self.toggle_move(i))
            g.addWidget(t, n // 2, n % 2)
            self.move_t[i] = t
        mc.body.addLayout(g)
        mc.body.addWidget(W.label('Learning or unlearning moves against the story can confuse quests. '
                                  'Undo works until you save.', 'small', wrap=True))
        left.addWidget(mc)
        ex = W.Card('Move extras', 'Food boosts and upgrades. Each one needs its move first.', T.G['star'])
        eg = QGridLayout()
        eg.setHorizontalSpacing(28)
        eg.setVerticalSpacing(4)
        self.extra_w = {}
        for n, (key, (label, _, _, _)) in enumerate(ps.EXTRAS.items()):
            row = W.ToggleRow(label)
            row.toggle.toggled.connect(lambda on, k=key: self.toggle_extra(k, on))
            eg.addWidget(row, n // 2, n % 2)
            self.extra_w[key] = row
        ex.body.addLayout(eg)
        left.addWidget(ex)
        left.addStretch(1)
        top.addLayout(left, 1)
        right = QVBoxLayout()
        right.setSpacing(14)
        wc = W.Card('Move wheel', 'Drag a learned move onto a slot, or click a slot.', T.G['refresh'])
        self.wheel = RadialWheel(ps.SKILL_WHEEL_COUNT, MOVE_MIME, lambda v, s: a.assets.skill(v, s), move_name, size=290)
        self.wheel.slot_clicked.connect(self.wheel_menu)
        self.wheel.slot_dropped.connect(self.set_wheel)
        wc.body.addWidget(self.wheel, 0, Qt.AlignHCenter)
        right.addWidget(wc)
        rw = W.Card('Emote wheel', '24 slots. Drag a learned emote onto a slot, or click a slot.', T.G['refresh'])
        self.rwheel = SlotGrid(ps.REACT_WHEEL_COUNT, 4, EMOTE_MIME, lambda v, s: a.assets.reaction(v, s), emote_name, tile=64)
        self.rwheel.slot_clicked.connect(self.rwheel_menu)
        self.rwheel.slot_dropped.connect(self.set_rwheel)
        rw.body.addWidget(self.rwheel, 0, Qt.AlignHCenter)
        right.addWidget(rw)
        right.addStretch(1)
        rwid = QWidget()
        rwid.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        rwid.setFixedWidth(340)
        top.addWidget(rwid, 0, Qt.AlignTop)
        lay.addLayout(top)
        # emotes
        ec = W.Card('Emotes', '', T.G['smile'])
        self.em_count = ec
        ec.actions.addWidget(W.button('Learn all', T.G['check'], self.learn_all, accent=True))
        holder = QWidget()
        flow = W.FlowLayout(holder, 8, 8)
        self.em_t = {}
        for i in ps.PUBLIC_REACTIONS:
            t = IconTile(emote_name(i), lambda s, i=i: a.assets.reaction(i, s), style='v', size=(98, 98),
                         mime=EMOTE_MIME, payload=i)
            t.clicked.connect(lambda i=i: self.toggle_emote(i))
            flow.addWidget(t)
            self.em_t[i] = t
        ec.body.addWidget(holder)
        lay.addWidget(ec)
        lay.addStretch(1)

    def refresh(self):
        c = self.c
        if not c:
            return
        for i, t in self.move_t.items():
            u, learned = c.skill(i)
            note = f'used {u:,}×' if u else 'never used'
            if not learned:
                note = 'not learned · click to learn'
            t.set_state(learned, note, tip=f'{move_name(i)}: {"learned" if learned else "not learned"}. '
                        + ('Drag onto the wheel to place it.' if learned and i in ps.WHEEL_SKILLS else
                           'This move does not go on the wheel.' if i not in ps.WHEEL_SKILLS else 'Click to learn.'))
        for key, row in self.extra_w.items():
            on = c.extra(key)
            block = '' if on else c.extra_blocker(key)
            row.toggle.set_quiet(on)
            row.toggle.setEnabled(not block)
            row.set_note(block)
        self.wheel.set_values(c.wheel())
        learned = [i for i in ps.PUBLIC_REACTIONS if c.reaction_learned(i)]
        self.em_count.set_subtitle(f'{len(learned)} of {len(ps.PUBLIC_REACTIONS)} learned. Click to learn or unlearn; '
                                   'drag a learned one onto the wheel.')
        for i, t in self.em_t.items():
            t.set_state(i in learned, tip=f'{emote_name(i)}: {"learned" if i in learned else "click to learn"}')
        self.rwheel.set_values(c.reaction_wheel())

    def toggle_move(self, i):
        if not self.app.need():
            return
        if self.c.skill(i)[1]:
            self.app.do(f'Unlearn {move_name(i)}', lambda: self.c.forget_skill(i))
        else:
            self.app.do(f'Learn {move_name(i)}', lambda: self.c.learn_skill(i))

    def toggle_extra(self, key, on):
        if self.app.need():
            self.app.do(f'{ps.EXTRAS[key][0]} {"on" if on else "off"}', lambda: self.c.set_extra(key, on))

    def set_wheel(self, k, move):
        self.app.do(f'Move wheel slot {k + 1}: {move_name(move) if move else "empty"}', lambda: self.c.set_skill_slot(k, move))

    def wheel_menu(self, k, pos):
        c = self.c
        m = QMenu(self)
        for i in ps.WHEEL_SKILLS:
            if c.skill(i)[1]:
                act = m.addAction(QIcon(self.app.assets.skill(i, 22)), move_name(i), lambda i=i: self.set_wheel(k, i))
                act.setCheckable(True)
                act.setChecked(c.wheel()[k] == i)
        if m.isEmpty():
            m.addAction('Learn a move first').setEnabled(False)
        m.addSeparator()
        m.addAction(T.glyph_icon(T.G['close']), 'Empty slot', lambda: self.set_wheel(k, 0))
        m.exec(pos)

    def toggle_emote(self, i):
        if not self.app.need():
            return
        if self.c.reaction_learned(i):
            self.app.do(f'Unlearn emote {emote_name(i)}', lambda: self.c.forget_reaction(i))
        else:
            self.app.do(f'Learn emote {emote_name(i)}', lambda: self.c.learn_reaction(i))

    def learn_all(self):
        if self.app.need():
            self.app.do('Learn all emotes', lambda: [self.c.learn_reaction(i) for i in ps.PUBLIC_REACTIONS])

    def set_rwheel(self, k, emote):
        self.app.do(f'Emote wheel slot {k + 1}: {emote_name(emote) if emote else "empty"}',
                    lambda: self.c.set_reaction_slot(k, emote))

    def rwheel_menu(self, k, pos):
        c = self.c
        m = QMenu(self)
        learned = [i for i in ps.PUBLIC_REACTIONS if c.reaction_learned(i)]
        cur = c.reaction_wheel()[k]
        for i in learned:
            act = m.addAction(QIcon(self.app.assets.reaction(i, 22)), emote_name(i), lambda i=i: self.set_rwheel(k, i))
            act.setCheckable(True)
            act.setChecked(cur == i)
        if not learned:
            m.addAction('Learn an emote first').setEnabled(False)
        m.addSeparator()
        m.addAction(T.glyph_icon(T.G['close']), 'Empty slot', lambda: self.set_rwheel(k, 0))
        m.exec(pos)
