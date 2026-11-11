"""Previous Tkinter GUI of the Pokopia save editor, kept as a fallback for when PySide6 is not installed.

  pythonw legacy/pokopia_gui_tk.py [SAVE_FOLDER] [--theme dark|light] [--screenshot DIR]
"""
import ctypes, datetime, json, math, os, queue, sys, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import pokopia_save as ps
import pokopia_extras as px

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = ImageDraw = ImageTk = None

SETTINGS = os.path.join(HERE, 'settings.json')
FONT = 'Segoe UI'

PALETTES = {
    'dark': dict(bg='#12151c', panel='#181c26', card='#202533', line='#30384a', text='#e7eaf0', muted='#8d96a8',
                 accent='#4fc98e', accent2='#3fae79', onaccent='#07130c', sel='#2a3a57', danger='#ef6b66',
                 warn='#e7b052', cell='#272d3d', cellhi='#343c50'),
    'light': dict(bg='#eef1f5', panel='#e3e7ee', card='#ffffff', line='#cfd6e1', text='#1b2230', muted='#667085',
                  accent='#1a9a5f', accent2='#15804e', onaccent='#ffffff', sel='#d3e4ff', danger='#c93c37',
                  warn='#a86b00', cell='#f1f4f8', cellhi='#e2e8f1'),
}


def apply_theme(root, P):
    st = ttk.Style(root)
    st.theme_use('clam')
    st.configure('.', background=P['bg'], foreground=P['text'], font=(FONT, 10), bordercolor=P['line'],
                 darkcolor=P['bg'], lightcolor=P['bg'], troughcolor=P['cell'], focuscolor=P['accent'],
                 selectbackground=P['sel'], selectforeground=P['text'], insertcolor=P['text'], fieldbackground=P['cell'])
    for pre, bg in (('', P['bg']), ('C.', P['card']), ('S.', P['panel'])):
        st.configure(pre + 'TFrame', background=bg)
        st.configure(pre + 'TLabel', background=bg, foreground=P['text'])
        st.configure(pre + 'Muted.TLabel', background=bg, foreground=P['muted'], font=(FONT, 9))
        st.configure(pre + 'H.TLabel', background=bg, foreground=P['text'], font=(FONT, 11, 'bold'))
        st.configure(pre + 'Big.TLabel', background=bg, foreground=P['text'], font=(FONT, 19, 'bold'))
        st.configure(pre + 'Accent.TLabel', background=bg, foreground=P['accent'], font=(FONT, 10, 'bold'))
        st.configure(pre + 'Warn.TLabel', background=bg, foreground=P['warn'])
        st.configure(pre + 'TCheckbutton', background=bg, foreground=P['text'], indicatorbackground=P['cell'],
                     indicatorforeground=P['onaccent'])
        st.map(pre + 'TCheckbutton', background=[('active', bg)], foreground=[('disabled', P['muted'])],
               indicatorbackground=[('selected', P['accent']), ('!selected', P['cell'])])
    st.configure('H1.TLabel', font=(FONT, 17, 'bold'))
    st.configure('S.Title.TLabel', font=(FONT, 13, 'bold'), foreground=P['accent'], background=P['panel'])
    st.configure('TButton', background=P['cell'], foreground=P['text'], bordercolor=P['line'], padding=(10, 5),
                 relief='flat', focusthickness=0, lightcolor=P['cell'], darkcolor=P['cell'])
    st.map('TButton', background=[('disabled', P['cell']), ('pressed', P['sel']), ('active', P['cellhi'])],
           foreground=[('disabled', P['muted'])], lightcolor=[('active', P['cellhi'])], darkcolor=[('active', P['cellhi'])])
    st.configure('Accent.TButton', background=P['accent'], foreground=P['onaccent'], bordercolor=P['accent'],
                 lightcolor=P['accent'], darkcolor=P['accent'], font=(FONT, 10, 'bold'))
    st.map('Accent.TButton', background=[('disabled', P['line']), ('active', P['accent2'])],
           foreground=[('disabled', P['muted'])], lightcolor=[('disabled', P['line']), ('active', P['accent2'])],
           darkcolor=[('disabled', P['line']), ('active', P['accent2'])], bordercolor=[('disabled', P['line'])])
    st.configure('Danger.TButton', foreground=P['danger'])
    st.configure('Small.TButton', padding=(7, 2), font=(FONT, 9))
    st.configure('Nav.TButton', background=P['panel'], bordercolor=P['panel'], lightcolor=P['panel'],
                 darkcolor=P['panel'], anchor='w', padding=(16, 9), font=(FONT, 10))
    st.map('Nav.TButton', background=[('active', P['cell'])], lightcolor=[('active', P['cell'])],
           darkcolor=[('active', P['cell'])])
    st.configure('NavSel.TButton', background=P['sel'], bordercolor=P['sel'], lightcolor=P['sel'], darkcolor=P['sel'],
                 foreground=P['accent'], anchor='w', padding=(16, 9), font=(FONT, 10, 'bold'))
    st.map('NavSel.TButton', background=[('active', P['sel'])], lightcolor=[('active', P['sel'])],
           darkcolor=[('active', P['sel'])])
    st.configure('Chip.TButton', padding=(6, 3), font=(FONT, 9))
    st.configure('ChipOn.TButton', padding=(6, 3), font=(FONT, 9, 'bold'), background=P['sel'], lightcolor=P['sel'],
                 darkcolor=P['sel'])
    st.map('ChipOn.TButton', background=[('disabled', P['sel'])], foreground=[('disabled', P['accent']), ('!disabled', P['accent'])])
    for w in ('TEntry', 'TSpinbox', 'TCombobox'):
        st.configure(w, fieldbackground=P['cell'], foreground=P['text'], bordercolor=P['line'], background=P['cell'],
                     arrowcolor=P['text'], padding=4, lightcolor=P['cell'], darkcolor=P['cell'])
        st.map(w, bordercolor=[('focus', P['accent'])], foreground=[('disabled', P['muted'])],
               fieldbackground=[('readonly', P['cell']), ('disabled', P['bg'])])
    st.map('TCombobox', selectbackground=[('readonly', P['cell'])], selectforeground=[('readonly', P['text'])],
           foreground=[('readonly', P['text']), ('disabled', P['muted'])])
    for k, v in (('background', P['card']), ('foreground', P['text']), ('selectBackground', P['sel']),
                 ('selectForeground', P['text'])):
        root.option_add('*TCombobox*Listbox.' + k, v)
    st.configure('Treeview', background=P['card'], fieldbackground=P['card'], foreground=P['text'],
                 bordercolor=P['line'], rowheight=28, borderwidth=0, lightcolor=P['card'], darkcolor=P['card'])
    st.map('Treeview', background=[('selected', P['sel'])], foreground=[('selected', P['text'])])
    st.configure('Treeview.Heading', background=P['panel'], foreground=P['muted'], relief='flat', padding=(6, 5),
                 font=(FONT, 9, 'bold'), lightcolor=P['panel'], darkcolor=P['panel'], bordercolor=P['panel'])
    st.map('Treeview.Heading', background=[('active', P['cell'])])
    st.configure('Big.Treeview', rowheight=40)
    st.configure('TScrollbar', background=P['line'], troughcolor=P['bg'], bordercolor=P['bg'], arrowcolor=P['muted'],
                 relief='flat', lightcolor=P['line'], darkcolor=P['line'])
    st.map('TScrollbar', background=[('active', P['muted'])])
    st.configure('Horizontal.TScale', background=P['accent'], troughcolor=P['cell'], lightcolor=P['cell'],
                 darkcolor=P['cell'], bordercolor=P['line'])
    st.configure('TSeparator', background=P['line'])


def dark_titlebar(win, dark):
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


class Images:
    """PhotoImage cache for item icons and resident portraits."""

    def __init__(self):
        self.icons = px.Icons()
        self.cache = {}
        self.ok = self.icons.available and ImageTk is not None

    def _load(self, path, size):
        if not path or not self.ok:
            return None
        key = (path, size)
        if key not in self.cache:
            try:
                im = Image.open(path).convert('RGBA')
                bb = im.getchannel('A').getbbox()  # sprites sit in a lot of empty space
                if bb:
                    im = im.crop(bb)
                f = min(size / im.width, size / im.height, 3.0)
                im = im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)
                box = Image.new('RGBA', (size, size), (0, 0, 0, 0))
                box.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
                self.cache[key] = ImageTk.PhotoImage(box)
            except Exception:
                self.cache[key] = None
        return self.cache[key]

    def item(self, item_id, size):
        return self._load(self.icons.item_path(item_id), size)

    def villager(self, index, size):
        return self._load(self.icons.villager_path(index), size)


class Tip:
    """Tooltip. `text` may be a string or a function(event) -> string (for canvases)."""

    def __init__(self, widget, text):
        self.w, self.text, self.win, self.job, self.cur = widget, text, None, None, None
        widget.bind('<Enter>', self._move, add='+')
        widget.bind('<Motion>', self._move, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _move(self, e):
        t = self.text(e) if callable(self.text) else self.text
        if t == self.cur and (self.win or self.job):
            return
        self._hide()
        self.cur = t
        if t:
            self.job = self.w.after(450, lambda: self._show(t, e.x_root, e.y_root))

    def _show(self, t, x, y):
        self.job = None
        self.win = tk.Toplevel(self.w)
        self.win.wm_overrideredirect(True)
        self.win.attributes('-topmost', True)
        tk.Label(self.win, text=t, bg='#fff8d6', fg='#222', bd=1, relief='solid', font=(FONT, 9), padx=6, pady=3,
                 justify='left', wraplength=360).pack()
        self.win.geometry(f'+{x + 14}+{y + 16}')

    def _hide(self, e=None):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
        if self.win:
            self.win.destroy()
            self.win = None
        self.cur = None


def scrolled(parent, widget_factory, **grid):
    """Frame holding a widget plus a vertical scrollbar. Returns (frame, widget)."""
    f = ttk.Frame(parent)
    w = widget_factory(f)
    sb = ttk.Scrollbar(f, orient='vertical', command=w.yview)
    w.configure(yscrollcommand=sb.set)
    w.pack(side='left', fill='both', expand=True)
    sb.pack(side='left', fill='y')
    return f, w


class Page(ttk.Frame):
    title = ''
    nav = ''

    def __init__(self, app):
        super().__init__(app.content)
        self.app, self.P, self.dirty = app, app.P, True
        self.build()

    @property
    def c(self):
        return self.app.save.common if self.app.save else None

    def card(self, parent, title=None, **pad):
        f = ttk.Frame(parent, style='C.TFrame', padding=pad.get('padding', 12))
        if title:
            ttk.Label(f, text=title, style='C.H.TLabel').pack(anchor='w', pady=(0, 6))
        return f

    def build(self): pass
    def refresh(self): pass
    def focus_search(self): pass


# ============================================================ Overview
class OverviewPage(Page):
    title, nav = 'Overview', 'Overview'
    STATS = ['Player', 'Play time', 'Residents', 'Bag', 'Moves', 'Emotes', 'Islands', 'Photos']

    def build(self):
        grid = ttk.Frame(self)
        grid.pack(fill='x')
        self.val, self.sub = {}, {}
        for n, name in enumerate(self.STATS):
            f = ttk.Frame(grid, style='C.TFrame', padding=14)
            f.grid(row=n // 4, column=n % 4, sticky='nsew', padx=(0, 10), pady=(0, 10))
            grid.columnconfigure(n % 4, weight=1, uniform='s')
            ttk.Label(f, text=name.upper(), style='C.Muted.TLabel').pack(anchor='w')
            self.val[name] = tk.StringVar(value='-')
            self.sub[name] = tk.StringVar()
            ttk.Label(f, textvariable=self.val[name], style='C.Big.TLabel').pack(anchor='w')
            ttk.Label(f, textvariable=self.sub[name], style='C.Muted.TLabel').pack(anchor='w')
        row = ttk.Frame(self)
        row.pack(fill='both', expand=True)
        row.columnconfigure(0, weight=1, uniform='o')
        row.columnconfigure(1, weight=1, uniform='o')
        row.rowconfigure(0, weight=1)
        left = ttk.Frame(row)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        c = self.card(left, 'Player name')
        c.pack(fill='x', pady=(0, 10))
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x')
        self.name = tk.StringVar()
        e = ttk.Entry(r, textvariable=self.name, width=28)
        e.pack(side='left')
        e.bind('<Return>', lambda ev: self.apply_name())
        ttk.Button(r, text='Rename', command=self.apply_name).pack(side='left', padx=8)
        ttk.Label(c, text='Up to 24 UTF-8 bytes. Every copy of the name in the save is updated.', style='C.Muted.TLabel').pack(anchor='w', pady=(6, 0))
        c = self.card(left, 'Save folder')
        c.pack(fill='both', expand=True)
        self.info = tk.StringVar()
        ttk.Label(c, textvariable=self.info, style='C.TLabel', justify='left', wraplength=440).pack(anchor='w')
        self.emu = ttk.Label(c, text='', style='C.Muted.TLabel', wraplength=440, justify='left')
        self.emu.pack(anchor='w', pady=(8, 0))
        r = ttk.Frame(c, style='C.TFrame'); r.pack(anchor='w', pady=(10, 0))
        ttk.Button(r, text='Open in Explorer', command=lambda: self.app.save and os.startfile(self.app.save.folder)).pack(side='left')
        ttk.Button(r, text='Reload from disk', command=self.app.reload).pack(side='left', padx=8)
        c = self.card(row, 'Pending changes')
        c.grid(row=0, column=1, sticky='nsew')
        self.count = tk.StringVar()
        ttk.Label(c, textvariable=self.count, style='C.Muted.TLabel').pack(anchor='w')
        fr, self.hist = scrolled(c, lambda p: tk.Listbox(p, bg=self.P['cell'], fg=self.P['text'], bd=0, highlightthickness=0,
                                                         selectbackground=self.P['sel'], selectforeground=self.P['text'],
                                                         activestyle='none', font=(FONT, 10)))
        fr.pack(fill='both', expand=True, pady=8)
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x')
        ttk.Button(r, text='Undo  Ctrl+Z', command=self.app.undo).pack(side='left')
        ttk.Button(r, text='Redo  Ctrl+Y', command=self.app.redo).pack(side='left', padx=8)
        ttk.Button(r, text='Review all changes', command=self.app.review).pack(side='right')

    def apply_name(self):
        if self.app.need():
            self.app.do('Rename player', lambda: setattr(self.c, 'player_name', self.name.get()))

    def refresh(self):
        c, app = self.c, self.app
        if not c:
            return
        self.name.set(c.player_name)
        vs = [c.get_villager(i) for i in c.villagers()]
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(c.path))
        self.val['Player'].set(c.player_name)
        self.sub['Player'].set(f'saved {mt:%d %b %Y %H:%M}')
        pt = c.play_seconds
        self.val['Play time'].set(ps.fmt_playtime(pt) if pt is not None else '-')
        self.sub['Play time'].set('read from the save')
        self.val['Residents'].set(str(len(vs)))
        self.sub['Residents'].set(f'{sum(v["friendship"] >= ps.FRIENDSHIP_MAX for v in vs)} at max friendship')
        self.val['Bag'].set(str(len(c.filled_slots())))
        self.sub['Bag'].set(f'of {ps.INV_COUNT} slots filled')
        self.val['Moves'].set(str(sum(c.skill(i)[1] for i in ps.PUBLIC_SKILLS)))
        self.sub['Moves'].set(f'of {len(ps.PUBLIC_SKILLS)} learned, {sum(c.extra(k) for k in ps.EXTRAS)} extras')
        self.val['Emotes'].set(str(sum(c.reaction_learned(i) for i in ps.PUBLIC_REACTIONS)))
        self.sub['Emotes'].set(f'of {len(ps.PUBLIC_REACTIONS)} learned')
        st = app.save.stage_files()
        self.val['Islands'].set(str(len(st)))
        self.sub['Islands'].set(', '.join(ps.name_of(ps.AREA_NAMES, n, 'Area') for n in st)[:44])
        a = app.album
        self.val['Photos'].set(str(len(a)) if a is not None else ('...' if app.album_state == 'loading' else '-'))
        self.sub['Photos'].set('in the album' if a is not None else app.album_state)
        self.info.set(f'{app.save.folder}\n\nGame save version {ps.VERSION:#010x} (2.0.x). Only G00\\CMNDAT.BIN is ever written; '
                      'islands, photos and the game\'s own backup slot are copied untouched.')
        if app.emus:
            self.emu.configure(text=f'Emulator running: {", ".join(app.emus)}. Close it before overwriting the save.', style='C.Warn.TLabel')
        else:
            self.emu.configure(text='No emulator running. Safe to overwrite.', style='C.Muted.TLabel')
        h = c.history
        self.count.set(f'{len(h)} edit{"s" if len(h) != 1 else ""} not saved yet' if h else 'Nothing changed yet.')
        self.hist.delete(0, 'end')
        for n, label in enumerate(h, 1):
            self.hist.insert('end', f' {n}.  {label}')
        self.hist.see('end')


# ============================================================ Bag
class BagPage(Page):
    title, nav = 'Bag', 'Bag'
    CELL, GAP, COLS, X0 = 60, 6, 10, 10

    def build(self):
        self.sel, self.anchor, self.pick, self.drag = set(), None, 0, None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        P = self.P
        fr, self.cv = scrolled(self, lambda p: tk.Canvas(p, bg=P['bg'], highlightthickness=0, width=self.X0 * 2 + self.COLS * (self.CELL + self.GAP)))
        fr.grid(row=0, column=0, sticky='nsw')
        cv = self.cv
        cv.bind('<Button-1>', self.press)
        cv.bind('<ButtonRelease-1>', self.release)
        cv.bind('<Button-3>', self.menu)
        cv.bind('<Double-Button-1>', lambda e: self.search_entry.focus_set())
        cv.bind('<MouseWheel>', lambda e: cv.yview_scroll(-e.delta // 120, 'units'))
        Tip(cv, self.tip)
        side = ttk.Frame(self)
        side.grid(row=0, column=1, sticky='nsew', padx=(14, 0))
        self.columnconfigure(1, weight=1)
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)
        c = self.card(side)
        c.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.sel_icon = ttk.Label(c, style='C.TLabel')
        self.sel_icon.pack(side='left', padx=(0, 10))
        self.sel_text = tk.StringVar(value='Click a slot. Ctrl/Shift-click selects several, drag swaps two slots.')
        ttk.Label(c, textvariable=self.sel_text, style='C.TLabel', wraplength=300, justify='left').pack(side='left', fill='x')
        c = self.card(side, 'Item')
        c.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.q = tk.StringVar()
        self.search_entry = ttk.Entry(c, textvariable=self.q)
        self.search_entry.pack(fill='x')
        self.q.trace_add('write', lambda *a: self.search())
        fr, self.res = scrolled(c, lambda p: ttk.Treeview(p, show='tree', selectmode='browse', height=8))
        fr.pack(fill='both', expand=True, pady=(6, 0))
        self.res.bind('<<TreeviewSelect>>', self.pick_result)
        self.res.bind('<Double-Button-1>', lambda e: self.put())
        self.hint = ttk.Label(c, text='', style='C.Muted.TLabel')
        self.hint.pack(anchor='w', pady=(4, 0))
        c = self.card(side, 'Amount')
        c.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x')
        self.cnt = tk.StringVar(value='99')
        ttk.Spinbox(r, from_=1, to=255, textvariable=self.cnt, width=6).pack(side='left')
        for n in (1, 10, 50, 99, 255):
            ttk.Button(r, text=str(n), style='Small.TButton', width=4, command=lambda n=n: self.cnt.set(str(n))).pack(side='left', padx=(6, 0))
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x', pady=(10, 0))
        ttk.Button(r, text='Put in selected', style='Accent.TButton', command=self.put).pack(side='left')
        ttk.Button(r, text='Add to first empty', command=self.add).pack(side='left', padx=6)
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x', pady=(6, 0))
        ttk.Button(r, text='Set amount only', command=self.set_count).pack(side='left')
        ttk.Button(r, text='Clear  Del', style='Danger.TButton', command=self.clear).pack(side='left', padx=6)
        c = self.card(side, 'Whole bag')
        c.grid(row=3, column=0, sticky='ew')
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x')
        ttk.Button(r, text='Sort by ID', style='Small.TButton', command=lambda: self.app.do('Sort bag by ID', lambda: self.c.sort_main())).pack(side='left')
        ttk.Button(r, text='Sort A-Z', style='Small.TButton', command=lambda: self.app.do('Sort bag by name', lambda: self.c.sort_main(True))).pack(side='left', padx=6)
        ttk.Button(r, text='All stacks to amount', style='Small.TButton', command=self.fill_all).pack(side='left')
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x', pady=(6, 0))
        ttk.Button(r, text='Save preset...', style='Small.TButton', command=self.save_preset).pack(side='left')
        ttk.Button(r, text='Load preset...', style='Small.TButton', command=self.load_preset).pack(side='left', padx=6)
        self.search()

    # geometry
    def xy(self, i):
        step = self.CELL + self.GAP
        if i < ps.INV_MAIN:
            return self.X0 + (i % self.COLS) * step, 34 + (i // self.COLS) * step
        return self.X0 + (i - ps.INV_MAIN) * step, 34 + (ps.INV_MAIN // self.COLS) * step + 36

    def slot_at(self, e):
        x, y = self.cv.canvasx(e.x), self.cv.canvasy(e.y)
        for i in range(ps.INV_COUNT):
            sx, sy = self.xy(i)
            if sx <= x < sx + self.CELL and sy <= y < sy + self.CELL:
                return i
        return None

    def tip(self, e):
        i = self.slot_at(e)
        if i is None or not self.c:
            return None
        iid, cnt, _ = self.c.get_slot(i)
        return f'Slot {i}: {ps.item_name(iid)} x{cnt}  (ID {iid})' if iid else f'Slot {i}: empty'

    def refresh(self):
        c, cv, P = self.c, self.cv, self.P
        cv.delete('all')
        if not c:
            return
        S = self.CELL
        cv.create_text(self.X0, 16, text=f'MAIN BAG  ·  {sum(1 for i in range(ps.INV_MAIN) if c.get_slot(i)[0])} / {ps.INV_MAIN}', anchor='w', fill=P['muted'], font=(FONT, 9, 'bold'))
        bx, by = self.xy(ps.INV_MAIN)
        cv.create_text(self.X0, by - 16, text='SECOND BAR', anchor='w', fill=P['muted'], font=(FONT, 9, 'bold'))
        for i in range(ps.INV_COUNT):
            x, y = self.xy(i)
            iid, cnt, _ = c.get_slot(i)
            on = i in self.sel
            cv.create_rectangle(x, y, x + S, y + S, fill=P['sel'] if on else P['cell'] if iid else P['panel'],
                                outline=P['accent'] if on else P['line'], width=2 if on else 1)
            if not iid:
                continue
            img = self.app.images.item(iid, 44)
            if img:
                cv.create_image(x + S // 2, y + S // 2 - 2, image=img)
            else:
                cv.create_text(x + S // 2, y + S // 2 - 4, text=ps.item_name(iid), width=S - 6, fill=P['text'], font=(FONT, 7), justify='center')
            t = cv.create_text(x + S - 4, y + S - 3, text=str(cnt), anchor='se', fill=P['text'], font=(FONT, 9, 'bold'))
            bb = cv.bbox(t)
            cv.tag_lower(cv.create_rectangle(bb[0] - 2, bb[1], bb[2] + 2, bb[3], fill=P['card'], outline=''), t)
        cv.configure(scrollregion=(0, 0, self.X0 * 2 + self.COLS * (S + self.GAP), by + S + 14))
        self.sel = {s for s in self.sel if s < ps.INV_COUNT}
        self.show_selection()

    def show_selection(self):
        c = self.c
        if not self.sel:
            self.sel_icon.configure(image='')
            self.sel_text.set('Click a slot. Ctrl/Shift-click selects several, drag swaps two slots.')
        elif len(self.sel) == 1:
            i = next(iter(self.sel))
            iid, cnt, _ = c.get_slot(i)
            self.sel_icon.configure(image=self.app.images.item(iid, 56) or '')
            self.sel_text.set(f'Slot {i}\n{ps.item_name(iid)}' + (f'  x{cnt}\nItem ID {iid}' if iid else ''))
        else:
            self.sel_icon.configure(image='')
            self.sel_text.set(f'{len(self.sel)} slots selected ({sum(1 for s in self.sel if c.get_slot(s)[0])} filled)')

    # mouse
    def press(self, e):
        self.cv.focus_set()
        i = self.slot_at(e)
        self.drag = (i, e.x, e.y) if i is not None and not e.state & 0x5 else None
        if i is None:
            self.sel = set()
        elif e.state & 0x4:
            self.sel ^= {i}
            self.anchor = i
        elif e.state & 0x1 and self.anchor is not None:
            a, b = sorted((self.anchor, i))
            self.sel = set(range(a, b + 1))
        else:
            self.sel, self.anchor = {i}, i
        self.refresh()

    def release(self, e):
        if not self.drag or not self.c:
            return
        src, x, y = self.drag
        self.drag = None
        dst = self.slot_at(e)
        if dst is not None and dst != src and abs(e.x - x) + abs(e.y - y) > 10:
            self.sel, self.anchor = {dst}, dst
            self.app.do(f'Swap slots {src} and {dst}', lambda: self.c.swap_slots(src, dst))

    def menu(self, e):
        i = self.slot_at(e)
        if i is None or not self.c:
            return
        if i not in self.sel:
            self.sel, self.anchor = {i}, i
            self.refresh()
        P = self.P
        m = tk.Menu(self, tearoff=0, bg=P['card'], fg=P['text'], activebackground=P['sel'], activeforeground=P['text'], bd=0)
        m.add_command(label='Put chosen item here', command=self.put)
        m.add_command(label='Set amount to 99', command=lambda: (self.cnt.set('99'), self.set_count()))
        m.add_command(label='Copy into first empty slot', command=self.duplicate)
        m.add_separator()
        m.add_command(label='Select all filled slots', command=self.select_filled)
        m.add_command(label='Clear', command=self.clear)
        m.tk_popup(e.x_root, e.y_root)

    def select_filled(self):
        self.sel = set(self.c.filled_slots())
        self.refresh()

    # item search
    def search(self):
        q = self.q.get().strip().lower()
        self.res.delete(*self.res.get_children())
        hits = [(i, n) for i, n in enumerate(ps.ITEM_NAMES) if i and n.strip() and (q in n.lower() or q == str(i))]
        for i, n in hits[:120]:
            img = self.app.images.item(i, 24)
            self.res.insert('', 'end', iid=str(i), text=f'  {n}   #{i}', **({'image': img} if img else {}))
        self.hint.configure(text=f'{len(hits)} items' + (', showing the first 120. Type to narrow down.' if len(hits) > 120 else ''))

    def pick_result(self, e=None):
        s = self.res.selection()
        if s:
            self.pick = int(s[0])

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, 'end')

    # actions
    def amount(self):
        try:
            n = int(self.cnt.get())
        except ValueError:
            raise ValueError('Amount must be a number from 1 to 255')
        if not 1 <= n <= 255:
            raise ValueError('Amount must be 1-255')
        return n

    def put(self):
        if not self.app.need():
            return
        if not self.pick:
            return self.app.toast('Pick an item from the list first.', 'err')
        if not self.sel:
            return self.add()
        name, sel = ps.item_name(self.pick), sorted(self.sel)

        def go():
            n = self.amount()
            for s in sel:
                self.c.set_slot(s, self.pick, n)
        self.app.do(f'{name} x{self.cnt.get()} into {len(sel)} slot{"s" if len(sel) > 1 else ""}', go)

    def add(self):
        if not self.app.need():
            return
        if not self.pick:
            return self.app.toast('Pick an item from the list first.', 'err')
        box = []
        self.app.do(f'Add {ps.item_name(self.pick)} x{self.cnt.get()}', lambda: box.append(self.c.add_item(self.pick, self.amount())))
        if box:
            self.sel, self.anchor = {box[0]}, box[0]
            self.refresh()

    def set_count(self):
        sel = [s for s in sorted(self.sel) if self.c and self.c.get_slot(s)[0]]
        if not sel:
            return self.app.toast('Select at least one filled slot.', 'err')

        def go():
            n = self.amount()
            for s in sel:
                self.c.set_count(s, n)
        self.app.do(f'Amount {self.cnt.get()} for {len(sel)} slot{"s" if len(sel) > 1 else ""}', go)

    def fill_all(self):
        if not self.app.need():
            return

        def go():
            n = self.amount()
            for s in self.c.filled_slots():
                self.c.set_count(s, n)
        self.app.do(f'All stacks to {self.cnt.get()}', go)

    def clear(self):
        sel = [s for s in sorted(self.sel) if self.c and self.c.get_slot(s)[0]]
        if sel:
            self.app.do(f'Clear {len(sel)} slot{"s" if len(sel) > 1 else ""}', lambda: [self.c.set_slot(s, 0, 0) for s in sel])

    def duplicate(self):
        sel = [s for s in sorted(self.sel) if self.c.get_slot(s)[0]]
        if sel:
            self.app.do(f'Copy {len(sel)} slot{"s" if len(sel) > 1 else ""}', lambda: [self.c.add_item(*self.c.get_slot(s)[:2]) for s in sel])

    def save_preset(self):
        if not self.app.need():
            return
        f = filedialog.asksaveasfilename(title='Save bag preset', defaultextension='.json', filetypes=[('Bag preset', '*.json')],
                                         initialdir=HERE, initialfile='bag_preset.json')
        if f:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(self.c.export_bag(), fh, indent=1, ensure_ascii=False)
            self.app.toast(f'Preset saved: {f}')

    def load_preset(self):
        if not self.app.need():
            return
        f = filedialog.askopenfilename(title='Load bag preset', filetypes=[('Bag preset', '*.json')], initialdir=HERE)
        if not f:
            return
        try:
            with open(f, encoding='utf-8') as fh:
                entries = json.load(fh)
        except Exception as ex:
            return self.app.toast(f'Cannot read preset: {ex}', 'err')
        self.app.do(f'Load bag preset ({len(entries)} items)', lambda: self.c.import_bag(entries))


# ============================================================ Residents
class ResidentsPage(Page):
    title, nav = 'Residents', 'Residents'
    COLS = [('fr', 'Friendship', 150), ('thank', 'Thanks', 60), ('lvl', 'Gift lvl', 60), ('home', 'Home', 150), ('met', 'First met', 120)]

    def build(self):
        self.sort, self.rev = 'name', False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(top, text='Filter').pack(side='left')
        self.q = tk.StringVar()
        self.q_entry = ttk.Entry(top, textvariable=self.q, width=24)
        self.q_entry.pack(side='left', padx=8)
        self.q.trace_add('write', lambda *a: self.fill())
        ttk.Button(top, text=f'Max friendship for everyone ({ps.FRIENDSHIP_MAX})', command=self.max_all).pack(side='right')
        fr, self.tv = scrolled(self, lambda p: ttk.Treeview(p, columns=[c[0] for c in self.COLS], show='tree headings', style='Big.Treeview', selectmode='extended'))
        fr.grid(row=1, column=0, sticky='nsew')
        self.tv.heading('#0', text='Pokemon', anchor='w', command=lambda: self.sort_by('name'))
        self.tv.column('#0', width=190, minwidth=150)
        for key, text, w in self.COLS:
            self.tv.heading(key, text=text, anchor='w', command=lambda k=key: self.sort_by(k))
            self.tv.column(key, width=w, minwidth=50, anchor='w')
        self.tv.bind('<<TreeviewSelect>>', lambda e: self.show())
        d = self.card(self)
        d.grid(row=0, column=1, rowspan=2, sticky='ns', padx=(14, 0))
        self.portrait = ttk.Label(d, style='C.TLabel')
        self.portrait.pack()
        self.d_name = tk.StringVar(value='Select a resident')
        ttk.Label(d, textvariable=self.d_name, style='C.H.TLabel').pack(pady=(4, 0))
        self.d_sub = tk.StringVar()
        ttk.Label(d, textvariable=self.d_sub, style='C.Muted.TLabel').pack()
        ttk.Separator(d).pack(fill='x', pady=10)
        ttk.Label(d, text='Friendship', style='C.TLabel').pack(anchor='w')
        r = ttk.Frame(d, style='C.TFrame'); r.pack(fill='x', pady=(2, 0))
        self.fr = tk.IntVar()
        self.scale = ttk.Scale(r, from_=0, to=ps.FRIENDSHIP_MAX, orient='horizontal', length=170, command=lambda v: self.fr.set(round(float(v))))
        self.scale.pack(side='left')
        ttk.Spinbox(r, from_=0, to=ps.FRIENDSHIP_MAX, textvariable=self.fr, width=5, command=lambda: self.scale.set(self.fr.get())).pack(side='left', padx=(8, 0))
        r = ttk.Frame(d, style='C.TFrame'); r.pack(fill='x', pady=8)
        ttk.Button(r, text='Apply to selected', style='Accent.TButton', command=self.apply).pack(side='left')
        ttk.Button(r, text='Max', command=lambda: (self.fr.set(ps.FRIENDSHIP_MAX), self.apply())).pack(side='left', padx=6)
        self.talk = tk.BooleanVar()
        self.talk_cb = ttk.Checkbutton(d, text='Name conversation finished', variable=self.talk, style='C.TCheckbutton', command=self.set_talk)
        self.talk_cb.pack(anchor='w')
        ttk.Separator(d).pack(fill='x', pady=10)
        self.d_info = tk.StringVar()
        ttk.Label(d, textvariable=self.d_info, style='C.TLabel', justify='left', wraplength=280).pack(anchor='w')
        self.map_btn = ttk.Button(d, text='Show home on map', command=self.goto_map)
        self.map_btn.pack(anchor='w', pady=(10, 0))

    def focus_search(self):
        self.q_entry.focus_set()

    def sort_by(self, key):
        self.rev = not self.rev if self.sort == key else False
        self.sort = key
        self.fill()

    def refresh(self):
        self.fill()

    def fill(self):
        c = self.c
        if not c:
            return
        keep = set(self.tv.selection())
        self.tv.delete(*self.tv.get_children())
        q = self.q.get().strip().lower()
        rows = [c.get_villager(i) for i in c.villagers()]
        rows = [v for v in rows if q in v['name'].lower() or q in v['home_area_name'].lower()]
        key = {'name': lambda v: v['name'].lower(), 'fr': lambda v: v['friendship'], 'thank': lambda v: v['thank_points'],
               'lvl': lambda v: v['present_level'], 'home': lambda v: v['home_area_name'],
               'met': lambda v: v['met'] or datetime.datetime.min}[self.sort]
        rows.sort(key=key, reverse=self.rev)
        for v in rows:
            f = v['friendship']
            n = min(10, round(f / ps.FRIENDSHIP_MAX * 10))
            bar = '●' * n + '○' * (10 - n)
            img = self.app.images.villager(v['index'], 34)
            self.tv.insert('', 'end', iid=str(v['index']), text='  ' + v['name'], **({'image': img} if img else {}),
                           values=(f'{bar}  {f}', v['thank_points'], v['present_level'], v['home_area_name'] or '-',
                                   v['met'].strftime('%d %b %Y %H:%M') if v['met'] else 'starter'))
        keep = [k for k in keep if self.tv.exists(k)]
        if keep:
            self.tv.selection_set(keep)
        self.show()

    def selected(self):
        return [int(s) for s in self.tv.selection()]

    def show(self):
        sel = self.selected()
        c = self.c
        if not sel or not c:
            self.portrait.configure(image='')
            self.d_name.set('Select a resident')
            self.d_sub.set('Ctrl/Shift-click selects several')
            self.d_info.set('')
            self.map_btn.state(['disabled'])
            self.talk_cb.state(['disabled'])
            return
        v = c.get_villager(sel[0])
        self.portrait.configure(image=self.app.images.villager(v['index'], 120) or '')
        self.d_name.set(v['name'] if len(sel) == 1 else f'{len(sel)} residents selected')
        self.d_sub.set(f'Resident #{v["index"]}' if len(sel) == 1 else 'Friendship applies to all of them')
        self.fr.set(v['friendship'])
        self.scale.set(min(v['friendship'], ps.FRIENDSHIP_MAX))
        self.talk.set(v['name_talk_done'])
        self.talk_cb.state(['!disabled'])
        lines = [f'Thank points:  {v["thank_points"]}', f'Gift level:  {v["present_level"]}' + ('   (gift waiting)' if v['waiting_present'] else '')]
        if v['met']:
            lines.append(f'First met:  {v["met"]:%d %b %Y, %H:%M}')
        else:
            lines.append('First met:  with you from the start')
        if v['met_playtime'] is not None:
            lines.append(f'Play time then:  {ps.fmt_playtime(v["met_playtime"])}')
        if v['home_xyz']:
            lines.append('Home:  {}\nBlock X {}  Y {}  Z {}'.format(v['home_area_name'], *v['home_xyz']))
        else:
            lines.append('Home:  none yet')
        self.d_info.set('\n'.join(lines))
        ok = len(sel) == 1 and v['home_xyz'] and v['home_area'] in self.app.save.stage_files()
        self.map_btn.state(['!disabled'] if ok else ['disabled'])

    def apply(self):
        sel = self.selected()
        if not sel:
            return self.app.toast('Select a resident first.', 'err')
        try:
            val = int(self.fr.get())
        except (ValueError, tk.TclError):
            return self.app.toast('Friendship must be a number.', 'err')
        val = max(0, min(ps.FRIENDSHIP_MAX, val))
        who = self.c.get_villager(sel[0])['name'] if len(sel) == 1 else f'{len(sel)} residents'
        self.app.do(f'{who}: friendship {val}', lambda: [self.c.set_friendship(i, val) for i in sel])

    def set_talk(self):
        sel = self.selected()
        if sel:
            on = self.talk.get()
            self.app.do(f'Name conversation {"done" if on else "not done"}', lambda: [self.c.set_name_talk_done(i, on) for i in sel])

    def max_all(self):
        if not self.app.need():
            return
        low = [i for i in self.c.villagers() if self.c.get_villager(i)['friendship'] < ps.FRIENDSHIP_MAX]
        if not low:
            return self.app.toast('Everyone is already at max friendship.', 'info')
        self.app.do(f'Max friendship for {len(low)} residents', lambda: [self.c.set_friendship(i, ps.FRIENDSHIP_MAX) for i in low])

    def goto_map(self):
        sel = self.selected()
        if sel:
            v = self.c.get_villager(sel[0])
            self.app.pages['Island Map'].focus_home(v)
            self.app.show('Island Map')


# ============================================================ Moves & Emotes
class MovesPage(Page):
    title, nav = 'Moves & Emotes', 'Moves & Emotes'

    def build(self):
        self.columnconfigure(0, weight=2, uniform='m')
        self.columnconfigure(1, weight=3, uniform='m')
        self.rowconfigure(0, weight=1)
        left = ttk.Frame(self); left.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        right = ttk.Frame(self); right.grid(row=0, column=1, sticky='nsew')
        c = self.card(left, 'Moves')
        c.pack(fill='x', pady=(0, 10))
        g = ttk.Frame(c, style='C.TFrame'); g.pack(fill='x')
        g.columnconfigure(0, weight=1)
        self.move_w = {}
        for r, i in enumerate(ps.PUBLIC_SKILLS):
            ttk.Label(g, text=ps.name_of(ps.SKILL_NAMES, i, 'Move'), style='C.TLabel').grid(row=r, column=0, sticky='w', pady=2)
            uses = ttk.Label(g, text='', style='C.Muted.TLabel'); uses.grid(row=r, column=1, sticky='e', padx=10)
            b = ttk.Button(g, text='Learn', style='Small.TButton', width=9, command=lambda i=i: self.toggle_move(i)); b.grid(row=r, column=2)
            self.move_w[i] = (uses, b)
        ttk.Label(c, text='Click "Learned" to unlearn a move (its extras are switched off too). Learning or '
                          'unlearning against the story can confuse quests. Undo works until you save.',
                  style='C.Muted.TLabel', wraplength=330, justify='left').pack(anchor='w', pady=(8, 0))
        c = self.card(left, 'Move extras')
        c.pack(fill='x', pady=(0, 10))
        self.extra_w = {}
        for key, (label, _, _, _) in ps.EXTRAS.items():
            r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x')
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(r, text=label, variable=var, style='C.TCheckbutton', command=lambda k=key: self.toggle_extra(k))
            cb.pack(side='left')
            why = ttk.Label(r, text='', style='C.Muted.TLabel'); why.pack(side='right')
            self.extra_w[key] = (var, cb, why)
        c = self.card(left, 'Move wheel')
        c.pack(fill='x')
        g = ttk.Frame(c, style='C.TFrame'); g.pack(fill='x')
        self.wheel = []
        for k in range(ps.SKILL_WHEEL_COUNT):
            cb = ttk.Combobox(g, state='readonly', width=11)
            cb.grid(row=k // 4, column=k % 4, padx=2, pady=2, sticky='ew')
            g.columnconfigure(k % 4, weight=1, uniform='mw')
            cb.bind('<<ComboboxSelected>>', lambda e, k=k: self.set_wheel(k))
            self.wheel.append(cb)
        c = self.card(right)
        c.pack(fill='x', pady=(0, 10))
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x', pady=(0, 6))
        ttk.Label(r, text='Emotes', style='C.H.TLabel').pack(side='left')
        self.em_count = ttk.Label(r, text='', style='C.Muted.TLabel'); self.em_count.pack(side='left', padx=10)
        ttk.Button(r, text='Learn all', style='Accent.TButton', command=self.learn_all).pack(side='right')
        g = ttk.Frame(c, style='C.TFrame'); g.pack(fill='x')
        self.em_w = {}
        for n, i in enumerate(ps.PUBLIC_REACTIONS):
            b = ttk.Button(g, text=ps.REACTION_NAMES[i], style='Chip.TButton', command=lambda i=i: self.toggle_emote(i))
            b.grid(row=n // 4, column=n % 4, sticky='ew', padx=2, pady=1)
            g.columnconfigure(n % 4, weight=1, uniform='e')
            self.em_w[i] = b
        c = self.card(right, 'Emote wheel (24 slots)')
        c.pack(fill='x')
        g = ttk.Frame(c, style='C.TFrame'); g.pack(fill='x')
        self.rwheel = []
        for k in range(ps.REACT_WHEEL_COUNT):
            cb = ttk.Combobox(g, state='readonly', width=13)
            cb.grid(row=k // 4, column=k % 4, padx=2, pady=2, sticky='ew')
            g.columnconfigure(k % 4, weight=1, uniform='w')
            cb.bind('<<ComboboxSelected>>', lambda e, k=k: self.set_rwheel(k))
            self.rwheel.append(cb)

    def refresh(self):
        c = self.c
        if not c:
            return
        for i, (uses, b) in self.move_w.items():
            u, learned = c.skill(i)
            uses.configure(text=f'used {u:,}x' if u else '')
            b.configure(text='Learned' if learned else 'Learn', style='ChipOn.TButton' if learned else 'Small.TButton')
        for key, (var, cb, why) in self.extra_w.items():
            on = c.extra(key)
            var.set(on)
            block = '' if on else c.extra_blocker(key)
            why.configure(text=block)
            cb.state(['disabled'] if block else ['!disabled'])
        self.w_moves = [m for m in ps.WHEEL_SKILLS if c.skill(m)[1]]
        names = ['-'] + [ps.name_of(ps.SKILL_NAMES, m, 'Move') for m in self.w_moves]
        for k, cb in enumerate(self.wheel):
            m = c.wheel()[k]
            cb.configure(values=names)
            cb.set(ps.name_of(ps.SKILL_NAMES, m, 'Move') if m else '-')
        learned = [i for i in ps.PUBLIC_REACTIONS if c.reaction_learned(i)]
        self.em_count.configure(text=f'{len(learned)} of {len(ps.PUBLIC_REACTIONS)} learned. Click to learn or unlearn.')
        for i, b in self.em_w.items():
            b.configure(style='ChipOn.TButton' if i in learned else 'Chip.TButton')
        self.w_emotes = learned
        names = ['-'] + [ps.REACTION_NAMES[i] for i in learned]
        rw = c.reaction_wheel()
        for k, cb in enumerate(self.rwheel):
            cb.configure(values=names)
            cb.set(ps.name_of(ps.REACTION_NAMES, rw[k], 'Emote') if rw[k] else '-')

    def toggle_move(self, i):
        if not self.app.need():
            return
        name = ps.name_of(ps.SKILL_NAMES, i, 'Move')
        if self.c.skill(i)[1]:
            self.app.do(f'Unlearn {name}', lambda: self.c.forget_skill(i))
        else:
            self.app.do(f'Learn {name}', lambda: self.c.learn_skill(i))

    def toggle_extra(self, key):
        if self.app.need():
            on = self.extra_w[key][0].get()
            self.app.do(f'{ps.EXTRAS[key][0]} {"on" if on else "off"}', lambda: self.c.set_extra(key, on))

    def set_wheel(self, k):
        n = self.wheel[k].current()
        move = self.w_moves[n - 1] if n > 0 else 0
        self.app.do(f'Move wheel slot {k + 1}', lambda: self.c.set_skill_slot(k, move))

    def toggle_emote(self, i):
        if not self.app.need():
            return
        if self.c.reaction_learned(i):
            self.app.do(f'Unlearn emote {ps.REACTION_NAMES[i]}', lambda: self.c.forget_reaction(i))
        else:
            self.app.do(f'Learn emote {ps.REACTION_NAMES[i]}', lambda: self.c.learn_reaction(i))

    def learn_all(self):
        if self.app.need():
            self.app.do('Learn all emotes', lambda: [self.c.learn_reaction(i) for i in ps.PUBLIC_REACTIONS])

    def set_rwheel(self, k):
        n = self.rwheel[k].current()
        emote = self.w_emotes[n - 1] if n > 0 else 0
        self.app.do(f'Emote wheel slot {k + 1}', lambda: self.c.set_reaction_slot(k, emote))


# ============================================================ Wardrobe
class WardrobePage(Page):
    title, nav = 'Wardrobe', 'Wardrobe'
    GROUPS = (('outfits', 'Outfits', ps.OUTFITS, 'outfit'), ('hair', 'Hairstyles', ps.HAIRSTYLES, 'hairstyle'))

    def build(self):
        self.w = {}
        self.counts, self.group_btns = {}, {}
        for key, title, entries, kind in self.GROUPS:
            c = self.card(self)
            c.pack(fill='x', pady=(0, 10))
            r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x', pady=(0, 6))
            ttk.Label(r, text=title, style='C.H.TLabel').pack(side='left')
            self.counts[key] = ttk.Label(r, text='', style='C.Muted.TLabel'); self.counts[key].pack(side='left', padx=10)
            b = ttk.Button(r, text=f'Unlock all {title.lower()}', style='Accent.TButton',
                           command=lambda e=entries, t=title: self.unlock([i for i, _ in e if i], f'Unlock all {t.lower()}'))
            b.pack(side='right')
            self.group_btns[key] = b
            g = ttk.Frame(c, style='C.TFrame'); g.pack(fill='x')
            for n, (i, name) in enumerate(entries):
                b = ttk.Button(g, text=name, style='Chip.TButton',
                               command=lambda i=i, nm=f'{name} {kind}': self.toggle(i, nm))
                b.grid(row=n // 6, column=n % 6, sticky='ew', padx=2, pady=1)
                g.columnconfigure(n % 6, weight=1, uniform=key)
                self.w[(key, n)] = (i, name, b)
        c = self.card(self)
        c.pack(fill='x')
        r = ttk.Frame(c, style='C.TFrame'); r.pack(fill='x', pady=(0, 6))
        ttk.Label(r, text='Everything', style='C.H.TLabel').pack(side='left')
        self.counts['all'] = ttk.Label(r, text='', style='C.Muted.TLabel'); self.counts['all'].pack(side='left', padx=10)
        self.all_btn = ttk.Button(r, text='Unlock all', style='Accent.TButton',
                                  command=lambda: self.unlock(ps.WARDROBE_IDS, 'Unlock all outfits & hairstyles'))
        self.all_btn.pack(side='right')
        ttk.Label(c, text='Click a name to unlock it, click a highlighted one to remove it again. Familiar 1/2 and the '
                          'starting hairstyles are always there. Change clothes in game before removing the outfit '
                          'you are wearing. "Unlock all" also sets the unnamed wardrobe entries; '
                          'that was tested in game with no side effects.\n'
                          'IDs follow the in-game mirror order, spot-checked in game for 7 outfits and 5 hairstyles.',
                  style='C.Muted.TLabel', wraplength=1000, justify='left').pack(anchor='w')

    def refresh(self):
        c = self.c
        if not c:
            return
        for key, _, entries, _ in self.GROUPS:
            have = [i for i, _ in entries if c.wardrobe_available(i)]
            self.counts[key].configure(text=f'{len(have)} of {len(entries)} available')
            self.group_btns[key].state(['disabled'] if len(have) == len(entries) else ['!disabled'])
        for (key, n), (i, name, b) in self.w.items():
            b.configure(style='ChipOn.TButton' if c.wardrobe_available(i) else 'Chip.TButton')
            b.state(['disabled'] if i in ps.WARDROBE_DEFAULTS else ['!disabled'])  # starting ones can't be removed
        n, total = len(c.wardrobe_unlocked()), len(ps.WARDROBE_IDS)
        self.counts['all'].configure(text=f'{n} of {total} wardrobe entries set in the save')
        self.all_btn.state(['disabled'] if n == total else ['!disabled'])

    def unlock(self, ids, label):
        if self.app.need():
            self.app.do(label, lambda: self.c.unlock_wardrobe(ids))

    def toggle(self, i, name):
        if not self.app.need():
            return
        if self.c.wardrobe_owned(i):
            self.app.do(f'Remove {name}', lambda: self.c.lock_wardrobe([i]))
        else:
            self.app.do(f'Unlock {name}', lambda: self.c.unlock_wardrobe([i]))


# ============================================================ Island map
class MapPage(Page):
    title, nav = 'Island Map', 'Island Map'

    def build(self):
        self.area, self.scale, self.cx, self.cz = None, 1.0, 0.0, 0.0
        self.photo, self.pending, self.hl, self.job, self.loading = None, None, None, None, {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        self.pick = ttk.Combobox(top, state='readonly', width=26)
        self.pick.pack(side='left')
        self.pick.bind('<<ComboboxSelected>>', lambda e: self.choose())
        ttk.Button(top, text='Fit island', command=lambda: self.fit(True)).pack(side='left', padx=(10, 0))
        ttk.Button(top, text='Fit everything', command=lambda: self.fit(False)).pack(side='left', padx=6)
        ttk.Button(top, text='+', width=3, command=lambda: self.zoom(1.5)).pack(side='left')
        ttk.Button(top, text='-', width=3, command=lambda: self.zoom(1 / 1.5)).pack(side='left', padx=6)
        self.homes = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text='Resident homes', variable=self.homes, command=self.draw).pack(side='left', padx=8)
        ttk.Button(top, text='Export PNG...', command=self.export).pack(side='right')
        self.cv = tk.Canvas(self, bg='#%02x%02x%02x' % px.BACKGROUND, highlightthickness=0)
        self.cv.grid(row=1, column=0, sticky='nsew')
        self.cv.bind('<Configure>', lambda e: self.draw())
        self.cv.bind('<ButtonPress-1>', lambda e: setattr(self, 'grab', (e.x, e.y, self.cx, self.cz)))
        self.cv.bind('<B1-Motion>', self.pan)
        self.cv.bind('<MouseWheel>', lambda e: self.zoom(1.25 if e.delta > 0 else 0.8, e.x, e.y))
        self.cv.bind('<Motion>', self.hover)
        self.info = tk.StringVar(value='Drag to move, scroll to zoom.')
        ttk.Label(self, textvariable=self.info, style='Muted.TLabel').grid(row=2, column=0, sticky='w', pady=(6, 0))

    def refresh(self):
        if not self.app.save:
            return
        st = self.app.save.stage_files()
        self.areas = list(st)
        self.pick.configure(values=[f'{n:02}  {ps.name_of(ps.AREA_NAMES, n, "Area")}' for n in st])
        if self.pending in st:
            self.area = self.pending
        if self.area not in st:
            self.area = self.areas[0] if st else None
        if self.area is not None:
            self.pick.current(self.areas.index(self.area))
        self.ensure()

    def choose(self):
        self.area, self.hl = self.areas[self.pick.current()], None
        self.ensure()

    def focus_home(self, v):
        self.pending, self.hl = v['home_area'], v['index']

    def ensure(self):
        app, a = self.app, self.area
        if a is None:
            return self.message('This save has no island files.')
        key = (app.save.folder, a)
        if key in app.map_cache:
            if self.pending == a and self.hl is not None:
                x, y, z = self.c.get_villager(self.hl)['home_xyz']
                m = app.map_cache[key][0]
                self.cx, self.cz = m.to_pixel(x, z)
                self.scale = 6.0
                self.pending = None
                self.draw()
            else:
                self.pending = None
                self.fit(True)
            return
        self.message('Decoding island...')
        if key in self.loading:
            return
        prog = self.loading[key] = [0.0]
        path = app.save.stage_files()[a]

        def work():
            try:
                m = px.StageMap(path, a, progress=lambda f: prog.__setitem__(0, f))
                app.q.put(('map', key, (m, m.render()), None))
            except Exception as ex:
                app.q.put(('map', key, None, str(ex)))
        threading.Thread(target=work, daemon=True).start()
        self.tick(key)

    def tick(self, key):
        if key in self.loading and self.winfo_exists():
            if (self.app.save.folder, self.area) == key:
                self.message(f'Decoding island...  {int(self.loading[key][0] * 100)}%')
            self.after(120, lambda: self.tick(key))

    def loaded(self, key, result, err):
        self.loading.pop(key, None)
        if err:
            if self.app.save and (self.app.save.folder, self.area) == key:
                self.message(f'Cannot read this island: {err}')
            return
        self.app.map_cache[key] = result
        if self.app.save and (self.app.save.folder, self.area) == key:
            self.ensure()

    def message(self, text):
        self.cv.delete('all')
        self.cv.create_text(self.cv.winfo_width() // 2, self.cv.winfo_height() // 2, text=text, fill='#aab3c5', font=(FONT, 12))

    def current(self):
        return self.app.map_cache.get((self.app.save.folder, self.area)) if self.app.save else None

    def fit(self, island):
        cur = self.current()
        if not cur:
            return
        m = cur[0]
        x0, z0, x1, z1 = m.main_bbox() if island else (0, 0, m.width, m.height)
        w, h = max(self.cv.winfo_width(), 50), max(self.cv.winfo_height(), 50)
        self.scale = max(0.2, min(w / (x1 - x0 + 16), h / (z1 - z0 + 16)))
        self.cx, self.cz = (x0 + x1) / 2, (z0 + z1) / 2
        self.draw()

    def zoom(self, f, ex=None, ey=None):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        ex, ey = (w / 2 if ex is None else ex), (h / 2 if ey is None else ey)
        wx, wz = self.cx + (ex - w / 2) / self.scale, self.cz + (ey - h / 2) / self.scale
        self.scale = max(0.2, min(32.0, self.scale * f))
        self.cx, self.cz = wx - (ex - w / 2) / self.scale, wz - (ey - h / 2) / self.scale
        self.draw()

    def pan(self, e):
        gx, gy, cx, cz = self.grab
        self.cx, self.cz = cx - (e.x - gx) / self.scale, cz - (e.y - gy) / self.scale
        self.draw()

    def draw(self):
        if self.job is None:
            self.job = self.after_idle(self._draw)

    def _draw(self):
        self.job = None
        cur = self.current()
        if not cur or not self.winfo_exists():
            return
        m, img = cur
        cv, s = self.cv, self.scale
        w, h = cv.winfo_width(), cv.winfo_height()
        vx0, vz0 = self.cx - w / 2 / s, self.cz - h / 2 / s
        bx0, bz0 = max(0, math.floor(vx0)), max(0, math.floor(vz0))
        bx1, bz1 = min(m.width, math.ceil(vx0 + w / s)), min(m.height, math.ceil(vz0 + h / s))
        cv.delete('all')
        if bx1 > bx0 and bz1 > bz0:
            part = img.crop((bx0, bz0, bx1, bz1)).resize((max(1, round((bx1 - bx0) * s)), max(1, round((bz1 - bz0) * s))),
                                                         Image.NEAREST if s >= 1 else Image.BILINEAR)
            self.photo = ImageTk.PhotoImage(part)
            cv.create_image((bx0 - vx0) * s, (bz0 - vz0) * s, image=self.photo, anchor='nw')
        self.marks = []
        if self.homes.get():
            for i, name, x, y, z in px.homes_on(self.c, self.area):
                ix, iz = m.to_pixel(x, z)
                sx, sy = (ix + 0.5 - vx0) * s, (iz + 0.5 - vz0) * s
                if not (-20 < sx < w + 20 and -20 < sy < h + 20):
                    continue
                hl = i == self.hl
                r = 8 if hl else 5
                cv.create_oval(sx - r, sy - r, sx + r, sy + r, fill='#ffd24a' if hl else '#ff6b8b', outline='#ffffff', width=2)
                if s >= 2.5 or hl:
                    t = cv.create_text(sx + r + 4, sy, text=name, anchor='w', fill='#ffffff', font=(FONT, 9, 'bold'))
                    cv.tag_lower(cv.create_rectangle(*[v + d for v, d in zip(cv.bbox(t), (-3, -1, 3, 1))], fill='#10131a', outline=''), t)
                self.marks.append((sx, sy, name))

    def hover(self, e):
        cur = self.current()
        if not cur:
            return
        m = cur[0]
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        ix = math.floor(self.cx + (e.x - w / 2) / self.scale)
        iz = math.floor(self.cz + (e.y - h / 2) / self.scale)
        hit = m.info_at(ix, iz)
        near = [n for sx, sy, n in getattr(self, 'marks', []) if abs(sx - e.x) < 9 and abs(sy - e.y) < 9]
        txt = f'X {hit[0]}   Y {hit[1]}   Z {hit[2]}   ·   block {hit[3]}' if hit else 'No terrain here'
        self.info.set(txt + (f'   ·   {near[0]}\'s home' if near else '') +
                      f'      {m.name}: {m.chunks} chunks, {m.parts:,} placed objects, zoom {self.scale:.1f}x')

    def export(self):
        cur = self.current()
        if not cur:
            return
        m, img = cur
        f = filedialog.asksaveasfilename(title='Export island map', defaultextension='.png', filetypes=[('PNG image', '*.png')],
                                         initialfile=f'pokopia_island_{self.area:02}.png')
        if not f:
            return
        out = img.copy()
        if self.homes.get():
            d = ImageDraw.Draw(out)
            for i, name, x, y, z in px.homes_on(self.c, self.area):
                ix, iz = m.to_pixel(x, z)
                d.ellipse((ix - 3, iz - 3, ix + 3, iz + 3), fill=(255, 107, 139), outline=(255, 255, 255))
        x0, z0, x1, z1 = m.main_bbox()
        out.crop((max(0, x0 - 8), max(0, z0 - 8), min(m.width, x1 + 8), min(m.height, z1 + 8))).resize(
            ((x1 - x0 + 16) * 3, (z1 - z0 + 16) * 3), Image.NEAREST).save(f)
        self.app.toast(f'Map exported: {f}')


# ============================================================ Photos
class PhotosPage(Page):
    title, nav = 'Photos', 'Photos'
    TW, TH = 208, 117

    def build(self):
        self.sel, self.big, self.thumbs = None, None, []
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        self.head = ttk.Label(top, text='', style='Muted.TLabel')
        self.head.pack(side='left')
        ttk.Button(top, text='Export all...', style='Accent.TButton', command=lambda: self.export(None)).pack(side='right')
        ttk.Button(top, text='Export this photo...', command=lambda: self.export([self.sel]) if self.sel is not None else None).pack(side='right', padx=8)
        fr, self.cv = scrolled(self, lambda p: tk.Canvas(p, bg=self.P['bg'], highlightthickness=0, width=2 * (self.TW + 10) + 10))
        fr.grid(row=1, column=0, sticky='ns')
        self.cv.bind('<Button-1>', self.click)
        self.cv.bind('<MouseWheel>', lambda e: self.cv.yview_scroll(-e.delta // 120, 'units'))
        self.view = tk.Canvas(self, bg=self.P['panel'], highlightthickness=0)
        self.view.grid(row=1, column=1, sticky='nsew', padx=(12, 0))
        self.view.bind('<Configure>', lambda e: self.show())

    def refresh(self):
        app = self.app
        self.cv.delete('all')
        if app.album is None:
            self.head.configure(text={'loading': 'Reading the photo album...', 'none': 'This save has no photo file.'}.get(app.album_state, app.album_state))
            self.view.delete('all')
            return
        n = len(app.album)
        self.head.configure(text=f'{n} photo{"s" if n != 1 else ""} stored in the save (1920 x 1080 JPEG). Exports are the original files, not re-compressed.')
        self.thumbs = [ImageTk.PhotoImage(t) for t in app.album_thumbs]
        for i, t in enumerate(self.thumbs):
            x, y = 10 + (i % 2) * (self.TW + 10), 10 + (i // 2) * (self.TH + 10)
            self.cv.create_image(x, y, image=t, anchor='nw')
            self.cv.create_rectangle(x - 1, y - 1, x + self.TW, y + self.TH, outline=self.P['accent'] if i == self.sel else self.P['line'], width=3 if i == self.sel else 1)
        self.cv.configure(scrollregion=(0, 0, 0, 20 + ((n + 1) // 2) * (self.TH + 10)))
        if self.sel is None and n:
            self.sel = 0
            self.refresh()
        self.show()

    def click(self, e):
        if self.app.album is None:
            return
        x, y = self.cv.canvasx(e.x) - 10, self.cv.canvasy(e.y) - 10
        col, row = int(x // (self.TW + 10)), int(y // (self.TH + 10))
        i = row * 2 + col
        if 0 <= col < 2 and 0 <= i < len(self.app.album):
            self.sel = i
            self.refresh()

    def show(self):
        a = self.app.album
        self.view.delete('all')
        if a is None or self.sel is None or self.sel >= len(a):
            return
        w, h = self.view.winfo_width(), self.view.winfo_height()
        if w < 20 or h < 20:
            return
        im = a.image(self.sel)
        im.draft('RGB', (w, h))
        im.thumbnail((w - 16, h - 16), Image.LANCZOS)
        self.big = ImageTk.PhotoImage(im)
        self.view.create_image(w // 2, h // 2, image=self.big)

    def export(self, which):
        a = self.app.album
        if a is None or not len(a):
            return
        d = filedialog.askdirectory(title='Folder to export photos into')
        if d:
            files = a.export(d, which)
            self.app.toast(f'{len(files)} photo{"s" if len(files) != 1 else ""} exported to {d}')


# ============================================================ Backups
class BackupsPage(Page):
    title, nav = 'Backups', 'Backups'
    COLS = [('when', 'Saved', 140), ('name', 'Folder', 210), ('player', 'Player', 90), ('played', 'Played', 80),
            ('res', 'Residents', 80), ('items', 'Items', 60)]

    def build(self):
        self.rows = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=2)
        self.rowconfigure(3, weight=3)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        ttk.Button(top, text='Back up now', style='Accent.TButton', command=self.backup).pack(side='left')
        ttk.Button(top, text='Compare with open save', command=self.compare).pack(side='left', padx=8)
        ttk.Button(top, text='Restore...', style='Danger.TButton', command=self.restore).pack(side='left')
        ttk.Button(top, text='Open folder', command=self.open_folder).pack(side='left', padx=8)
        ttk.Button(top, text='What changed since the game\'s last save?', command=self.compare_b00).pack(side='right')
        fr, self.tv = scrolled(self, lambda p: ttk.Treeview(p, columns=[c[0] for c in self.COLS], show='headings', selectmode='browse', height=6))
        fr.grid(row=1, column=0, sticky='nsew')
        for key, text, w in self.COLS:
            self.tv.heading(key, text=text, anchor='w')
            self.tv.column(key, width=w, anchor='w')
        self.out_title = ttk.Label(self, text='Pick a backup and press Compare, or ask what changed since the game\'s last save.', style='Muted.TLabel')
        self.out_title.grid(row=2, column=0, sticky='w', pady=(12, 4))
        P = self.P
        fr, self.out = scrolled(self, lambda p: tk.Text(p, bg=P['card'], fg=P['text'], bd=0, highlightthickness=0, font=(FONT, 10),
                                                        padx=12, pady=10, wrap='word', state='disabled', height=8))
        fr.grid(row=3, column=0, sticky='nsew')

    def refresh(self):
        self.rows = px.list_backups()
        keep = self.tv.selection()
        self.tv.delete(*self.tv.get_children())
        for n, e in enumerate(self.rows):
            self.tv.insert('', 'end', iid=str(n), values=(f'{e["when"]:%d %b %Y %H:%M}', e['name'], e['player'],
                                                           ps.fmt_playtime(e['playtime']) if e['playtime'] is not None else '-',
                                                           e['residents'], e['items']))
        if keep and self.tv.exists(keep[0]):
            self.tv.selection_set(keep[0])

    def chosen(self):
        s = self.tv.selection()
        if not s:
            self.app.toast('Select a backup in the list first.', 'err')
            return None
        return self.rows[int(s[0])]

    def lines(self, title, lines):
        self.out_title.configure(text=title)
        self.out.configure(state='normal')
        self.out.delete('1.0', 'end')
        self.out.insert('1.0', '\n'.join(lines) if lines else 'No differences in the fields this editor understands.')
        self.out.configure(state='disabled')

    def backup(self):
        if not self.app.need():
            return
        try:
            dst = px.create_backup(self.app.save.folder)
        except Exception as ex:
            return self.app.toast(f'Backup failed: {ex}', 'err')
        self.refresh()
        self.app.toast(f'Backup written: {dst}')

    def compare(self):
        e = self.chosen()
        if not e or not self.app.need():
            return
        try:
            old = ps.SaveFolder(e['path']).common
        except Exception as ex:
            return self.app.toast(str(ex), 'err')
        self.lines(f'From backup "{e["name"]}" to the open save (including unsaved edits):', ps.describe_changes(old, self.c))

    def compare_b00(self):
        if not self.app.need():
            return
        old = self.app.save.game_backup()
        if old is None:
            return self.app.toast('This save has no readable B00 slot.', 'err')
        self.lines('From the game\'s previous save (B00) to the open save:', ps.describe_changes(old, self.c))

    def open_folder(self):
        s = self.tv.selection()
        p = self.rows[int(s[0])]['path'] if s else ps.default_backup_root()
        if os.path.isdir(p):
            os.startfile(p)

    def restore(self):
        e = self.chosen()
        app = self.app
        if not e or not app.need():
            return
        if app.emus and not messagebox.askyesno('Emulator running', f'{", ".join(app.emus)} is running.\n\nRestoring while the game is open can be undone by the game\'s next save. Restore anyway?', default='no'):
            return
        if not messagebox.askyesno('Restore backup', f'Replace the whole save folder\n{app.save.folder}\n\nwith backup "{e["name"]}" ({e["when"]:%d %b %Y %H:%M})?\n\n'
                                   'The current save is backed up first.' + ('\nUnsaved edits in the editor are discarded.' if self.c.edited else ''), default='no'):
            return
        try:
            safety = px.restore_backup(e['path'], app.save.folder)
        except Exception as ex:
            return messagebox.showerror('Not restored', str(ex))
        app.load(app.save.folder, quiet=True)
        app.toast(f'Restored. The previous save is in {safety}')


# ============================================================ Advanced
class AdvancedPage(Page):
    title, nav = 'Advanced', 'Advanced'
    FC, FW, FH = 25, 31, 27

    def build(self):
        self.columnconfigure(0, weight=1)
        warn = self.card(self)
        warn.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(warn, text='These fields are not verified. Raw flags, thank points and gift level were found by inspecting the save; '
                             'nobody has confirmed what the game does when they are changed. Keep a backup.', style='C.Warn.TLabel',
                  wraplength=900, justify='left').pack(anchor='w')
        self.unlock = tk.BooleanVar(value=self.app.adv_unlocked)
        ttk.Checkbutton(warn, text='I understand, let me edit them', variable=self.unlock, style='C.TCheckbutton', command=self.toggle).pack(anchor='w', pady=(8, 0))
        c = self.card(self, 'Function flags 1-249')
        c.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        P = self.P
        self.cv = tk.Canvas(c, bg=P['card'], highlightthickness=0, width=self.FC * self.FW + 2, height=10 * self.FH + 2)
        self.cv.pack(anchor='w')
        self.cv.bind('<Button-1>', self.click)
        Tip(self.cv, self.tip)
        ttk.Label(c, text='Filled = on. Outlined in amber = behaviour known (hover for the name). Click to toggle.', style='C.Muted.TLabel').pack(anchor='w', pady=(6, 0))
        c = self.card(self, 'Resident values')
        c.grid(row=2, column=0, sticky='ew')
        r = ttk.Frame(c, style='C.TFrame'); r.pack(anchor='w')
        self.who = ttk.Combobox(r, state='readonly', width=24)
        self.who.pack(side='left')
        self.who.bind('<<ComboboxSelected>>', lambda e: self.load_res())
        ttk.Label(r, text='Thank points', style='C.TLabel').pack(side='left', padx=(16, 6))
        self.thank = tk.StringVar()
        self.w_thank = ttk.Spinbox(r, from_=0, to=65535, textvariable=self.thank, width=7)
        self.w_thank.pack(side='left')
        ttk.Label(r, text='Gift level', style='C.TLabel').pack(side='left', padx=(16, 6))
        self.lvl = tk.StringVar()
        self.w_lvl = ttk.Spinbox(r, from_=0, to=255, textvariable=self.lvl, width=5)
        self.w_lvl.pack(side='left')
        self.w_apply = ttk.Button(r, text='Apply', command=self.apply_res)
        self.w_apply.pack(side='left', padx=16)

    def toggle(self):
        self.app.adv_unlocked = self.unlock.get()
        self.refresh()

    def cell(self, e):
        col, row = e.x // self.FW, e.y // self.FH
        i = row * self.FC + col
        return i if 0 <= col < self.FC and 1 <= i < ps.FLAG_COUNT else None

    def tip(self, e):
        i = self.cell(e)
        if i is None or not self.c:
            return None
        return f'Flag {i}: {ps.KNOWN_FLAGS.get(i, "unknown")}  ({"on" if self.c.get_flag(i) else "off"})'

    def click(self, e):
        i = self.cell(e)
        if i is None or not self.app.need():
            return
        if not self.unlock.get():
            return self.app.toast('Tick the box above to enable advanced edits.', 'err')
        on = not self.c.get_flag(i)
        self.app.do(f'Flag {i} {"on" if on else "off"}', lambda: self.c.set_flag(i, on))

    def refresh(self):
        c, cv, P = self.c, self.cv, self.P
        cv.delete('all')
        if not c:
            return
        live = self.unlock.get()
        for i in range(1, ps.FLAG_COUNT):
            x, y = (i % self.FC) * self.FW + 1, (i // self.FC) * self.FH + 1
            on, known = c.get_flag(i), i in ps.KNOWN_FLAGS
            cv.create_rectangle(x, y, x + self.FW - 4, y + self.FH - 4, fill=(P['accent'] if live else P['muted']) if on else P['cell'],
                                outline=P['warn'] if known else P['line'], width=2 if known else 1)
            cv.create_text(x + (self.FW - 4) // 2, y + (self.FH - 4) // 2, text=str(i), font=(FONT, 8), fill=P['onaccent'] if on else P['muted'])
        self.ids = c.villagers()
        cur = self.who.current()
        self.who.configure(values=[f'{ps.name_of(ps.VILLAGER_NAMES, i, "Resident")}  #{i}' for i in self.ids])
        if self.ids:
            self.who.current(cur if 0 <= cur < len(self.ids) else 0)
            self.load_res()
        for w in (self.w_thank, self.w_lvl, self.w_apply):
            w.state(['!disabled'] if live else ['disabled'])

    def load_res(self):
        v = self.c.get_villager(self.ids[self.who.current()])
        self.thank.set(str(v['thank_points']))
        self.lvl.set(str(v['present_level']))

    def apply_res(self):
        if not self.ids:
            return
        i = self.ids[self.who.current()]
        name = ps.name_of(ps.VILLAGER_NAMES, i, 'Resident')

        def go():
            self.c.set_thank_points(i, int(self.thank.get()))
            self.c.set_present_level(i, int(self.lvl.get()))
        self.app.do(f'{name}: thank points {self.thank.get()}, gift level {self.lvl.get()}', go)


PAGES = [OverviewPage, BagPage, ResidentsPage, MovesPage, WardrobePage, MapPage, PhotosPage, BackupsPage, AdvancedPage]


# ============================================================ App
class App(tk.Tk):
    def __init__(self, folder=None, theme=None, persist=True):
        super().__init__()
        self.persist = persist  # False for test runs, which must not change the user's settings
        self.settings = self.read_settings()
        self.theme = theme or self.settings.get('theme', 'dark')
        self.save, self.album, self.album_thumbs, self.album_state = None, None, [], 'none'
        self.map_cache, self.emus, self.adv_unlocked = {}, [], False
        self.q = queue.Queue()
        self.images = Images()
        self.title('Pokopia Save Editor')
        self.geometry(self.settings.get('geometry', '1280x840'))
        self.minsize(1120, 740)
        self.current = 'Overview'
        self.build_ui()
        self.protocol('WM_DELETE_WINDOW', self.close)
        for seq, fn in (('<Control-o>', self.open), ('<Control-s>', self.save_inplace), ('<Control-S>', self.save_new),
                        ('<Control-z>', self.undo), ('<Control-y>', self.redo), ('<F5>', self.reload),
                        ('<Control-f>', lambda: self.pages[self.current].focus_search()), ('<Delete>', self.delete_key)):
            self.bind(seq, lambda e, fn=fn: self.key(e, fn))
        self.bind('<FocusIn>', self.focus_in)
        self.after(100, self.poll)
        # 1. folder given on the command line, 2. last folder used, 3. newest save found in the emulator folders
        last = self.settings.get('last_folder')
        start = folder or (last if last and px.save_header(last) else None) or px.default_save()
        if start:
            self.load(start, quiet=True)
            if self.save and start != last and not folder:
                self.toast(f'Found your save automatically: {start}')
        elif self.persist:  # (not in screenshot mode)
            self.after(300, self.open)  # nothing found: let the user pick or browse
        self.check_emulators()

    # ---------- settings ----------
    def read_settings(self):
        try:
            with open(SETTINGS, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def write_settings(self):
        if not self.persist:
            return
        d = dict(theme=self.theme, geometry=self.geometry(), last_folder=self.save.folder if self.save else self.settings.get('last_folder'))
        try:
            with open(SETTINGS, 'w', encoding='utf-8') as f:
                json.dump(d, f, indent=1)
        except OSError:
            pass

    # ---------- layout ----------
    def build_ui(self):
        for w in self.winfo_children():
            w.destroy()
        P = self.P = PALETTES[self.theme]
        apply_theme(self, P)
        self.configure(bg=P['bg'])
        self.update_idletasks()
        dark_titlebar(self, self.theme == 'dark')
        side = ttk.Frame(self, style='S.TFrame', width=200)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        ttk.Label(side, text='Pokopia', style='S.Title.TLabel').pack(anchor='w', padx=16, pady=(18, 0))
        ttk.Label(side, text='Save Editor', style='S.Muted.TLabel').pack(anchor='w', padx=16, pady=(0, 14))
        self.navb = {}
        main = ttk.Frame(self)
        main.pack(side='left', fill='both', expand=True)
        head = ttk.Frame(main)
        head.pack(fill='x', padx=20, pady=(16, 10))
        self.h_title = ttk.Label(head, text='', style='H1.TLabel')
        self.h_title.pack(side='left')
        self.b_save = ttk.Button(head, text='Save', style='Accent.TButton', command=self.save_inplace)
        self.b_save.pack(side='right')
        Tip(self.b_save, 'Overwrite the open save (Ctrl+S). A full backup of the folder is made first.')
        b = ttk.Button(head, text='Save to new folder...', command=self.save_new)
        b.pack(side='right', padx=8)
        Tip(b, 'Write a complete copy of the save, with your edits, into an empty folder (Ctrl+Shift+S).')
        self.b_redo = ttk.Button(head, text='Redo', command=self.redo)
        self.b_redo.pack(side='right')
        self.b_undo = ttk.Button(head, text='Undo', command=self.undo)
        self.b_undo.pack(side='right', padx=8)
        ttk.Button(head, text='Open...', command=self.open).pack(side='right')
        bar = ttk.Frame(main, style='S.TFrame')
        bar.pack(side='bottom', fill='x')
        self.status = ttk.Label(bar, text='', style='S.TLabel')
        self.status.pack(side='left', padx=14, pady=6)
        self.state_lbl = ttk.Label(bar, text='', style='S.Muted.TLabel')
        self.state_lbl.pack(side='right', padx=14)
        self.content = ttk.Frame(main)
        self.content.pack(fill='both', expand=True, padx=20, pady=(0, 14))
        self.pages = {}
        for cls in PAGES:
            p = self.pages[cls.nav] = cls(self)
            b = ttk.Button(side, text=cls.nav, style='Nav.TButton', command=lambda n=cls.nav: self.show(n))
            b.pack(fill='x')
            self.navb[cls.nav] = b
        ttk.Button(side, text='Light theme' if self.theme == 'dark' else 'Dark theme', style='Nav.TButton', command=self.toggle_theme).pack(side='bottom', fill='x', pady=(0, 10))
        self.side_info = ttk.Label(side, text='', style='S.Muted.TLabel', justify='left', wraplength=170)
        self.side_info.pack(side='bottom', anchor='w', padx=16, pady=10)
        self.show(self.current)
        self.update_chrome()

    def toggle_theme(self):
        self.theme = 'light' if self.theme == 'dark' else 'dark'
        self.build_ui()
        self.write_settings()

    def show(self, name):
        self.current = name
        for n, p in self.pages.items():
            p.pack_forget()
            self.navb[n].configure(style='NavSel.TButton' if n == name else 'Nav.TButton')
        page = self.pages[name]
        page.pack(fill='both', expand=True)
        self.h_title.configure(text=page.title)
        if page.dirty:
            page.dirty = False
            page.refresh()

    def update_chrome(self):
        c = self.save.common if self.save else None
        edited = bool(c and c.edited)
        self.title(('* ' if edited else '') + 'Pokopia Save Editor' + (f' - {c.player_name}' if c else ''))
        self.b_save.state(['!disabled'] if edited else ['disabled'])
        self.b_undo.state(['!disabled'] if c and c.history else ['disabled'])
        self.b_redo.state(['!disabled'] if c and c.can_redo else ['disabled'])
        if not c:
            self.state_lbl.configure(text='No save open')
            self.side_info.configure(text='Open a save folder\n(the one with G00 and S00).')
            return
        n = len(c.history)
        self.state_lbl.configure(text=(f'{n} unsaved edit{"s" if n != 1 else ""}   ·   ' if edited else 'No unsaved changes   ·   ') + self.save.folder)
        pt = c.play_seconds
        self.side_info.configure(text=f'{c.player_name}\n{ps.fmt_playtime(pt) if pt is not None else ""} played\n{len(c.villagers())} residents')

    def data_changed(self):
        for p in self.pages.values():
            p.dirty = True
        self.update_chrome()
        self.show(self.current)

    def toast(self, msg, kind='ok'):
        self.status.configure(text=msg, foreground={'ok': self.P['accent'], 'err': self.P['danger'], 'info': self.P['muted']}[kind])
        if kind == 'err':
            self.bell()
        if getattr(self, '_toast', None):
            self.after_cancel(self._toast)
        self._toast = self.after(9000, lambda: self.status.configure(text=''))

    # ---------- background work ----------
    def poll(self):
        try:
            while True:
                kind, key, result, err = self.q.get_nowait()
                if kind == 'map':
                    self.pages['Island Map'].loaded(key, result, err)
                elif kind == 'album' and self.save and key == self.save.folder:
                    if err:
                        self.album, self.album_state = None, f'Cannot read photos: {err}'
                    else:
                        self.album, self.album_thumbs = result
                        self.album_state = 'ready'
                    for n in ('Overview', 'Photos'):
                        self.pages[n].dirty = True
                    self.show(self.current)
                elif kind == 'emu':
                    if result != self.emus:
                        self.emus = result
                        self.pages['Overview'].dirty = True
                        if self.current == 'Overview':
                            self.show('Overview')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def load_album(self):
        self.album, self.album_thumbs = None, []
        path = self.save.photo_file()
        if not path or Image is None:
            self.album_state = 'none' if Image is not None else 'Pillow is not installed'
            return
        self.album_state = 'loading'
        folder = self.save.folder

        def work():
            try:
                a = px.PhotoAlbum(path)
                thumbs = []
                for i in range(len(a)):
                    im = a.image(i)
                    im.draft('RGB', (PhotosPage.TW * 2, PhotosPage.TH * 2))
                    thumbs.append(im.convert('RGB').resize((PhotosPage.TW, PhotosPage.TH), Image.LANCZOS))
                self.q.put(('album', folder, (a, thumbs), None))
            except Exception as ex:
                self.q.put(('album', folder, None, str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def check_emulators(self):
        threading.Thread(target=lambda: self.q.put(('emu', None, px.running_emulators(), None)), daemon=True).start()

    def focus_in(self, e):
        if e.widget is not self:
            return
        self.check_emulators()
        if self.save and self.save.changed_on_disk():
            if self.save.common.edited:
                self.toast('The game saved again while you had unsaved edits. Reload (F5) before overwriting.', 'err')
            else:
                self.load(self.save.folder, quiet=True)
                self.toast('The save changed on disk, reloaded.', 'info')

    # ---------- editing ----------
    def need(self):
        if not self.save:
            self.toast('Open a save folder first.', 'err')
            return False
        return True

    def do(self, label, fn):
        """Run one edit as an undo step. Errors roll the edit back and show in the status bar."""
        if not self.need():
            return False
        c = self.save.common
        try:
            fn()
        except (ValueError, ps.FormatError, tk.TclError) as ex:
            c.rollback()
            self.toast(str(ex), 'err')
            self.data_changed()
            return False
        if c.commit(label):
            self.toast(label, 'info')
        self.data_changed()
        return True

    def undo(self):
        label = self.save and self.save.common.undo()
        if label:
            self.toast(f'Undone: {label}', 'info')
            self.data_changed()

    def redo(self):
        label = self.save and self.save.common.redo()
        if label:
            self.toast(f'Redone: {label}', 'info')
            self.data_changed()

    def key(self, e, fn):
        # leave normal typing keys alone inside text fields
        if isinstance(e.widget, (ttk.Entry, tk.Entry)) and e.keysym in ('z', 'y', 'Delete'):
            return
        fn()
        return 'break'

    def delete_key(self):
        if self.current == 'Bag':
            self.pages['Bag'].clear()

    # ---------- files ----------
    def open(self):
        if not self.discard_ok():
            return
        d = SavePickerDialog(self).result
        if d:
            self.load(d)

    def reload(self):
        if self.save and self.discard_ok():
            self.load(self.save.folder)

    def discard_ok(self):
        if self.save and self.save.common.edited:
            return messagebox.askyesno('Unsaved edits', 'You have edits that are not saved. Discard them?', default='no')
        return True

    def load(self, d, quiet=False):
        try:
            self.save = ps.SaveFolder(d)
        except Exception as ex:
            messagebox.showerror('Cannot open', str(ex))
            return
        self.load_album()
        self.data_changed()
        self.write_settings()
        if not quiet:
            self.toast(f'Opened {self.save.folder}')

    def review(self, confirm=None):
        if not self.need():
            return False
        lines = self.save.common.pending_changes()
        return ChangesDialog(self, 'Changes to be written' if confirm else 'Pending changes', lines, confirm).result

    def save_new(self):
        if not self.need():
            return
        if not self.save.common.edited and not messagebox.askyesno('No edits', 'Nothing has been changed. Write an identical copy anyway?'):
            return
        d = filedialog.askdirectory(title='Choose an EMPTY folder for the edited save', mustexist=False)
        if not d:
            return
        try:
            t, _ = self.save.write(out_folder=d)
        except Exception as ex:
            return messagebox.showerror('Not written', str(ex))
        self.toast(f'Written and verified: {t}. Copy its contents over the live save when the emulator is closed.')

    def save_inplace(self):
        if not self.need():
            return
        if not self.save.common.edited:
            return self.toast('Nothing to save.', 'info')
        self.emus = px.running_emulators()
        if self.emus and not messagebox.askyesno('Emulator running', f'{", ".join(self.emus)} is running.\n\nIf the game is open it will overwrite this file the next time it saves, '
                                                 'and may not notice the change at all. Close it first.\n\nWrite anyway?', default='no', icon='warning'):
            return
        if not self.review('Back up and overwrite'):
            return
        try:
            t, b = self.save.write(in_place=True)
        except Exception as ex:
            return messagebox.showerror('Not written', str(ex))
        self.load(t, quiet=True)
        self.toast(f'Saved and verified. Backup of the previous save: {b}')

    def close(self):
        if self.discard_ok():
            self.write_settings()
            self.destroy()


def short_path(p):
    """C:\\Users\\me\\AppData\\Roaming\\eden\\... -> %APPDATA%\\eden\\... for display."""
    for var in ('APPDATA', 'LOCALAPPDATA', 'USERPROFILE'):
        base = os.environ.get(var)
        if base and os.path.normcase(p).startswith(os.path.normcase(base) + os.sep):
            return f'%{var}%' + p[len(base):]
    return p


class SavePickerDialog(tk.Toplevel):
    """Lists the Pokopia saves found in the usual emulator folders, with Browse for anything else."""

    def __init__(self, app):
        super().__init__(app)
        self.app, self.result, self.found = app, None, []
        P = app.P
        self.title('Open a save')
        self.configure(bg=P['bg'])
        self.geometry(f'860x400+{app.winfo_rootx() + 120}+{app.winfo_rooty() + 100}')
        self.transient(app)
        ttk.Label(self, text='Open a save', style='H.TLabel').pack(anchor='w', padx=16, pady=(14, 2))
        self.info = ttk.Label(self, text='', style='Muted.TLabel', wraplength=820, justify='left')
        self.info.pack(anchor='w', padx=16)
        row = ttk.Frame(self)
        row.pack(side='bottom', fill='x', padx=16, pady=14)
        self.b_open = ttk.Button(row, text='Open', style='Accent.TButton', command=self.ok)
        self.b_open.pack(side='right')
        ttk.Button(row, text='Cancel', command=self.destroy).pack(side='right', padx=8)
        ttk.Button(row, text='Browse for a folder...', command=self.browse).pack(side='left')
        ttk.Button(row, text='Search again', command=self.scan).pack(side='left', padx=8)
        cols = ('emu', 'saved', 'state', 'folder')
        self.tv = ttk.Treeview(self, columns=cols, show='headings', selectmode='browse', height=8)
        for c, text, w in zip(cols, ('Emulator', 'Last saved', 'Status', 'Folder'), (80, 130, 140, 480)):
            self.tv.heading(c, text=text, anchor='w')
            self.tv.column(c, width=w, anchor='w', stretch=c == 'folder')
        self.tv.pack(fill='both', expand=True, padx=16, pady=(10, 0))
        self.tv.bind('<Double-1>', lambda e: self.ok())
        self.tv.bind('<<TreeviewSelect>>', lambda e: self.update_buttons())
        self.bind('<Return>', lambda e: self.ok())
        self.bind('<Escape>', lambda e: self.destroy())
        self.scan()
        self.update_idletasks()
        dark_titlebar(self, app.theme == 'dark')
        self.grab_set()
        self.wait_window()

    def scan(self):
        self.found = px.find_saves()
        self.tv.delete(*self.tv.get_children())
        current = os.path.normcase(self.app.save.folder) if self.app.save else None
        for n, e in enumerate(self.found):
            state = 'Supported' if e['supported'] else 'Other game version'
            if current == os.path.normcase(e['folder']):
                state += ' (open)'
            self.tv.insert('', 'end', iid=str(n), values=(e['emulator'], f"{e['saved']:%d %b %Y %H:%M}", state, short_path(e['folder'])))
        if self.found:
            self.tv.selection_set('0')
            self.info.configure(text=f'Found {len(self.found)} Pokopia save{"s" if len(self.found) != 1 else ""} '
                                     'in the usual emulator folders, newest first. Pick one, or browse for another folder.')
        else:
            self.info.configure(text='No Pokopia save was found in the usual folders of Eden, Yuzu, Suyu, Sudachi, Citron, '
                                     'Torzu or Ryujinx (including a NAND folder moved in the emulator settings). '
                                     f'Use "Browse for a folder" and pick the folder that contains G00 '
                                     f'(in yuzu-family emulators it is named {px.TITLE_ID}).')
        self.update_buttons()

    def update_buttons(self):
        self.b_open.state(['!disabled'] if self.tv.selection() else ['disabled'])

    def ok(self):
        sel = self.tv.selection()
        if sel:
            self.result = self.found[int(sel[0])]['folder']
            self.destroy()

    def browse(self):
        start = self.app.save.folder if self.app.save else os.path.expanduser('~')
        d = filedialog.askdirectory(parent=self, initialdir=start, title='Select the save folder (the one containing G00)')
        if not d:
            return
        d = os.path.normpath(d)
        if os.path.basename(d).upper() in ('G00', 'B00', 'S00'):
            d = os.path.dirname(d)
        if not px.save_header(d):  # an emulator or parent folder: look inside it
            self.configure(cursor='watch'); self.update()
            hits = [e for e in px.find_saves([d], defaults=False)]
            self.configure(cursor='')
            if not hits:
                return messagebox.showerror('No save there', f'No Pokopia save (a folder containing G00\\CMNDAT.BIN) was found in\n{d}', parent=self)
            if len(hits) > 1:
                self.found = hits
                self.tv.delete(*self.tv.get_children())
                for n, e in enumerate(hits):
                    self.tv.insert('', 'end', iid=str(n), values=(e['emulator'], f"{e['saved']:%d %b %Y %H:%M}",
                                   'Supported' if e['supported'] else 'Other game version', short_path(e['folder'])))
                self.tv.selection_set('0')
                self.info.configure(text=f'Found {len(hits)} saves inside {d}. Pick one.')
                return
            d = hits[0]['folder']
        self.result = d
        self.destroy()


class ChangesDialog(tk.Toplevel):
    def __init__(self, app, title, lines, confirm=None):
        super().__init__(app)
        P = app.P
        self.result = False
        self.title(title)
        self.configure(bg=P['bg'])
        self.geometry(f'620x480+{app.winfo_rootx() + 200}+{app.winfo_rooty() + 100}')
        self.transient(app)
        ttk.Label(self, text=title, style='H.TLabel').pack(anchor='w', padx=16, pady=(14, 2))
        ttk.Label(self, text=f'{len(lines)} difference{"s" if len(lines) != 1 else ""} from the save as it was opened.', style='Muted.TLabel').pack(anchor='w', padx=16)
        row = ttk.Frame(self)
        row.pack(side='bottom', fill='x', padx=16, pady=14)
        if confirm:
            ttk.Button(row, text=confirm, style='Accent.TButton', command=self.ok).pack(side='right')
            ttk.Button(row, text='Cancel', command=self.destroy).pack(side='right', padx=8)
        else:
            ttk.Button(row, text='Close', command=self.destroy).pack(side='right')
        fr, t = scrolled(self, lambda p: tk.Text(p, bg=P['card'], fg=P['text'], bd=0, highlightthickness=0, font=(FONT, 10), padx=12, pady=10, wrap='word'))
        fr.pack(fill='both', expand=True, padx=16, pady=(10, 0))
        t.insert('1.0', '\n'.join(lines) if lines else 'Nothing has been changed.')
        t.configure(state='disabled')
        self.bind('<Escape>', lambda e: self.destroy())
        self.update_idletasks()
        dark_titlebar(self, app.theme == 'dark')
        self.grab_set()
        self.wait_window()

    def ok(self):
        self.result = True
        self.destroy()


# ============================================================ screenshots (for checking the UI)
def run_screenshots(app, outdir):
    from PIL import ImageGrab
    os.makedirs(outdir, exist_ok=True)
    app.attributes('-topmost', True)
    names = [c.nav for c in PAGES]

    def prep(name):
        if name == 'Bag':
            p = app.pages['Bag']
            p.q.set('berry')
            p.sel = {0}
            p.refresh()
        if name == 'Residents':
            tv = app.pages['Residents'].tv
            if tv.get_children():
                tv.selection_set(tv.get_children()[0])
        if name == 'Backups':
            app.pages['Backups'].compare_b00()
        if name == 'Advanced':
            app.adv_unlocked = True
            app.pages['Advanced'].unlock.set(True)
            app.pages['Advanced'].refresh()

    def busy(name):
        if name == 'Island Map':
            return not app.pages['Island Map'].current()
        if name in ('Photos', 'Overview'):
            return app.album_state == 'loading'
        return False

    def step(i, waited=0):
        if i >= len(names):
            app.destroy()
            return
        name = names[i]
        if waited == 0:
            app.show(name)
            prep(name)
        if busy(name) and waited < 150:
            return app.after(200, lambda: step(i, waited + 1))
        app.update()
        app.after(500, lambda: grab(i))

    def grab(i):
        app.update()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(os.path.join(outdir, f'{i + 1}_{names[i].replace(" & ", "_").replace(" ", "_")}_{app.theme}.png'))
        step(i + 1)

    app.after(800, lambda: step(0))


def main():
    args = sys.argv[1:]
    shot = theme = None
    if '--screenshot' in args:
        i = args.index('--screenshot')
        shot = args[i + 1]
        del args[i:i + 2]
    if '--theme' in args:
        i = args.index('--theme')
        theme = args[i + 1]
        del args[i:i + 2]
    app = App(args[0] if args else None, theme, persist=not shot)
    if shot:
        run_screenshots(app, shot)
    app.mainloop()


if __name__ == '__main__':
    main()
