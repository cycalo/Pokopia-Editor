"""Pokopia save format core (CMNDAT.BIN, version 0x0200017D / game 2.0.x).

Format notes (verified against a real save):
  * Every .BIN except S00/SYDAT.BIN is: header + zlib stream.
    - 0x00 u32 magic 0x31227687
    - 0x04 u32 version (CMNDAT 2.0.x = 0x0200017D)
    - 0x08 u32 0x00040001
    - 0x10 u32 active length = header size + compressed size
      (bytes after that are leftover padding and are ignored by the game)
    - CMNDAT header size is 0x130. No extra checksum: integrity is the zlib
      Adler-32, which zlib recomputes on every write.
  * Decompressed CMNDAT is exactly 0x470CED bytes.

Fields marked "own finding" below were located by comparing
G00 with B00 in a real save and are only ever READ, except where noted "advanced".
"""
import os, shutil, struct, sys, zlib, hashlib, datetime

MAGIC = 0x31227687
VERSION = 0x0200017D
HEADER_SIZE = 0x130
DATA_SIZE = 0x470CED
NAME_OFS, NAME_SIZE, NAME_COUNT = 0x46E0E5, 25, 9
INV_OFS, INV_COUNT, INV_MAIN, ITEM_SIZE = 0x46ECEA, 130, 120, 5
ITEM_MASK = 0x1FFF
VIL_COUNT, VIL_SIZE = 1050, 374
HOME_OFS, HOME_SIZE = 0x79824, 21
ABIL_OFS = 0x405047
FLAGS_OFS = 0x220F04
FLAG_COUNT = 250
FRIENDSHIP_MAX = 170
PUBLIC_SKILLS = [1, 2, 3, 4, 5, 6, 10, 11, 12, 13]
WHEEL_SKILLS = [1, 2, 3, 4, 5, 6, 12, 13]

SKILL_COUNT, SKILL_SIZE = 64, 8
SKILL_WHEEL_OFS, SKILL_WHEEL_COUNT = ABIL_OFS + SKILL_COUNT * SKILL_SIZE, 8
REACT_OFS, REACT_COUNT = SKILL_WHEEL_OFS + SKILL_WHEEL_COUNT, 128
REACT_WHEEL_OFS, REACT_WHEEL_COUNT = REACT_OFS + REACT_COUNT, 24
REACT_PUBLIC_MAX = 100

# own findings (read only)
PLAYTIME_OFS = 0x223269          # f64 seconds played
VIL_MET_PLAYTIME = 0x1B          # f32 play-time seconds when the resident joined
VIL_MET_DATE = 0x16A             # 6 x u16: year, month, day, hour, minute, second

# Own finding, confirmed in game 2026-11-11: one byte per item ID ("obtained" catalog). Normal items
# use 0x43; outfits and hairstyles are item IDs with no name in the item list and the game marks
# them owned with 1. Setting every one of these to 1 unlocked all 27 outfits plus extra hairstyles.
CATALOG_OFS = 0x402ED9
WARDROBE_IDS = list(range(2389, 2434)) + list(range(2439, 2446)) + list(range(2452, 2501))
WARDROBE_OWNED = 1
# IDs follow the order the game's mirror lists them (own finding, 2026-11-11).
# Outfits: 2397 + position, confirmed in game at 2400, 2403, 2404, 2407, 2411, 2421.
OUTFITS = [(2397 + n, name) for n, name in enumerate([
    'Familiar 1', 'Familiar 2', 'Pokémon Center', 'Team Rocket', 'Rock-solid', 'Ranger', 'Ninja',
    'Psychic Master', 'Black Belt', 'Sailor', 'Super Nerd', 'Roughneck', 'Bird Keeper', 'Red', 'Fresh',
    'Cool', 'Rascal', 'Cozy', 'Sporty', 'Chic', 'Professor', 'Sightseer', 'Mermaid', 'Preschooler'], 1)]
# Hairstyles: mirror order, Shaved is a default with no ID found. Confirmed in game at 2461 Parted,
# 2463 Mermaid, 2472 Side tails; 2459 showed nothing new (Locs is a default). The rest follow the order.
HAIRSTYLES = list(zip(range(2454, 2461), ['Short', 'Pigtails', 'Buns', 'Two-block cut', 'Braided pigtails',
                                          'Locs', 'Curly'])) + [(None, 'Shaved')] + \
    list(zip(range(2461, 2473), ['Parted', 'Fluffy', 'Mermaid', 'Winged pigtails', 'Sideswept', 'Simple',
                                 'Long bangs', 'Long', 'Crested', 'Ponytail', 'Messy short', 'Side tails']))
# available without being stored as owned (Familiar 1/2 and the starting hairstyles)
WARDROBE_DEFAULTS = {2398, 2399, 2454, 2455, 2456, 2457, 2458, 2459, None}
WARDROBE_CONFIRMED = {2400, 2403, 2404, 2407, 2411, 2414, 2421, 2460, 2461, 2463, 2466, 2472}
KNOWN_WARDROBE = {i: f'{n} outfit' for i, n in OUTFITS}
KNOWN_WARDROBE.update({i: f'{n} hairstyle' for i, n in HAIRSTYLES if i})


def wardrobe_lookup(text):
    """Item ID for an outfit/hairstyle name or number, e.g. 'Ranger', 'outfit:Mermaid', 'hair:mermaid', '2403'."""
    t = text.strip().lower()
    if t.isdigit():
        i = int(t)
        if i not in WARDROBE_IDS:
            raise ValueError(f'{i} is not a wardrobe entry')
        return i
    kind, _, name = t.rpartition(':')
    pools = {'outfit': OUTFITS, 'hair': HAIRSTYLES, 'hairstyle': HAIRSTYLES}
    pool = pools.get(kind, OUTFITS + HAIRSTYLES)
    hits = [i for i, n in pool if n.lower() == name]
    if len(hits) > 1:
        raise ValueError(f'"{text}" is both an outfit and a hairstyle; write outfit:{name} or hair:{name}')
    if not hits or hits[0] is None:
        raise ValueError(f'No unlockable outfit or hairstyle called "{text}"')
    return hits[0]

# function flags with known behaviour
KNOWN_FLAGS = {
    54: 'Liquid absorption (Water Gun)',
    56: 'Surf permission',
    57: 'Glide permission',
    71: 'Leafage food boost',
    72: 'Cut food boost',
    73: 'Water Gun food boost',
    74: 'Rock Smash food boost',
    125: 'Rock Smash extra food effect',
    148: 'Dive (Surf)',
    153: 'Surf food boost',
}
# key -> (label, flags to set, required learned move, required other extra)
EXTRAS = {
    'absorb': ('Liquid Absorption', (54,), 3, None),
    'dive': ('Dive', (148,), 10, None),
    'boost1': ('Leafage food boost', (71,), 1, None),
    'boost5': ('Cut food boost', (72,), 5, None),
    'boost3': ('Water Gun food boost', (73,), 3, None),
    'boost4': ('Rock Smash food boost', (74, 125), 4, None),
    'boost10': ('Surf food boost', (153,), 10, 'dive'),
}

HERE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))  # bundle dir in the exe


def _names(kind):
    p = os.path.join(HERE, 'data', kind + '.txt')
    try:
        with open(p, encoding='utf-8') as f:
            return f.read().replace('\r', '').split('\n')
    except OSError:
        return []


ITEM_NAMES = _names('item')
VILLAGER_NAMES = _names('villager')
SKILL_NAMES = _names('skill')
AREA_NAMES = _names('area')
REACTION_NAMES = _names('reaction')
PUBLIC_REACTIONS = [i for i in range(1, min(REACT_PUBLIC_MAX + 1, len(REACTION_NAMES))) if REACTION_NAMES[i].strip()]


def name_of(lst, i, prefix):
    if 0 <= i < len(lst) and lst[i].strip():
        return lst[i]
    return f'{prefix} {i}'


def item_name(i):
    return name_of(ITEM_NAMES, i, 'Item') if i else '(empty)'


def fmt_playtime(sec):
    sec = int(sec)
    return f'{sec // 3600}h {sec % 3600 // 60:02}m'


class FormatError(Exception):
    pass


class CommonSave:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.original = f.read()
        o = self.original
        if len(o) < HEADER_SIZE:
            raise FormatError('File too small')
        magic, ver, v8 = struct.unpack_from('<III', o, 0)
        if magic != MAGIC:
            raise FormatError(f'Bad magic {magic:#x}')
        if ver != VERSION:
            raise FormatError(f'Unsupported CMNDAT version {ver:#010x} (supported {VERSION:#010x}). Refusing to edit.')
        if v8 != 0x40001:
            raise FormatError(f'Unexpected header field {v8:#x}')
        length = struct.unpack_from('<I', o, 0x10)[0]
        if not (HEADER_SIZE < length <= len(o)):
            raise FormatError('Compressed length field is invalid')
        d = zlib.decompressobj()
        try:
            raw = d.decompress(o[HEADER_SIZE:length])
        except zlib.error as e:
            raise FormatError(f'zlib error: {e}')
        if not d.eof or d.unused_data:
            raise FormatError('zlib stream does not end exactly at the length field')
        if len(raw) != DATA_SIZE:
            raise FormatError(f'Decompressed size {len(raw)} != expected {DATA_SIZE}')
        self.orig_data = raw
        self.data = bytearray(raw)
        self._shadow = bytearray(raw)
        self._undo, self._redo = [], []
        self.player_name  # validate

    @classmethod
    def from_data(cls, raw):
        """A file-less view over decompressed data (for comparisons)."""
        self = cls.__new__(cls)
        self.path = self.original = None
        self.orig_data = bytes(raw)
        self.data = bytearray(raw)
        self._shadow = bytearray(raw)
        self._undo, self._redo = [], []
        return self

    def pending_changes(self):
        """What the edits made so far change, as readable lines."""
        return describe_changes(CommonSave.from_data(self.orig_data), self)

    # ---------- generic ----------
    @property
    def edited(self):
        return bytes(self.data) != self.orig_data

    def to_bytes(self):
        if not self.edited:
            return self.original
        comp = zlib.compress(bytes(self.data), 1)  # level 1 matches the game's own output
        length = HEADER_SIZE + len(comp)
        out = bytearray(max(length, len(self.original)))
        out[:HEADER_SIZE] = self.original[:HEADER_SIZE]
        out[HEADER_SIZE:length] = comp
        struct.pack_into('<I', out, 0x10, length)
        return bytes(out)

    # ---------- undo / redo journal ----------
    def commit(self, label):
        """Record everything changed since the last commit as one undo step. Returns True if anything changed."""
        patches = _diff_patches(self._shadow, self.data)
        if not patches:
            return False
        for ofs, _, new in patches:
            self._shadow[ofs:ofs + len(new)] = new
        self._undo.append((label, patches))
        self._redo.clear()
        return True

    def rollback(self):
        """Drop uncommitted changes (used when an edit fails half way)."""
        for ofs, old, _ in _diff_patches(self._shadow, self.data):
            self.data[ofs:ofs + len(old)] = old

    def undo(self):
        if not self._undo:
            return None
        label, patches = self._undo.pop()
        for ofs, old, _ in patches:
            self.data[ofs:ofs + len(old)] = old
            self._shadow[ofs:ofs + len(old)] = old
        self._redo.append((label, patches))
        return label

    def redo(self):
        if not self._redo:
            return None
        label, patches = self._redo.pop()
        for ofs, _, new in patches:
            self.data[ofs:ofs + len(new)] = new
            self._shadow[ofs:ofs + len(new)] = new
        self._undo.append((label, patches))
        return label

    @property
    def history(self):
        return [label for label, _ in self._undo]

    @property
    def can_redo(self):
        return bool(self._redo)

    # ---------- player ----------
    def _read_name(self, ofs):
        b = bytes(self.data[ofs:ofs + NAME_SIZE])
        if 0 not in b:
            raise FormatError('Player name not terminated')
        return b[:b.index(0)].decode('utf-8')

    @property
    def player_name(self):
        for i in range(NAME_COUNT):
            ofs = NAME_OFS + i * NAME_SIZE
            if self.data[ofs]:
                return self._read_name(ofs)
        return self._read_name(NAME_OFS)

    @player_name.setter
    def player_name(self, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Name must be non-empty with no control characters')
        b = value.encode('utf-8')
        if len(b) >= NAME_SIZE:
            raise ValueError(f'Name must be at most {NAME_SIZE - 1} UTF-8 bytes')
        old = self.player_name
        for i in range(NAME_COUNT):
            ofs = NAME_OFS + i * NAME_SIZE
            if self._read_name(ofs) == old:
                self.data[ofs:ofs + NAME_SIZE] = b.ljust(NAME_SIZE, b'\0')

    @property
    def play_seconds(self):
        """Own finding, read only. Returns None if the value does not look like a play time."""
        v = struct.unpack_from('<d', self.data, PLAYTIME_OFS)[0]
        return v if 0 <= v < 3.6e7 else None

    # ---------- inventory ----------
    def get_slot(self, i):
        ofs = INV_OFS + i * ITEM_SIZE
        rawv = struct.unpack_from('<I', self.data, ofs)[0]
        return rawv & ITEM_MASK, self.data[ofs + 4], rawv

    def set_slot(self, i, item_id, count):
        if not 0 <= i < INV_COUNT:
            raise ValueError('Slot out of range')
        if not 0 <= item_id <= ITEM_MASK:
            raise ValueError('Item ID out of range (0-8191)')
        if not 0 <= count <= 255:
            raise ValueError('Count must be 0-255')
        ofs = INV_OFS + i * ITEM_SIZE
        if item_id == 0 or count == 0:
            self.data[ofs:ofs + 5] = b'\0' * 5
            return
        cur_id, _, rawv = self.get_slot(i)
        if cur_id != item_id:
            rawv = 0  # variant/placement bits belong to the old item
        rawv = (rawv & ~ITEM_MASK) | item_id
        struct.pack_into('<IB', self.data, ofs, rawv, count)

    def filled_slots(self):
        return [i for i in range(INV_COUNT) if self.get_slot(i)[0]]

    def first_empty(self, start=0, end=INV_MAIN):
        for i in range(start, end):
            if self.get_slot(i)[0] == 0:
                return i
        return None

    def add_item(self, item_id, count):
        """Put an item in the first empty main slot. Returns the slot."""
        if item_id == 0 or count == 0:
            raise ValueError('Pick an item and a count above 0')
        i = self.first_empty()
        if i is None:
            raise ValueError('No empty slot in the main bag')
        self.set_slot(i, item_id, count)
        return i

    def set_count(self, i, count):
        item_id = self.get_slot(i)[0]
        if item_id:
            self.set_slot(i, item_id, count)

    def swap_slots(self, i, j):
        for k in (i, j):
            if not 0 <= k < INV_COUNT:
                raise ValueError('Slot out of range')
        a, b = INV_OFS + i * ITEM_SIZE, INV_OFS + j * ITEM_SIZE
        ra, rb = bytes(self.data[a:a + 5]), bytes(self.data[b:b + 5])
        self.data[a:a + 5], self.data[b:b + 5] = rb, ra

    def sort_main(self, by_name=False):
        """Pack the main bag to the front, ordered by item ID or name. The second bar is left alone."""
        recs = []
        for i in range(INV_MAIN):
            ofs = INV_OFS + i * ITEM_SIZE
            if self.get_slot(i)[0]:
                recs.append(bytes(self.data[ofs:ofs + 5]))
        ident = lambda r: struct.unpack_from('<I', r)[0] & ITEM_MASK
        recs.sort(key=(lambda r: (item_name(ident(r)).lower(), ident(r))) if by_name else ident)
        recs += [b'\0' * 5] * (INV_MAIN - len(recs))
        self.data[INV_OFS:INV_OFS + INV_MAIN * ITEM_SIZE] = b''.join(recs)

    def export_bag(self):
        return [dict(slot=i, id=self.get_slot(i)[0], count=self.get_slot(i)[1], name=item_name(self.get_slot(i)[0]))
                for i in self.filled_slots()]

    def import_bag(self, entries, clear=True):
        entries = [(int(e['slot']), int(e['id']), int(e['count'])) for e in entries]
        for slot, item_id, count in entries:  # validate everything before touching data
            if not (0 <= slot < INV_COUNT and 0 < item_id <= ITEM_MASK and 0 < count <= 255):
                raise ValueError(f'Bad preset entry: slot {slot}, item {item_id}, count {count}')
        if clear:
            self.data[INV_OFS:INV_OFS + INV_COUNT * ITEM_SIZE] = bytes(INV_COUNT * ITEM_SIZE)
        for slot, item_id, count in entries:
            self.set_slot(slot, item_id, count)

    # ---------- villagers ----------
    def villager_present(self, i):
        b = self.data[i * VIL_SIZE + 1:i * VIL_SIZE + 17]
        return any(b)

    def villagers(self):
        return [i for i in range(VIL_COUNT) if self.villager_present(i)]

    def get_villager(self, i):
        o = i * VIL_SIZE
        d = self.data
        fr, thank = struct.unpack_from('<HH', d, o + 0x11)
        h = HOME_OFS + i * HOME_SIZE
        htype = d[h]
        stage = d[h + 3]
        y, mo, da, hh, mi, ss = struct.unpack_from('<6H', d, o + VIL_MET_DATE)
        met = None
        if 2020 <= y < 2100 and 1 <= mo <= 12 and 1 <= da <= 31 and hh < 24 and mi < 60 and ss < 60:
            try:
                met = datetime.datetime(y, mo, da, hh, mi, ss)
            except ValueError:
                met = None
        pt = struct.unpack_from('<f', d, o + VIL_MET_PLAYTIME)[0]
        return dict(index=i, name=name_of(VILLAGER_NAMES, i, 'Resident'), friendship=fr, thank_points=thank,
                    present_level=d[o + 0x15], waiting_present=bool(d[o + 0x16]),
                    name_talk_done=bool(d[o + 0xC4]), home_type=htype, home_area=stage,
                    home_area_name=name_of(AREA_NAMES, stage, 'Area') if htype else '',
                    home_uid=struct.unpack_from('<H', d, h + 1)[0],
                    home_xyz=struct.unpack_from('<3h', d, h + 6) if htype else None,
                    met=met, met_playtime=pt if 0 < pt < 3.6e7 else None)

    def _need_villager(self, i):
        if not (0 <= i < VIL_COUNT and self.villager_present(i)):
            raise ValueError('That resident is not in this save')

    def set_friendship(self, i, value):
        self._need_villager(i)
        if not 0 <= value <= 0xFFFF:
            raise ValueError('Friendship must be 0-65535')
        struct.pack_into('<H', self.data, i * VIL_SIZE + 0x11, value)

    def set_name_talk_done(self, i, done):
        self._need_villager(i)
        self.data[i * VIL_SIZE + 0xC4] = 1 if done else 0

    def set_thank_points(self, i, value):
        """Advanced: unverified, normally read only."""
        self._need_villager(i)
        if not 0 <= value <= 0xFFFF:
            raise ValueError('Thank points must be 0-65535')
        struct.pack_into('<H', self.data, i * VIL_SIZE + 0x13, value)

    def set_present_level(self, i, value):
        """Advanced: unverified, normally read only."""
        self._need_villager(i)
        if not 0 <= value <= 255:
            raise ValueError('Present level must be 0-255')
        self.data[i * VIL_SIZE + 0x15] = value

    # ---------- function flags ----------
    def get_flag(self, i):
        if not 1 <= i < FLAG_COUNT:
            raise ValueError(f'Flag must be 1-{FLAG_COUNT - 1}')
        return bool(self.data[FLAGS_OFS + (i >> 3)] >> (i & 7) & 1)

    def set_flag(self, i, on):
        if not 1 <= i < FLAG_COUNT:
            raise ValueError(f'Flag must be 1-{FLAG_COUNT - 1}')
        if on:
            self.data[FLAGS_OFS + (i >> 3)] |= 1 << (i & 7)
        else:
            self.data[FLAGS_OFS + (i >> 3)] &= ~(1 << (i & 7)) & 0xFF

    def flags_set(self):
        return [i for i in range(1, FLAG_COUNT) if self.get_flag(i)]

    # ---------- moves ----------
    def skill(self, i):
        uses, flag = struct.unpack_from('<IB', self.data, ABIL_OFS + i * 8)
        learned = bool(flag & 1)
        if i == 10:
            learned = learned and bool(self.data[FLAGS_OFS + 7] & 1)
        if i == 11:
            learned = learned and bool(self.data[FLAGS_OFS + 7] & 2)
        return uses, learned

    def wheel(self):
        return list(self.data[SKILL_WHEEL_OFS:SKILL_WHEEL_OFS + SKILL_WHEEL_COUNT])

    def learn_skill(self, i):
        if i not in PUBLIC_SKILLS:
            raise ValueError(f'Move {i} is not a supported move ({PUBLIC_SKILLS})')
        if i == 10:
            self.data[FLAGS_OFS + 7] |= 1
        if i == 11:
            self.data[FLAGS_OFS + 7] |= 2
        ofs = ABIL_OFS + i * 8 + 4
        if self.data[ofs] & 1:
            return
        self.data[ofs] |= 1
        if i in WHEEL_SKILLS:
            w = SKILL_WHEEL_OFS
            wheel = self.data[w:w + 8]
            if i not in wheel and 0 in wheel:
                self.data[w + wheel.index(0)] = i

    def forget_skill(self, i):
        """Unlearn a move: clears it, takes it off the move wheel and switches off the extras that need it
        (e.g. its food boost, Dive and the Surf food boost for Surf). The use counter is kept."""
        if i not in PUBLIC_SKILLS:
            raise ValueError(f'Move {i} is not a supported move ({PUBLIC_SKILLS})')
        self.data[ABIL_OFS + i * 8 + 4] &= 0xFE
        if i == 10:
            self.data[FLAGS_OFS + 7] &= 0xFE
        if i == 11:
            self.data[FLAGS_OFS + 7] &= 0xFD
        w = SKILL_WHEEL_OFS
        for k in range(SKILL_WHEEL_COUNT):
            if self.data[w + k] == i:
                self.data[w + k] = 0
        gone = {key for key, (_, _, move, _) in EXTRAS.items() if move == i}
        gone |= {key for key, (_, _, _, other) in EXTRAS.items() if other in gone}
        for key in gone:
            for f in EXTRAS[key][1]:
                self.set_flag(f, False)

    def set_skill_slot(self, slot, move):
        if not 0 <= slot < SKILL_WHEEL_COUNT:
            raise ValueError('Wheel slot out of range')
        if move and not (move in WHEEL_SKILLS and self.skill(move)[1]):
            raise ValueError('Choose a learned wheel move or leave the slot empty')
        w = SKILL_WHEEL_OFS
        cur = self.data[w + slot]
        if cur == move:
            return
        if move:
            for k in range(SKILL_WHEEL_COUNT):
                if k != slot and self.data[w + k] == move:
                    self.data[w + k] = cur  # swap
        self.data[w + slot] = move

    # ---------- move extras (food boosts, Dive, Liquid Absorption) ----------
    def extra(self, key):
        return all(self.get_flag(f) for f in EXTRAS[key][1])

    def extra_blocker(self, key):
        """Why this extra cannot be unlocked yet, or '' if it can."""
        _, _, move, other = EXTRAS[key]
        if not self.skill(move)[1]:
            return f'Learn {name_of(SKILL_NAMES, move, "Move")} first'
        if other and not self.extra(other):
            return f'Unlock {EXTRAS[other][0]} first'
        return ''

    def set_extra(self, key, on=True):
        if key not in EXTRAS:
            raise ValueError(f'Unknown unlock {key!r} ({", ".join(EXTRAS)})')
        if on:
            why = self.extra_blocker(key)
            if why:
                raise ValueError(why + '.')
        for f in EXTRAS[key][1]:
            self.set_flag(f, on)

    # ---------- emotes (the game calls them reactions) ----------
    def reaction_learned(self, i):
        return bool(self.data[REACT_OFS + i] & 1)

    def reactions_learned(self):
        return [i for i in range(REACT_COUNT) if self.reaction_learned(i)]

    def reaction_wheel(self):
        return [self.data[REACT_WHEEL_OFS + k * 2] for k in range(REACT_WHEEL_COUNT)]

    def learn_reaction(self, i):
        if i not in PUBLIC_REACTIONS:
            raise ValueError('Choose an emote from the list')
        if self.reaction_learned(i):
            return
        self.data[REACT_OFS + i] |= 1
        wheel = self.reaction_wheel()
        if i not in wheel and 0 in wheel:
            k = wheel.index(0)
            self.data[REACT_WHEEL_OFS + k * 2] = i
            self.data[REACT_WHEEL_OFS + k * 2 + 1] = 0

    # ---------- item catalog (read only for normal items) ----------
    def catalog_state(self, item_id):
        """Raw catalog byte for an item (0 = never obtained). Read only: the editor never writes it for normal items."""
        return self.data[CATALOG_OFS + item_id] if 0 < item_id < len(ITEM_NAMES) else 0

    def catalog_items(self):
        """Set of item IDs the item catalog marks as obtained (wardrobe entries excluded)."""
        base, wid = CATALOG_OFS, set(WARDROBE_IDS)
        blk = self.data[base:base + len(ITEM_NAMES)]
        return {i for i, v in enumerate(blk) if v and i and i not in wid}

    # ---------- wardrobe (outfits and hairstyles) ----------
    def wardrobe_owned(self, item_id):
        return self.data[CATALOG_OFS + item_id] != 0

    def wardrobe_available(self, item_id):
        """Owned, or available from the start without being stored."""
        return item_id in WARDROBE_DEFAULTS or self.wardrobe_owned(item_id)

    def wardrobe_unlocked(self):
        return [i for i in WARDROBE_IDS if self.wardrobe_owned(i)]

    def unlock_wardrobe(self, ids=None):
        """Mark outfits/hairstyles as owned (all of them by default). Entries already set are left alone."""
        for i in WARDROBE_IDS if ids is None else ids:
            if i not in WARDROBE_IDS:
                raise ValueError(f'{i} is not a wardrobe entry')
            if not self.wardrobe_owned(i):
                self.data[CATALOG_OFS + i] = WARDROBE_OWNED

    def lock_wardrobe(self, ids):
        """Mark outfits/hairstyles as not owned again. Starting outfits/hairstyles cannot be removed."""
        for i in ids:
            if i not in WARDROBE_IDS:
                raise ValueError(f'{i} is not a wardrobe entry')
            if i in WARDROBE_DEFAULTS:
                raise ValueError(f'{KNOWN_WARDROBE.get(i, i)} is available from the start and cannot be removed')
            self.data[CATALOG_OFS + i] = 0

    def forget_reaction(self, i):
        """Unlearn an emote and take it off the emote wheel."""
        if i not in PUBLIC_REACTIONS:
            raise ValueError('Choose an emote from the list')
        self.data[REACT_OFS + i] &= 0xFE
        for k in range(REACT_WHEEL_COUNT):
            if self.data[REACT_WHEEL_OFS + k * 2] == i:
                self.data[REACT_WHEEL_OFS + k * 2:REACT_WHEEL_OFS + k * 2 + 2] = b'\0\0'

    def set_reaction_slot(self, slot, emote):
        if not 0 <= slot < REACT_WHEEL_COUNT:
            raise ValueError('Wheel slot out of range')
        if emote and not (emote in PUBLIC_REACTIONS and self.reaction_learned(emote)):
            raise ValueError('Choose a learned emote or leave the slot empty')
        w = REACT_WHEEL_OFS
        if self.data[w + slot * 2] == emote:
            return
        for k in range(REACT_WHEEL_COUNT):
            if emote and k != slot and self.data[w + k * 2] == emote:
                a, b = w + slot * 2, w + k * 2  # move both saved bytes with the emote
                pa, pb = bytes(self.data[a:a + 2]), bytes(self.data[b:b + 2])
                self.data[a:a + 2], self.data[b:b + 2] = pb, pa
                return
        self.data[w + slot * 2] = emote
        self.data[w + slot * 2 + 1] = 0


def _diff_patches(old, new, page=4096):
    """[(offset, old_bytes, new_bytes)] for every differing run. Fast: only differing 4 KB pages are scanned."""
    out = []
    for p in range(0, len(new), page):
        a, b = old[p:p + page], new[p:p + page]
        if a == b:
            continue
        i, n = 0, len(a)
        while i < n:
            if a[i] != b[i]:
                j = i + 1
                while j < n and a[j] != b[j]:
                    j += 1
                out.append((p + i, bytes(a[i:j]), bytes(b[i:j])))
                i = j
            else:
                i += 1
    return out


def describe_changes(a, b, limit=400):
    """Human readable list of what differs going from save `a` to save `b` (both CommonSave)."""
    out = []
    if a.player_name != b.player_name:
        out.append(f'Player name: {a.player_name} -> {b.player_name}')
    pa, pb = a.play_seconds, b.play_seconds
    if pa is not None and pb is not None and int(pa) != int(pb):
        out.append(f'Play time: {fmt_playtime(pa)} -> {fmt_playtime(pb)}')
    for i in range(INV_COUNT):
        (ia, ca, _), (ib, cb, _) = a.get_slot(i), b.get_slot(i)
        if (ia, ca) != (ib, cb):
            fa = f'{item_name(ia)} x{ca}' if ia else 'empty'
            fb = f'{item_name(ib)} x{cb}' if ib else 'empty'
            out.append(f'Bag slot {i}: {fa} -> {fb}')
    va, vb = set(a.villagers()), set(b.villagers())
    for i in sorted(vb - va):
        out.append(f'New resident: {name_of(VILLAGER_NAMES, i, "Resident")}')
    for i in sorted(va - vb):
        out.append(f'Resident gone: {name_of(VILLAGER_NAMES, i, "Resident")}')
    for i in sorted(va & vb):
        x, y = a.get_villager(i), b.get_villager(i)
        for key, label in (('friendship', 'friendship'), ('thank_points', 'thank points'), ('present_level', 'present level'),
                           ('name_talk_done', 'name talk done'), ('home_area_name', 'home area')):
            if x[key] != y[key]:
                out.append(f'{x["name"]}: {label} {x[key] or "-"} -> {y[key] or "-"}')
    for i in PUBLIC_SKILLS:
        if a.skill(i)[1] != b.skill(i)[1]:
            out.append(f'Move {name_of(SKILL_NAMES, i, "Move")}: {"learned" if b.skill(i)[1] else "forgotten"}')
    if a.wheel() != b.wheel():
        fmt = lambda w: ', '.join(name_of(SKILL_NAMES, m, 'Move') if m else '-' for m in w)
        out.append(f'Move wheel: [{fmt(a.wheel())}] -> [{fmt(b.wheel())}]')
    for i in range(REACT_COUNT):
        if a.reaction_learned(i) != b.reaction_learned(i):
            out.append(f'Emote {name_of(REACTION_NAMES, i, "Emote")}: {"learned" if b.reaction_learned(i) else "forgotten"}')
    if a.reaction_wheel() != b.reaction_wheel():
        out.append('Emote wheel layout changed')
    wa, wb = a.wardrobe_unlocked(), b.wardrobe_unlocked()
    if wa != wb:
        def names(ids):
            n = [KNOWN_WARDROBE.get(i, f'entry {i}') for i in ids]
            return ', '.join(n[:6]) + (f' and {len(n) - 6} more' if len(n) > 6 else '')
        new = [i for i in wb if i not in wa]
        gone = [i for i in wa if i not in wb]
        out.append(f'Outfits & hairstyles: {len(wa)} -> {len(wb)} of {len(WARDROBE_IDS)} unlocked'
                   + (f' (new: {names(new)})' if new else '') + (f' (removed: {names(gone)})' if gone else ''))
    for i in range(1, FLAG_COUNT):
        if a.get_flag(i) != b.get_flag(i):
            out.append(f'Flag {i} ({KNOWN_FLAGS.get(i, "unknown")}): {"on" if b.get_flag(i) else "off"}')
    if len(out) > limit:
        out = out[:limit] + [f'... and {len(out) - limit} more']
    return out


class SaveFolder:
    REL = os.path.join('G00', 'CMNDAT.BIN')

    def __init__(self, folder):
        folder = os.path.abspath(folder)
        if os.path.basename(folder).upper() in ('G00', 'B00', 'S00'):
            folder = os.path.dirname(folder)
        if not os.path.isfile(os.path.join(folder, self.REL)):
            raise FormatError('Pick the save folder that contains G00 (and S00), e.g. ...\\0400A3A01EE4C000')
        self.folder = folder
        self.common = CommonSave(os.path.join(folder, self.REL))

    def game_backup(self):
        """The game's own previous save (B00), or None."""
        p = os.path.join(self.folder, 'B00', 'CMNDAT.BIN')
        try:
            return CommonSave(p) if os.path.isfile(p) else None
        except FormatError:
            return None

    def stage_files(self):
        """{area number: path} for every G00/STGDAT##.BIN."""
        out = {}
        g = os.path.join(self.folder, 'G00')
        for fn in sorted(os.listdir(g)):
            u = fn.upper()
            if len(u) == 12 and u.startswith('STGDAT') and u.endswith('.BIN') and u[6:8].isdigit():
                out[int(u[6:8])] = os.path.join(g, fn)
        return out

    def photo_file(self):
        p = os.path.join(self.folder, 'G00', 'SCSHDAT.BIN')
        return p if os.path.isfile(p) else None

    def changed_on_disk(self):
        """True if the game (or anything else) rewrote CMNDAT.BIN since this save was opened."""
        try:
            with open(self.common.path, 'rb') as f:
                return f.read() != self.common.original
        except OSError:
            return True

    def write(self, out_folder=None, in_place=False, backup_root=None):
        """Write to a new folder (default) or in place after an automatic backup. Returns (path, backup)."""
        if in_place and self.changed_on_disk():
            raise ValueError('The save on disk changed after it was opened (the game saved again). Reopen it first.')
        new_bytes = self.common.to_bytes()
        # validate what we are about to write
        _validate_bytes(new_bytes, bytes(self.common.data))
        backup = None
        if in_place:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_root = backup_root or default_backup_root()
            backup = os.path.join(backup_root, 'auto_' + ts)
            shutil.copytree(self.folder, backup)
            target = self.folder
        else:
            if not out_folder:
                raise ValueError('Output folder required')
            out_folder = os.path.abspath(out_folder)
            if os.path.normcase(out_folder) == os.path.normcase(self.folder):
                raise ValueError('Output folder is the input folder. Use in-place mode instead.')
            if os.path.exists(out_folder) and os.listdir(out_folder):
                raise ValueError('Output folder must be new or empty')
            shutil.copytree(self.folder, out_folder, dirs_exist_ok=True)
            target = out_folder
        dst = os.path.join(target, self.REL)
        tmpf = dst + '.tmp'
        with open(tmpf, 'wb') as f:
            f.write(new_bytes)
        os.replace(tmpf, dst)
        # re-read from disk and compare
        again = CommonSave(dst)
        if bytes(again.data) != bytes(self.common.data):
            raise FormatError('Verification after write failed')
        return target, backup


def default_backup_root():
    return os.path.join(os.path.expanduser('~'), 'Documents', 'Pokopia_Save_Backups')


def _validate_bytes(b, expected_data):
    length = struct.unpack_from('<I', b, 0x10)[0]
    raw = zlib.decompress(b[HEADER_SIZE:length])
    if raw != expected_data or struct.unpack_from('<I', b, 0)[0] != MAGIC:
        raise FormatError('Re-encoded save failed validation, nothing written')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()
