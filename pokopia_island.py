# Linux port modifications by frinimini, 2026-11-25. See CREDITS.md.
"""Editable islands (G00/STGDAT##.BIN): terrain blocks, placed objects, habitats and the separate areas in each file.

Island file layout (decompressed, own findings from real saves, 2026-11-18):
- 0x58571B  64 x 64 u16 chunk map (chunk index = cz * 64 + cx -> storage slot, 0xFFFF = no chunk). Chunk = 32 x 32 columns.
- 0x58771F  i32 count of placed-object records in use (record 0 is an empty dummy).
- 0x587723  placed-object pool, 0xC8000 x 16 bytes: u32 link, u32 location, u32 state, u32 extra.
            location = variation (12 bits) | flag << 12 | x << 13 | y << 18 | z << 25 | direction << 30 (x, z inside the chunk)
            state    = kind (4 bits) | handle << 4 (20 bits) | flags << 24
            link     = index of the previous record in the same chunk, 0xFFFFFFFF for the first one.
            The game loads handle h < count from record points[h] when that index is below the count too
            (confirmed in game 2026-11-18: records whose handle was not below the count did not appear).
            Removed objects leave a hole in place: variation 0 and a handle at or above the count; the record
            past the count keeps the freed handle. Records are never moved.
- 0x1207723 handle table, 0xC8000 x u32: (record index << 12) | chunk index (chunk 0 for free handles).
- 0x4C0640  habitats, 924 x 26 bytes: i16 min xyz, max xyz, home xyz, u32 habitat type, 4 bytes. Habitat uid = 101 + row.
- 0x23FFEDC voxel grid, one 32 x 128 x 32 block of 3-byte cells per slot, index (y * 1024 + z * 32 + x).
            cell = block id (11 bits) | flags << 11. 0 = air, 1 = bedrock (y = 0), 0x7FF = space taken by a placed object.
            Flag 0x200 marks cells the player placed. Liquids keep their fill level (0x1F = full) in the low flag bits.
            Some objects (fences, roofs, partitions...) fill their space with a dedicated collision block id instead of 0x7FF.

Block ids are named through data/blocks.bin (tools/extract_block_table.py), placed objects through data/map_parts.bin.
Writes keep the 0x124-byte header and update the compressed length at 0x10, like the game does.
"""
import array
import os
import struct
import sys
import zlib
from collections import Counter

import pokopia_extras as px
import pokopia_save as ps

HERE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')

VERSION = 0x0300018B
HEADER = 0x124
DATA_SIZE = 0x83FFDB8
CHUNK_MAP = 0x58571B
PART_COUNT = 0x58771F
PART_POOL = 0x587723
PART_CAP = 0xC8000
POINTS = 0x1207723
HABITATS = 0x4C0640
HABITAT_SIZE = 26
HABITAT_CAP = 924
GRID = 0x23FFEDC
CHUNK_BYTES = 0x20000 * 3
PLANE = 1024 * 3
ZERO_PLANE = bytes(PLANE)

AIR, BEDROCK, OBJECT = 0, 1, 0x7FF
ID_MASK = 0x7FF
PLAYER = 0x200 << 11          # "placed by the player" cell flag
FREE_LINK = 0xFFFFFFFF
# Read-only treasure position table. Verified against a known glowing spot before
# breaking, after breaking, and after collecting its drop on 2026-11-25.
# The fourth u16 and the surrounding counters are not yet decoded.
GLOWING_POSITIONS = 0x15CF36
GLOWING_SLOTS = 25
NO_DATA = 255
SEA_LEVEL = 31
COMPRESS_LEVEL = 9            # smaller than the game's own file; the game reads any zlib stream

# block kinds (data/blocks.bin)
K_NONE, K_TERRAIN, K_BUILD, K_LIQUID = 0, 1, 2, 3
# cell classes used while scanning
C_AIR, C_SOLID, C_LIQUID, C_OBJECT = 0, 1, 2, 3

_BLOCKS = None


def _blocks():
    global _BLOCKS
    if _BLOCKS is None:
        tab = [(0, K_NONE)] * 2048
        try:
            with open(os.path.join(DATA, 'blocks.bin'), 'rb') as f:
                b = f.read()
            if len(b) == 2048 * 4:
                tab = [(it, k) for it, k, _ in struct.iter_unpack('<HBB', b)]
        except OSError:
            pass
        _BLOCKS = tab
    return _BLOCKS


def block_item(bid):
    return _blocks()[bid & ID_MASK][0]


def block_kind(bid):
    return _blocks()[bid & ID_MASK][1]


def block_name(bid):
    bid &= ID_MASK
    if bid == AIR:
        return 'air'
    if bid == BEDROCK:
        return 'bedrock'
    if bid == OBJECT:
        return 'placed object'
    item, kind = _blocks()[bid]
    if kind and item:
        return ps.item_name(item)
    return f'block {bid}'


def paintable_blocks():
    """[(block id, item id, kind)] that the paint tool offers: terrain and building blocks."""
    return [(b, it, k) for b, (it, k) in enumerate(_blocks()) if it and k in (K_TERRAIN, K_BUILD)]


def local_to_world(x, z, d, u, v):
    """Cell (u along the width, v along the depth) of an object anchored at (x, z) facing d."""
    if d == 0:
        return x + u, z - v
    if d == 1:
        return x - v, z - u
    if d == 2:
        return x - u, z + v
    return x + v, z + u


def box_of(x, z, d, w, dp):
    """World footprint (x0, z0, x1, z1), inclusive, of a w x dp object anchored at (x, z) facing d."""
    if d == 0:
        return x, z + 1 - dp, x + w - 1, z
    if d == 1:
        return x + 1 - dp, z + 1 - w, x, z
    if d == 2:
        return x + 1 - w, z, x, z + dp - 1
    return x, z, x + dp - 1, z + w - 1


def part_size(var):
    """(item id, width, height, depth) of a placed-object variation."""
    info = px.map_part(var)
    if not info:
        return 0, 1, 1, 1
    return info[1], max(1, info[2]), max(1, info[3]), max(1, info[4])


class EditError(ValueError):
    pass


class PlacedObject:
    __slots__ = ('index', 'handle', 'link', 'var', 'flag12', 'x', 'y', 'z', 'dir', 'kind', 'flags', 'extra',
                 'chunk', 'item', 'w', 'h', 'dp', 'box')

    @property
    def name(self):
        return ps.item_name(self.item) if self.item else f'structure part {self.var}'

    def cells(self):
        """(wx, wy, wz, u, v, t) for every cell this object occupies."""
        for u in range(self.w):
            for v in range(self.dp):
                wx, wz = local_to_world(self.x, self.z, self.dir, u, v)
                for t in range(self.h):
                    yield wx, self.y + t, wz, u, v, t


class Habitat:
    __slots__ = ('uid', 'row', 'min', 'max', 'home', 'type', 'tail')

    @property
    def name(self):
        return ps.name_of(ps.HABITAT_NAMES, self.type, 'Habitat')


class Zone:
    """A connected group of chunks: the island itself, the Pokémon Center interior, a Dream Island, a small plot."""
    __slots__ = ('kind', 'title', 'note', 'chunks', 'box', 'objects')

    def __init__(self, kind, title, note, chunks, box, objects):
        self.kind, self.title, self.note, self.chunks, self.box, self.objects = kind, title, note, chunks, box, objects


BEACH = ('palm', 'seashore', 'seashell', 'sea glass', 'seaweed', 'yellow tall grass')
MOUNTAIN = ('red tall grass', 'pointy tree', 'mountain flowers', 'fern', 'cave mushroom')
SKY = ('skyland', 'iron pipe', 'pink tall grass', 'blue-green', 'robust flowers', 'fire hydrant')
PC_ITEMS = ('Pokémon Center counter', 'healing machine', 'Pokémon Center counter')


class Island:
    def __init__(self, path, area, progress=None):
        self.path, self.area = path, area
        self.name = ps.name_of(ps.AREA_NAMES, area, 'Area')
        with open(path, 'rb') as f:
            self.original = f.read()
        o = self.original
        if len(o) < HEADER:
            raise ps.FormatError('Island file too small')
        magic, ver = struct.unpack_from('<II', o, 0)
        if magic != ps.MAGIC:
            raise ps.FormatError(f'Bad magic {magic:#x}')
        if ver != VERSION:
            raise ps.FormatError(f'Unsupported island version {ver:#010x}')
        length = struct.unpack_from('<I', o, 0x10)[0]
        if not (HEADER < length <= len(o)):
            raise ps.FormatError('Compressed length field is invalid')
        try:
            raw = zlib.decompress(o[HEADER:length])
        except zlib.error as e:
            raise ps.FormatError(f'zlib error: {e}')
        if len(raw) != DATA_SIZE:
            raise ps.FormatError(f'Island size {len(raw)} != expected {DATA_SIZE}')
        self.d = bytearray(raw)
        del raw
        self._undo, self._redo, self._op = [], [], []
        self._dirty_cols, self._objs_dirty = set(), False
        self.cut = 127            # look-inside height: blocks and objects above it are ignored by the surface
        self._read_chunks()
        self._read_objects()
        self._learn_proxies()
        self._scan(progress)
        self._read_habitats()
        self._make_zones()

    # ------------------------------------------------------------------ structure
    def _read_chunks(self):
        self.cmap = list(struct.unpack_from('<4096H', self.d, CHUNK_MAP))
        alloc = [(i, s) for i, s in enumerate(self.cmap) if s != 0xFFFF]
        if not alloc:
            raise ps.FormatError('Island has no terrain')
        for _, s in alloc:
            if GRID + (s + 1) * CHUNK_BYTES > len(self.d):
                raise ps.FormatError('Island chunk table points outside the file')
        self.alloc = alloc
        self.slot_chunk = {s: i for i, s in alloc}
        cx0, cx1 = min(i & 63 for i, _ in alloc), max(i & 63 for i, _ in alloc)
        cz0, cz1 = min(i >> 6 for i, _ in alloc), max(i >> 6 for i, _ in alloc)
        self.x0, self.z0 = cx0 * 32, cz0 * 32
        self.width, self.height = (cx1 - cx0 + 1) * 32, (cz1 - cz0 + 1) * 32
        self.chunks = len(alloc)

    def has_chunk(self, wx, wz):
        return 0 <= wx < 2048 and 0 <= wz < 2048 and self.cmap[(wz >> 5) * 64 + (wx >> 5)] != 0xFFFF

    def cell_ofs(self, wx, y, wz):
        if not (0 <= wx < 2048 and 0 <= wz < 2048 and 0 <= y < 128):
            return None
        s = self.cmap[(wz >> 5) * 64 + (wx >> 5)]
        if s == 0xFFFF:
            return None
        return GRID + s * CHUNK_BYTES + (y * 1024 + (wz & 31) * 32 + (wx & 31)) * 3

    def get_cell(self, wx, y, wz):
        o = self.cell_ofs(wx, y, wz)
        if o is None:
            return None
        d = self.d
        return d[o] | d[o + 1] << 8 | d[o + 2] << 16

    def cls(self, bid):
        return self.cls_table[bid & ID_MASK]

    # ------------------------------------------------------------------ objects
    def count(self):
        return struct.unpack_from('<i', self.d, PART_COUNT)[0]

    def _read_objects(self):
        d = self.d
        n = self.count()
        if not 0 < n <= PART_CAP:
            n = 0
        objs = []
        unpack = struct.unpack_from
        for i in range(1, n):
            link, loc, st, ex = unpack('<IIII', d, PART_POOL + i * 16)
            h = (st >> 4) & 0xFFFFF
            if h >= n:
                continue        # the game skips these (holes, leftovers)
            pt = unpack('<I', d, POINTS + h * 4)[0]
            if pt >> 12 != i:
                continue
            var = loc & 0xFFF
            if not var:
                continue
            o = PlacedObject()
            ch = pt & 0xFFF
            o.index, o.handle, o.link, o.var, o.flag12 = i, h, link, var, (loc >> 12) & 1
            o.x = (ch & 63) * 32 + ((loc >> 13) & 31)
            o.y = (loc >> 18) & 127
            o.z = (ch >> 6) * 32 + ((loc >> 25) & 31)
            o.dir = loc >> 30
            o.kind, o.flags, o.extra, o.chunk = st & 15, st >> 24, ex, ch
            o.item, o.w, o.h, o.dp = part_size(var)
            o.box = box_of(o.x, o.z, o.dir, o.w, o.dp)
            objs.append(o)
        self.objects = objs
        self.by_handle = {o.handle: o for o in objs}
        self._buckets = None
        self._objs_dirty = False
        self.objects_version = getattr(self, 'objects_version', 0) + 1

    def buckets(self):
        """{(chunk x, chunk z) relative to the image: [object, ...]} for fast lookups by area."""
        if self._buckets is None:
            b = {}
            for o in self.objects:
                x0, z0, x1, z1 = o.box
                for bx in range((x0 - self.x0) >> 5, ((x1 - self.x0) >> 5) + 1):
                    for bz in range((z0 - self.z0) >> 5, ((z1 - self.z0) >> 5) + 1):
                        b.setdefault((bx, bz), []).append(o)
            self._buckets = b
        return self._buckets

    def objects_in(self, x0, z0, x1, z1):
        """Objects whose footprint overlaps the world rectangle (inclusive)."""
        b, seen = self.buckets(), set()
        for bx in range((int(x0) - self.x0) >> 5, ((int(x1) - self.x0) >> 5) + 1):
            for bz in range((int(z0) - self.z0) >> 5, ((int(z1) - self.z0) >> 5) + 1):
                for o in b.get((bx, bz), ()):
                    if o.handle not in seen:
                        bx0, bz0, bx1, bz1 = o.box
                        if bx0 <= x1 and bx1 >= x0 and bz0 <= z1 and bz1 >= z0:
                            seen.add(o.handle)
                            yield o

    def glowing_blocks(self):
        """Saved, uncleared treasure coordinates for the supported island format."""
        positions = []
        for index in range(GLOWING_SLOTS):
            x, y, z, flags = struct.unpack_from('<HHHH', self.d, GLOWING_POSITIONS + index * 8)
            if (x or y or z) and 0 <= y < 128 and self.has_chunk(x, z):
                positions.append((index, x, y, z, flags))
        return positions

    def set_cut(self, y):
        """Look inside: ignore everything above height y (127 = see everything). Rescans the surface."""
        y = max(1, min(127, int(y)))
        if y != self.cut:
            self.cut = y
            self._scan()

    def visible(self, o):
        return o.y <= self.cut

    def crosses_cut(self, o):
        """True for objects cut through by look-inside (a building whose roof is above the cut)."""
        return self.cut < 127 and o.y <= self.cut < o.y + o.h - 1

    def object_at(self, wx, wz):
        hits = [o for o in self.objects_in(wx, wz, wx, wz) if o.y <= self.cut]
        return max(hits, key=lambda o: (not self.crosses_cut(o), o.y + o.h, -o.w * o.dp)) if hits else None

    def top_at(self, wx, wz):
        """Height of the highest block or object in a column, ignoring look-inside."""
        top = None
        for y in range(127, -1, -1):
            c = self.get_cell(wx, y, wz)
            if c is None:
                break
            if c & ID_MASK:
                top = y
                break
        for o in self.objects_in(wx, wz, wx, wz):
            t = o.y + o.h - 1
            top = t if top is None else max(top, t)
        return top

    def habitat_recipes(self):
        """What each habitat on this island is made of, to rebuild it elsewhere: dicts with type, name, island,
        size and parts [(variation, dx, height above ground, dz, direction, item)]."""
        out = []
        for h in self.habitats:
            x0, y0, z0 = h.min
            x1, y1, z1 = h.max
            parts = []
            for o in self.objects_in(x0, z0, x1, z1):
                if not (x0 <= o.x <= x1 and z0 <= o.z <= z1 and y0 - 1 <= o.y <= y1 + 1):
                    continue
                col = self.column(o.x, o.z)
                g = col[2] + 1 if col else o.y
                parts.append((o.var, o.x - x0, max(0, o.y - g), o.z - z0, o.dir, o.item))
            if not parts:
                continue
            water = any((c := self.column(x, z)) and c[0] != c[2]
                        for x in range(x0 - 1, x1 + 2) for z in range(z0 - 1, z1 + 2))
            heights = {c[2] for x in range(x0, x1 + 1) for z in range(z0, z1 + 1) if (c := self.column(x, z))}
            out.append(dict(type=h.type, name=h.name, island=self.name, w=x1 - x0 + 1, d=z1 - z0 + 1,
                            parts=parts, water=water, uneven=len(heights) > 1))
        return out

    def _learn_proxies(self):
        """Block ids that objects use as collision cells (not terrain), plus a cell template per variation."""
        tab = _blocks()
        cnt = Counter()
        self.templates = {}
        for o in self.objects:
            tpl = {}
            for wx, wy, wz, u, v, t in o.cells():
                c = self.get_cell(wx, wy, wz)
                if c is None:
                    continue
                bid = c & ID_MASK
                if bid == OBJECT or (bid > BEDROCK and not tab[bid][1]):
                    tpl[(u, v, t)] = c
                    if bid != OBJECT:
                        cnt[bid] += 1
            if o.var not in self.templates or len(tpl) > len(self.templates[o.var]):
                self.templates[o.var] = tpl
        self.proxies = set(cnt)
        ct = bytearray(2048)
        for bid, (it, k) in enumerate(tab):
            if k == K_LIQUID:
                ct[bid] = C_LIQUID
            elif bid:
                ct[bid] = C_SOLID
        for bid in self.proxies:
            if not tab[bid][1]:
                ct[bid] = C_OBJECT
        ct[AIR], ct[BEDROCK], ct[OBJECT] = C_AIR, C_SOLID, C_OBJECT
        self.cls_table = bytes(ct)

    # ------------------------------------------------------------------ surface
    def _scan(self, progress=None):
        W, H = self.width, self.height
        self.top_h = bytearray(b'\xff') * (W * H)       # height of the top block (liquid surface or ground)
        self.top_id = array.array('H', bytes(2 * W * H))
        self.floor_h = bytearray(b'\xff') * (W * H)     # height of the ground under any liquid
        self.floor_id = array.array('H', bytes(2 * W * H))
        for n, (ci, s) in enumerate(self.alloc):
            self._scan_chunk(ci, s)
            if progress:
                progress((n + 1) / len(self.alloc))

    def _scan_chunk(self, ci, slot):
        d, CLS, W = self.d, self.cls_table, self.width
        top_h, top_id, floor_h, floor_id = self.top_h, self.top_id, self.floor_h, self.floor_id
        base = GRID + slot * CHUNK_BYTES
        ox, oz = (ci & 63) * 32 - self.x0, (ci >> 6) * 32 - self.z0
        rem = list(range(1024))
        liq = {}
        for y in range(self.cut, -1, -1):
            o = base + y * PLANE
            pl = d[o:o + PLANE]
            if pl == ZERO_PLANE:
                continue
            nxt = []
            for k in rem:
                j = k * 3
                bid = (pl[j] | pl[j + 1] << 8) & ID_MASK
                c = CLS[bid]
                if c == C_SOLID:
                    p = (oz + (k >> 5)) * W + ox + (k & 31)
                    L = liq.get(k)
                    if L:
                        top_h[p], top_id[p] = L
                    else:
                        top_h[p], top_id[p] = y, bid
                    floor_h[p], floor_id[p] = y, bid
                else:
                    if c == C_LIQUID and k not in liq:
                        liq[k] = (y, bid)
                    nxt.append(k)
            rem = nxt
            if not rem:
                break
        for k in rem:
            L = liq.get(k)
            if L:
                p = (oz + (k >> 5)) * W + ox + (k & 31)
                top_h[p], top_id[p] = L
                floor_h[p], floor_id[p] = 0, L[1]

    def _scan_column(self, wx, wz):
        px_, pz = wx - self.x0, wz - self.z0
        if not (0 <= px_ < self.width and 0 <= pz < self.height):
            return
        p = pz * self.width + px_
        self.top_h[p] = self.floor_h[p] = NO_DATA
        self.top_id[p] = self.floor_id[p] = 0
        if not self.has_chunk(wx, wz):
            return
        CLS, liq = self.cls_table, None
        for y in range(self.cut, -1, -1):
            bid = self.get_cell(wx, y, wz) & ID_MASK
            c = CLS[bid]
            if c == C_SOLID:
                if liq:
                    self.top_h[p], self.top_id[p] = liq
                else:
                    self.top_h[p], self.top_id[p] = y, bid
                self.floor_h[p], self.floor_id[p] = y, bid
                return
            if c == C_LIQUID and liq is None:
                liq = (y, bid)
        if liq:
            self.top_h[p], self.top_id[p] = liq
            self.floor_h[p], self.floor_id[p] = 0, liq[1]

    def column(self, wx, wz):
        """(top height, top block, ground height, ground block) or None outside the island."""
        px_, pz = wx - self.x0, wz - self.z0
        if not (0 <= px_ < self.width and 0 <= pz < self.height):
            return None
        p = pz * self.width + px_
        if self.top_h[p] == NO_DATA:
            return None
        return self.top_h[p], self.top_id[p], self.floor_h[p], self.floor_id[p]

    # ------------------------------------------------------------------ habitats & zones
    def _read_habitats(self):
        d, out = self.d, []
        for row in range(HABITAT_CAP):
            o = HABITATS + row * HABITAT_SIZE
            v = struct.unpack_from('<9h', d, o)
            t = struct.unpack_from('<I', d, o + 18)[0]
            if not t:
                continue
            if not (0 <= v[0] <= v[3] < 2048 and 0 <= v[1] <= v[4] < 128 and 0 <= v[2] <= v[5] < 2048 and t < 4096):
                break
            h = Habitat()
            h.uid, h.row, h.min, h.max, h.home, h.type = 101 + row, row, v[0:3], v[3:6], v[6:9], t
            h.tail = bytes(d[o + 22:o + 26])
            out.append(h)
        self.habitats = out

    def _make_zones(self):
        todo, groups = {(i & 63, i >> 6) for i, _ in self.alloc}, []
        while todo:
            stack, g = [todo.pop()], []
            while stack:
                c = stack.pop()
                g.append(c)
                for nb in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                    if nb in todo:
                        todo.remove(nb)
                        stack.append(nb)
            groups.append(g)
        groups.sort(key=len, reverse=True)
        names = {}
        for o in self.objects:
            names.setdefault((o.x >> 5, o.z >> 5), Counter())[o.name] += 1
        zones = []
        for n, g in enumerate(groups):
            gs = set(g)
            cnt = Counter()
            for c in g:
                cnt.update(names.get(c, {}))
            xs, zs = [c[0] for c in g], [c[1] for c in g]
            box = (min(xs) * 32, min(zs) * 32, (max(xs) + 1) * 32 - 1, (max(zs) + 1) * 32 - 1)
            objs = sum(cnt.values())
            text = ' '.join(cnt).lower()
            if n == 0:
                z = Zone('island', self.name, 'The island you explore and build on.', gs, box, objs)
            elif any(k in cnt for k in PC_ITEMS) or 'counter' in cnt or (min(xs) >= 56 and min(zs) >= 60):
                z = Zone('center', 'Pokémon Center interior',
                         'Inside the Pokémon Center: the ground floor with the counter and healing machine, '
                         'the bedroom upstairs, and the building\'s other stages stacked underneath. '
                         'It sits far from the island because buildings in this game are entered like separate rooms.',
                         gs, box, objs)
            elif len(g) >= 16:
                z = Zone('dream', 'Dream Island',
                         'A second island stored in this file, far from the first. Its shape and contents match the '
                         'Dream Islands Drifloon takes you to; the game replaces it when you visit a new one.',
                         gs, box, objs)
            else:
                biome = max((sum(k in text for k in BEACH), 'Beach'), (sum(k in text for k in MOUNTAIN), 'Mountain'),
                            (sum(k in text for k in SKY), 'Skyland'))
                title = f'{biome[1]} plot' if biome[0] else 'Small plot'
                z = Zone('plot', title,
                         'A small scenery plot that was part of this island from the start. Nothing connects it to the '
                         'island, so it cannot be reached on foot.', gs, box, objs)
            zones.append(z)
        self.zones = zones

    def zone_at(self, wx, wz):
        c = (wx >> 5, wz >> 5)
        return next((z for z in self.zones if c in z.chunks), None)

    def main_box(self):
        return self.zones[0].box

    # ------------------------------------------------------------------ journal
    def _put(self, ofs, data):
        old = bytes(self.d[ofs:ofs + len(data)])
        if old == data:
            return
        self._op.append((ofs, old, bytes(data)))
        self.d[ofs:ofs + len(data)] = data
        if ofs >= GRID:
            self._mark_cell_ofs(ofs)
        elif PART_COUNT <= ofs < POINTS + PART_CAP * 4:
            self._objs_dirty = True

    def _mark_cell_ofs(self, ofs):
        rel = ofs - GRID
        s, r = divmod(rel, CHUNK_BYTES)
        ci = self.slot_chunk.get(s)
        if ci is None:
            return
        k = (r // 3) % 1024
        self._dirty_cols.add(((ci & 63) * 32 + (k & 31), (ci >> 6) * 32 + (k >> 5)))

    def set_cell(self, wx, y, wz, value):
        o = self.cell_ofs(wx, y, wz)
        if o is None:
            raise EditError('That spot is outside the island.')
        self._put(o, bytes((value & 255, value >> 8 & 255, value >> 16 & 255)))

    @property
    def edited(self):
        return bool(self._undo)

    @property
    def history(self):
        return [lab for lab, _ in self._undo]

    @property
    def can_redo(self):
        return bool(self._redo)

    def commit(self, label):
        if not self._op:
            return False
        self._undo.append((label, self._op))
        self._op = []
        self._redo.clear()
        self.refresh()
        return True

    def rollback(self):
        for ofs, old, _ in reversed(self._op):
            self.d[ofs:ofs + len(old)] = old
            if ofs >= GRID:
                self._mark_cell_ofs(ofs)
            else:
                self._objs_dirty = True
        self._op = []
        self.refresh()

    def undo(self):
        if not self._undo:
            return None
        label, op = self._undo.pop()
        for ofs, old, _ in reversed(op):
            self.d[ofs:ofs + len(old)] = old
            self._mark_any(ofs)
        self._redo.append((label, op))
        self.refresh()
        return label

    def redo(self):
        if not self._redo:
            return None
        label, op = self._redo.pop()
        for ofs, _, new in op:
            self.d[ofs:ofs + len(new)] = new
            self._mark_any(ofs)
        self._undo.append((label, op))
        self.refresh()
        return label

    def _mark_any(self, ofs):
        if ofs >= GRID:
            self._mark_cell_ofs(ofs)
        elif PART_COUNT <= ofs < POINTS + PART_CAP * 4:
            self._objs_dirty = True

    def refresh(self):
        """Bring the object list and surface back in step with the raw data. Returns the columns that changed."""
        if self._objs_dirty:
            self._read_objects()
        cols, self._dirty_cols = self._dirty_cols, set()
        for wx, wz in cols:
            self._scan_column(wx, wz)
        self.last_dirty = cols
        return cols

    def summary(self):
        """Readable lines describing the edits made so far."""
        return [f'{self.name}: {lab}' for lab, _ in self._undo]

    # ------------------------------------------------------------------ writing
    def to_bytes(self):
        if not self.edited:
            return self.original
        comp = zlib.compress(bytes(self.d), COMPRESS_LEVEL)
        length = HEADER + len(comp)
        out = bytearray(max(length, len(self.original)))
        out[:HEADER] = self.original[:HEADER]
        out[HEADER:length] = comp
        struct.pack_into('<I', out, 0x10, length)
        return bytes(out)

    def validate(self, blob):
        length = struct.unpack_from('<I', blob, 0x10)[0]
        if struct.unpack_from('<II', blob, 0) != (ps.MAGIC, VERSION) or zlib.decompress(blob[HEADER:length]) != self.d:
            raise ps.FormatError(f'Re-encoded {self.name} failed validation, nothing written')

    def changed_on_disk(self):
        try:
            with open(self.path, 'rb') as f:
                return f.read() != self.original
        except OSError:
            return True

    # ------------------------------------------------------------------ terrain edits
    def _top_solid(self, wx, wz):
        """(y, cell) of the ground block of a column, or None."""
        col = self.column(wx, wz)
        if not col:
            return None
        y = col[2]
        c = self.get_cell(wx, y, wz)
        return (y, c) if c is not None else None

    def paint(self, cols, bid, all_layers=False):
        """Replace the ground block of each column. Columns under water keep their water. Returns the count."""
        if self.cls(bid) != C_SOLID or bid in (AIR, BEDROCK, OBJECT):
            raise EditError('Pick a terrain or building block to paint with.')
        n = 0
        for wx, wz in cols:
            t = self._top_solid(wx, wz)
            if not t or t[0] == 0:
                continue
            top = t[0]
            for y in (range(1, top + 1) if all_layers else (top,)):
                c = self.get_cell(wx, y, wz)
                if c is None:
                    continue
                old = c & ID_MASK
                if old in (AIR, BEDROCK, OBJECT, bid) or self.cls(old) != C_SOLID:
                    continue
                if all_layers and y != top and block_kind(old) != K_TERRAIN:
                    continue
                self.set_cell(wx, y, wz, bid | PLAYER)
                n += 1
        return n

    def set_liquid(self, cols, bid):
        """Turn the ground block of each column into a full liquid block (a one-deep pool). Returns the count."""
        if self.cls(bid) != C_LIQUID:
            raise EditError('That is not a liquid.')
        n = 0
        for wx, wz in cols:
            t = self._top_solid(wx, wz)
            if not t or t[0] <= 1:
                continue
            y, c = t
            above = self.get_cell(wx, y + 1, wz)
            if above is not None and self.cls_table[above & ID_MASK] == C_OBJECT:
                continue
            self.set_cell(wx, y, wz, bid | (0x21F << 11))
            n += 1
        return n

    def _fill_for(self, wx, y, wz):
        """What an emptied cell becomes: the neighbouring liquid if it touches one, else air."""
        for nx, ny, nz in ((wx, y + 1, wz), (wx + 1, y, wz), (wx - 1, y, wz), (wx, y, wz + 1), (wx, y, wz - 1)):
            c = self.get_cell(nx, ny, nz)
            if c is not None and self.cls_table[c & ID_MASK] == C_LIQUID:
                return c
        return AIR

    def _lift_surface_objects(self, wx, wz, ground_y):
        """Lift obstructing placed items and their stacks, preserving their layout."""
        moving = {o.handle: o for o in self.objects_in(wx, wz, wx, wz)
                  if o.y <= ground_y + 1 < o.y + o.h}
        pending = list(moving.values())
        while pending:
            base = pending.pop()
            for other in self.objects_in(*base.box):
                if other.handle not in moving and other.y >= base.y + base.h:
                    moving[other.handle] = other
                    pending.append(other)
        if moving:
            self.move_objects([(o.handle, o.x, o.y + 1, o.z, o.dir)
                               for o in moving.values()])

    def raise_ground(self, cols, bid=None, lift_objects=False):
        n = 0
        for wx, wz in cols:
            t = self._top_solid(wx, wz)
            if not t or t[0] >= 126:
                continue
            y, c = t
            above = self.get_cell(wx, y + 1, wz)
            if lift_objects:
                self._lift_surface_objects(wx, wz, y)
                above = self.get_cell(wx, y + 1, wz)
            if above is None or self.cls_table[above & ID_MASK] in (C_SOLID, C_OBJECT):
                continue
            self.set_cell(wx, y + 1, wz, (bid if bid else c & ID_MASK) | PLAYER)
            n += 1
        return n

    def lower_ground(self, cols):
        n = 0
        for wx, wz in cols:
            t = self._top_solid(wx, wz)
            if not t or t[0] <= 1:
                continue
            y, c = t
            above = self.get_cell(wx, y + 1, wz)
            if above is not None and self.cls_table[above & ID_MASK] == C_OBJECT:
                continue          # something stands on it
            self.set_cell(wx, y, wz, self._fill_for(wx, y, wz))
            n += 1
        return n

    def level_ground(self, cols, target, bid=None, lift_objects=False):
        """Raise or lower each column until its ground is at `target`."""
        n = 0
        for wx, wz in cols:
            for _ in range(64):
                self.refresh()
                t = self._top_solid(wx, wz)
                if not t or t[0] == target:
                    break
                k = self.raise_ground([(wx, wz)], bid, lift_objects=lift_objects) if t[0] < target else self.lower_ground([(wx, wz)])
                if not k:
                    break
                n += k
        return n

    # ------------------------------------------------------------------ object edits
    def _rec(self, i):
        return struct.unpack_from('<IIII', self.d, PART_POOL + i * 16)

    def _set_rec(self, i, rec):
        self._put(PART_POOL + i * 16, struct.pack('<IIII', *rec))

    def _point(self, h):
        return struct.unpack_from('<I', self.d, POINTS + h * 4)[0]

    def _set_point(self, h, v):
        self._put(POINTS + h * 4, struct.pack('<I', v))

    def _relink(self, chunks):
        """Rewrite the per-chunk links (previous record in the same chunk) for the given chunks."""
        chunks = set(chunks)
        if not chunks:
            return
        n, last = self.count(), {}
        for i in range(1, n):
            link, loc, st, ex = self._rec(i)
            h = (st >> 4) & 0xFFFFF
            if not loc & 0xFFF or h >= n or self._point(h) >> 12 != i:
                continue
            ch = self._point(h) & 0xFFF
            if ch in chunks:
                want = last.get(ch, FREE_LINK)
                if link != want:
                    self._set_rec(i, (want, loc, st, ex))
                last[ch] = i

    def template_for(self, var):
        return self.templates.get(var)

    def _cells_of(self, var, x, y, z, d):
        _, w, h, dp = part_size(var)
        for u in range(w):
            for v in range(dp):
                wx, wz = local_to_world(x, z, d, u, v)
                for t in range(h):
                    yield wx, y + t, wz, u, v, t

    def blocked(self, var, x, y, z, d, ignore=()):
        """None if the object fits there, else a reason. Cells of objects in `ignore` (handles) count as free."""
        if not (0 <= y and y + part_size(var)[2] <= 128):
            return 'Too high or too low.'
        mine = set()
        for hnd in ignore:
            o = self.by_handle.get(hnd)
            if o:
                mine.update((wx, wy, wz) for wx, wy, wz, *_ in o.cells())
        cells = [(wx, wy, wz) for wx, wy, wz, *_ in self._cells_of(var, x, y, z, d)]
        _, w, h, dp = part_size(var)
        bx0, bz0, bx1, bz1 = box_of(x, z, d, w, dp)
        want = set(cells)
        for o in self.objects_in(bx0, bz0, bx1, bz1):
            if o.handle in ignore or o.y > y + h - 1 or o.y + o.h - 1 < y:
                continue
            if any((wx, wy, wz) in want for wx, wy, wz, *_ in o.cells()):
                return f'It would overlap the {o.name}.'
        for wx, wy, wz in cells:
            c = self.get_cell(wx, wy, wz)
            if c is None:
                return 'Part of it would be outside the island.'
            k = self.cls_table[c & ID_MASK]
            if k == C_SOLID:
                return 'Something solid is in the way.'
            if k == C_OBJECT and (wx, wy, wz) not in mine:
                return 'Another object is in the way.'
        return None

    def ground_y(self, var, x, z, d):
        """Height an object would stand at: one above the highest ground under its footprint."""
        _, w, h, dp = part_size(var)
        best = None
        for u in range(w):
            for v in range(dp):
                wx, wz = local_to_world(x, z, d, u, v)
                col = self.column(wx, wz)
                if col:
                    best = col[2] + 1 if best is None else max(best, col[2] + 1)
        return best

    def _write_cells(self, var, x, y, z, d, tpl):
        default = OBJECT | PLAYER
        for wx, wy, wz, u, v, t in self._cells_of(var, x, y, z, d):
            val = tpl.get((u, v, t)) if tpl is not None else default
            if val is None:
                continue
            self.set_cell(wx, wy, wz, (val & ~PLAYER & 0xFFFFFF) | PLAYER)

    def _clear_cells(self, o):
        """Empty the cells an object takes. Returns its template (u, v, t) -> cell."""
        tpl, cells = {}, []
        shared = set()
        for other in self.objects_in(*o.box):
            if other.handle != o.handle and not (other.y > o.y + o.h - 1 or other.y + other.h - 1 < o.y):
                shared.update((wx, wy, wz) for wx, wy, wz, *_ in other.cells())
        for wx, wy, wz, u, v, t in o.cells():
            c = self.get_cell(wx, wy, wz)
            if c is not None and self.cls_table[c & ID_MASK] == C_OBJECT and (wx, wy, wz) not in shared:
                tpl[(u, v, t)] = c
                cells.append((wx, wy, wz))
        for wx, wy, wz in cells:
            self.set_cell(wx, wy, wz, AIR)
        for wx, wy, wz in cells:
            self.set_cell(wx, wy, wz, self._fill_for(wx, wy, wz))
        return tpl

    def _parked(self, j):
        """Handle parked in free record j (index at or past the count), initialising never-used records."""
        link, loc, st, ex = self._rec(j)
        h = (st >> 4) & 0xFFFFF
        if h and self._point(h) >> 12 == j:
            return h
        if not st and not loc and j and self._point(j) in (0, j << 12) and j not in self.by_handle:
            # the game never initialised this record: its handle is its index
            self._set_rec(j, (FREE_LINK, 0, j << 4, 0))
            self._set_point(j, j << 12)
            return j
        return None

    def _swap_handles(self, i, j):
        """Exchange the handles of records i and j (keeping each handle's chunk bits)."""
        ri, rj = self._rec(i), self._rec(j)
        hi, hj = (ri[2] >> 4) & 0xFFFFF, (rj[2] >> 4) & 0xFFFFF
        ci, cj = self._point(hi) & 0xFFF, self._point(hj) & 0xFFF
        self._set_rec(i, (ri[0], ri[1], (ri[2] & ~0xFFFFF0) | hj << 4, ri[3]))
        self._set_rec(j, (rj[0], rj[1], (rj[2] & ~0xFFFFF0) | hi << 4, rj[3]))
        self._set_point(hj, (i << 12) | cj)
        self._set_point(hi, (j << 12) | ci)

    def _find_parked(self, n, want_low, start=None):
        """Index of a free record (at or past the count n) whose handle is below n (want_low) or not."""
        for j in range(start if start is not None else n, min(PART_CAP, n + 200000)):
            h = self._parked(j)
            if h is not None and (h < n) == want_low:
                return j
        return None

    def _normalize(self):
        """Holes below the count must hold handles at or above it, live records handles below it."""
        n = self.count()
        for i in range(1, n):
            link, loc, st, ex = self._rec(i)
            h = (st >> 4) & 0xFFFFF
            if self._point(h) >> 12 != i:
                continue
            hole = not loc & 0xFFF
            if hole and h < n:
                j = self._find_parked(n, want_low=False)
                if j is None:
                    raise EditError('No spare object handles left on this island.')
                self._swap_handles(i, j)

    def add_object(self, var, x, y, z, d, like=None, exact=False):
        """Place a new object at the end of the pool. Kind and extra state come from `like` (an existing object of
        the same kind, found automatically if not given); its flags too when `exact` (duplicates). Returns the handle."""
        if var <= 0 or var >= 4096:
            raise EditError('Unknown object.')
        why = self.blocked(var, x, y, z, d)
        if why:
            raise EditError(why)
        n = self.count()
        if n + 1 >= PART_CAP:
            raise EditError('This island has no room for more objects.')
        if like is None:
            like = next((o for o in self.objects if o.var == var), None)
        kind, flags, extra = (like.kind, like.flags if exact else like.flags & 0x0F, like.extra) if like else (4, 0, 0)
        # the new record sits at index n and needs a handle the game will load: at most n (count becomes n + 1)
        h = self._parked(n)
        if h is None or h > n:
            j = self._find_parked(n + 1, want_low=True, start=n + 1)
            if j is not None and self._parked(j) <= n:
                if h is None:
                    raise EditError('The object list of this island is not in a shape the editor understands.')
                self._swap_handles(n, j)
            else:
                # handle n may sit on a hole; take it from there
                k = next((i for i in range(1, n) if (self._rec(i)[2] >> 4) & 0xFFFFF == n
                          and not self._rec(i)[1] & 0xFFF), None)
                if k is None or h is None:
                    raise EditError('No free object handle on this island.')
                self._swap_handles(n, k)
            h = (self._rec(n)[2] >> 4) & 0xFFFFF
        ch = (z >> 5) * 64 + (x >> 5)
        loc = var | (x & 31) << 13 | y << 18 | (z & 31) << 25 | (d & 3) << 30
        self._set_rec(n, (FREE_LINK, loc, kind | h << 4 | flags << 24, extra))
        self._set_point(h, (n << 12) | ch)
        self._put(PART_COUNT, struct.pack('<i', n + 1))
        self._normalize()
        self._write_cells(var, x, y, z, d, self.templates.get(var))
        self._relink([ch])
        self._read_objects()
        return h

    def remove_object(self, handle):
        """Remove an object the way the game does: its record becomes a hole in place, nothing else moves."""
        o = self.by_handle.get(handle)
        if not o:
            raise EditError('That object is already gone.')
        self._clear_cells(o)
        n = self.count()
        i = o.index
        if i == n - 1:
            # the last record: just shrink the count; the record keeps the freed handle past the end
            self._set_rec(i, (FREE_LINK, 0, handle << 4, 0))
            self._set_point(handle, (i << 12) | o.chunk)
            self._put(PART_COUNT, struct.pack('<i', n - 1))
            self._normalize()
        else:
            j = self._find_parked(n, want_low=False)
            if j is None:
                raise EditError('No spare object handles left on this island.')
            self._set_rec(i, (FREE_LINK, 0, handle << 4, 0))
            self._swap_handles(i, j)          # the hole gets the spare handle, record j keeps the freed one
            hs = (self._rec(i)[2] >> 4) & 0xFFFFF
            self._set_point(hs, (i << 12) | o.chunk)
            self._set_rec(j, (FREE_LINK, 0, handle << 4, 0))
            self._set_point(handle, (j << 12) | o.chunk)
        self._relink([o.chunk])
        self._read_objects()

    def move_objects(self, moves):
        """moves: [(handle, x, y, z, dir)]. All or nothing."""
        objs = []
        for hnd, x, y, z, d in moves:
            o = self.by_handle.get(hnd)
            if not o:
                raise EditError('An object in the selection is gone.')
            objs.append((o, x, y, z, d & 3))
        mine = [o.handle for o, *_ in objs]
        # check the new spots against everything except the moving objects themselves
        for o, x, y, z, d in objs:
            why = self.blocked(o.var, x, y, z, d, ignore=mine)
            if why:
                raise EditError(why)
        # the moved objects may not overlap each other's new spots
        taken = set()
        for (o, x, y, z, d) in objs:
            for wx, wy, wz, *_ in self._cells_of(o.var, x, y, z, d):
                if (wx, wy, wz) in taken:
                    raise EditError('Two moved objects would overlap.')
                taken.add((wx, wy, wz))
        tpls = [self._clear_cells(o) for o, *_ in objs]
        chunks = set()
        for (o, x, y, z, d), tpl in zip(objs, tpls):
            link, loc, st, ex = self._rec(o.index)
            ch = (z >> 5) * 64 + (x >> 5)
            loc = (loc & 0x1FFF) | (x & 31) << 13 | y << 18 | (z & 31) << 25 | d << 30
            self._set_rec(o.index, (link, loc, st, ex))
            self._set_point(o.handle, (o.index << 12) | ch)
            chunks.update((o.chunk, ch))
            self._write_cells(o.var, x, y, z, d, tpl)
        self._relink(chunks)
        self._read_objects()

    def duplicate_objects(self, handles, dx, dz):
        """Copy objects, shifted by (dx, dz). Returns the new handles."""
        src = [self.by_handle[h] for h in handles if h in self.by_handle]
        out = []
        for o in sorted(src, key=lambda o: o.y):
            tpl_keep = self.templates.get(o.var)
            own = {}
            for wx, wy, wz, u, v, t in o.cells():
                c = self.get_cell(wx, wy, wz)
                if c is not None and self.cls_table[c & ID_MASK] == C_OBJECT:
                    own[(u, v, t)] = c
            self.templates[o.var] = own
            try:
                out.append(self.add_object(o.var, o.x + dx, o.y, o.z + dz, o.dir, like=o, exact=True))
            finally:
                if tpl_keep is not None:
                    self.templates[o.var] = tpl_keep
        return out


def load(path, area, progress=None):
    return Island(path, area, progress)
