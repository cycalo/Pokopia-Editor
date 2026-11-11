"""Read-only extras for the Pokopia save editor: island maps, photos, backups, icons, emulator check.

Nothing in this module ever writes to a save file. STGDAT (island) and SCSHDAT (photo)
files are only decoded for viewing/exporting.

The photo layout, and the meaning of
block id 349 (sea water), are own findings from a real save.
"""
import array, datetime, glob, io, os, shutil, struct, subprocess, sys, zlib
import pokopia_save as ps

try:
    from PIL import Image
except ImportError:  # the editor still works without Pillow, just without maps/photos/icons
    Image = None

HERE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))  # bundle dir in the exe
DATA = os.path.join(HERE, 'data')


# ---------------------------------------------------------------- island maps
class StageMap:
    """Top-down view of one island (G00/STGDAT##.BIN)."""
    VERSION = 0x0300018B
    HEADER = 0x124
    DATA_SIZE = 0x83FFDB8
    CHUNK_MAP = 0x58571B      # 64 x 64 u16, 0xFFFF = not allocated
    PART_COUNT = 0x58771F
    PART_POOL = 0x587723      # 16-byte placed-object records
    PART_CAPACITY = 0xC8000
    POINTS = 0x1207723        # u32 per handle: (part index << 12) | chunk
    GRID = 0x23FFEDC
    CHUNK_CELLS = 0x20000     # 32 x 32 columns x 128 high, 3 bytes per cell
    ID_MASK = 0x7FF
    OBJECT = 0x7FF            # cell occupied by a placed object
    WATER = 349
    SEA_LEVEL = 31
    NO_DATA = 255

    def __init__(self, path, area, progress=None):
        self.path, self.area = path, area
        self.name = ps.name_of(ps.AREA_NAMES, area, 'Area')
        with open(path, 'rb') as f:
            o = f.read()
        if len(o) < self.HEADER:
            raise ps.FormatError('Island file too small')
        magic, ver = struct.unpack_from('<II', o, 0)
        if magic != ps.MAGIC:
            raise ps.FormatError(f'Bad magic {magic:#x}')
        if ver != self.VERSION:
            raise ps.FormatError(f'Unsupported island version {ver:#010x}')
        length = struct.unpack_from('<I', o, 0x10)[0]
        if not (self.HEADER < length <= len(o)):
            raise ps.FormatError('Compressed length field is invalid')
        try:
            d = zlib.decompress(o[self.HEADER:length])
        except zlib.error as e:
            raise ps.FormatError(f'zlib error: {e}')
        del o
        if len(d) != self.DATA_SIZE:
            raise ps.FormatError(f'Island size {len(d)} != expected {self.DATA_SIZE}')
        self.parts = struct.unpack_from('<i', d, self.PART_COUNT)[0]
        self._scan(d, progress)
        self.placed = self._read_parts(d)

    def _read_parts(self, d):
        """Placed objects: [(variation, item_id, min_x, min_z, max_x, max_z, y, height, direction)] in world
        block coordinates. Read only."""
        n = self.parts
        if not 0 < n <= self.PART_CAPACITY:
            return []
        out = []
        pool, points = self.PART_POOL, self.POINTS
        for i in range(n):
            loc, state = struct.unpack_from('<II', d, pool + i * 16 + 4)
            h = (state >> 4) & 0xFFFFF
            if h >= self.PART_CAPACITY:
                continue
            pt = struct.unpack_from('<I', d, points + h * 4)[0]
            if pt >> 12 != i:
                continue
            ch = pt & 0xFFF
            var = loc & 0xFFF
            if not var:
                continue
            x = (ch & 63) * 32 + ((loc >> 13) & 31)
            y = (loc >> 18) & 127
            z = (ch >> 6) * 32 + ((loc >> 25) & 31)
            dr = loc >> 30
            info = map_part(var)
            item, w, hh, dp = (info[1], info[2], info[3], info[4]) if info else (0, 1, 1, 1)
            w, hh, dp = max(1, w), max(1, hh), max(1, dp)
            if dr == 0:
                box = (x, z + 1 - dp, x + w - 1, z)
            elif dr == 1:
                box = (x + 1 - dp, z + 1 - w, x, z)
            elif dr == 2:
                box = (x + 1 - w, z, x, z + dp - 1)
            else:
                box = (x, z, x + dp - 1, z + w - 1)
            out.append((var, item) + box + (y, hh, dr))
        return out

    def parts_at(self, wx, wz):
        """Placed objects whose footprint covers world column (wx, wz), topmost first."""
        hits = [p for p in self.placed if p[2] <= wx <= p[4] and p[3] <= wz <= p[5]]
        return sorted(hits, key=lambda p: -(p[6] + p[7]))

    def _scan(self, d, progress):
        cmap = struct.unpack_from('<4096H', d, self.CHUNK_MAP)
        alloc = [(i, s) for i, s in enumerate(cmap) if s != 0xFFFF]
        if not alloc:
            raise ps.FormatError('Island has no terrain')
        plane = 32 * 32 * 3
        for _, s in alloc:
            if self.GRID + (s + 1) * self.CHUNK_CELLS * 3 > len(d):
                raise ps.FormatError('Island chunk table points outside the file')
        cx0, cx1 = min(i & 63 for i, _ in alloc), max(i & 63 for i, _ in alloc)
        cz0, cz1 = min(i >> 6 for i, _ in alloc), max(i >> 6 for i, _ in alloc)
        self.x0, self.z0 = cx0 * 32, cz0 * 32
        W = self.width = (cx1 - cx0 + 1) * 32
        H = self.height = (cz1 - cz0 + 1) * 32
        self.chunks = len(alloc)
        self._cells = {((i & 63) - cx0, (i >> 6) - cz0) for i, _ in alloc}
        hts = self.heights = bytearray(b'\xff') * (W * H)
        ids = self.ids = array.array('H', bytes(2 * W * H))
        depth = self.depth = bytearray(W * H)
        objs = self.objects = bytearray(W * H)
        zero = bytes(plane)
        ID_MASK, OBJECT, WATER = self.ID_MASK, self.OBJECT, self.WATER
        for n, (ci, s) in enumerate(alloc):
            base = self.GRID + s * self.CHUNK_CELLS * 3
            ox, oz = ((ci & 63) - cx0) * 32, ((ci >> 6) - cz0) * 32
            rem = list(range(1024))
            wtop = [-1] * 1024
            for y in range(127, -1, -1):
                pl = d[base + y * plane:base + (y + 1) * plane]
                if pl == zero:
                    continue
                nxt = []
                for k in rem:
                    j = k * 3
                    bid = (pl[j] | pl[j + 1] << 8) & ID_MASK
                    if bid == 0:
                        nxt.append(k)
                        continue
                    p = (oz + (k >> 5)) * W + ox + (k & 31)
                    if bid == OBJECT:
                        objs[p] = 1
                        nxt.append(k)
                        continue
                    if bid == WATER:
                        if wtop[k] < 0:
                            wtop[k] = y
                        nxt.append(k)
                        continue
                    if wtop[k] >= 0:
                        hts[p], ids[p], depth[p] = wtop[k], WATER, min(255, wtop[k] - y)
                    else:
                        hts[p], ids[p] = y, bid
                rem = nxt
                if not rem:
                    break
            for k in rem:  # water all the way down
                if wtop[k] >= 0:
                    p = (oz + (k >> 5)) * W + ox + (k & 31)
                    hts[p], ids[p], depth[p] = wtop[k], WATER, 255
            if progress:
                progress((n + 1) / len(alloc))

    def main_bbox(self):
        """Pixel box (x0, z0, x1, z1) of the largest connected group of chunks.

        Islands keep a few stray chunks far out in the corners; this is the part worth looking at."""
        todo, best = set(self._cells), None
        while todo:
            stack, group = [todo.pop()], []
            while stack:
                cx, cz = stack.pop()
                group.append((cx, cz))
                for n in ((cx + 1, cz), (cx - 1, cz), (cx, cz + 1), (cx, cz - 1)):
                    if n in todo:
                        todo.remove(n)
                        stack.append(n)
            if best is None or len(group) > len(best):
                best = group
        xs, zs = [c[0] for c in best], [c[1] for c in best]
        return min(xs) * 32, min(zs) * 32, (max(xs) + 1) * 32, (max(zs) + 1) * 32

    # world block coordinates <-> image pixels
    def to_pixel(self, x, z):
        return x - self.x0, z - self.z0

    def info_at(self, px, pz):
        """(world x, height, world z, block id) under an image pixel, or None."""
        if not (0 <= px < self.width and 0 <= pz < self.height):
            return None
        p = pz * self.width + px
        if self.heights[p] == self.NO_DATA:
            return None
        return px + self.x0, self.heights[p], pz + self.z0, self.ids[p]

    def render(self, objects=True):
        """PIL RGB image, 1 pixel per block column."""
        if Image is None:
            raise RuntimeError('Pillow is needed to draw maps')
        W, H = self.width, self.height
        hts, ids, depth, objs = self.heights, self.ids, self.depth, self.objects
        bg = BACKGROUND
        buf = bytearray(bytes(bg) * (W * H))
        cache = {}
        NO, WATER = self.NO_DATA, self.WATER
        for p in range(W * H):
            h = hts[p]
            if h == NO:
                continue
            bid = ids[p]
            if bid == WATER:
                dp = depth[p]
                t = min(dp, 24) / 24
                r, g, b = int(86 - 50 * t), int(170 - 78 * t), int(226 - 62 * t)
            else:
                base = cache.get(bid)
                if base is None:
                    base = cache[bid] = block_color(bid)
                # relief: light from the north-west, plus a little brightening with altitude
                q = p - W - 1
                slope = 0
                if p % W and q >= 0 and hts[q] != NO:
                    slope = h - hts[q]
                    slope = 3 if slope > 3 else -3 if slope < -3 else slope
                f = 0.82 + (h - 31) * 0.006 + slope * 0.07
                f = 0.45 if f < 0.45 else 1.3 if f > 1.3 else f
                r, g, b = base
                r, g, b = min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f))
            if objects and objs[p]:
                r, g, b = (r * 3 + 60) >> 2, (g * 3 + 40) >> 2, (b * 3 + 50) >> 2
            i = p * 3
            buf[i], buf[i + 1], buf[i + 2] = r, g, b
        return Image.frombytes('RGB', (W, H), bytes(buf))

    def top_blocks(self, n=12):
        from collections import Counter
        c = Counter(self.ids[p] for p in range(self.width * self.height) if self.heights[p] != self.NO_DATA)
        return c.most_common(n)


BACKGROUND = (24, 28, 36)
# Hand-picked colours for the most common surface blocks. The ids have no public names;
# these are guesses from where they appear. Anything else gets a stable muted colour.
BLOCK_COLORS = {}


def block_color(bid):
    c = BLOCK_COLORS.get(bid)
    if c:
        return c
    h = (bid * 2654435761) & 0xFFFFFFFF
    # muted earth/green range so unknown blocks still read as terrain
    return 110 + (h & 63), 120 + (h >> 8 & 63), 80 + (h >> 16 & 47)


_MAP_PARTS = None


def map_part(variation):
    """(base part, item id, width, height, depth, can_edit) for a placed-object variation, from
    data/map_parts.bin (4096 x 8 bytes). None if unknown."""
    global _MAP_PARTS
    if _MAP_PARTS is None:
        _MAP_PARTS = {}
        try:
            with open(os.path.join(DATA, 'map_parts.bin'), 'rb') as f:
                b = f.read()
            if len(b) == 4096 * 8:
                for i, rec in enumerate(struct.iter_unpack('<HHBBBB', b)):
                    if rec[1] or rec[0]:
                        _MAP_PARTS[i] = (rec[0], rec[1], rec[2], rec[3], rec[4], bool(rec[5]))
        except OSError:
            pass
    return _MAP_PARTS.get(variation)


def placeable_items():
    """{item id: (width, height, depth)} for every item that can be placed on an island."""
    map_part(0)
    out = {}
    for base, item, w, h, d, _ in _MAP_PARTS.values():
        if item and item not in out:
            out[item] = (w, h, d)
    return out


def homes_on(common, area):
    """[(resident index, name, x, y, z)] for residents whose home is on this island."""
    out = []
    for i in common.villagers():
        v = common.get_villager(i)
        if v['home_type'] and v['home_area'] == area and v['home_xyz']:
            x, y, z = v['home_xyz']
            out.append((i, v['name'], x, y, z))
    return out


# ---------------------------------------------------------------- photos
class PhotoAlbum:
    """In-game photos stored in G00/SCSHDAT.BIN (plain JPEGs inside a zlib stream)."""
    HEADER = 0x40
    SLOT = 0x3E800

    def __init__(self, path):
        self.path = path
        self.photos = []  # raw JPEG bytes, exactly as stored
        with open(path, 'rb') as f:
            o = f.read()
        if len(o) < self.HEADER or struct.unpack_from('<I', o, 0)[0] != ps.MAGIC:
            raise ps.FormatError('Not a Pokopia photo file')
        length = struct.unpack_from('<I', o, 0x10)[0]
        if not (self.HEADER < length <= len(o)):
            raise ps.FormatError('Compressed length field is invalid')
        try:
            d = zlib.decompress(o[self.HEADER:length])
        except zlib.error as e:
            raise ps.FormatError(f'zlib error: {e}')
        i = d.find(b'\xff\xd8\xff')
        while i >= 0:
            nxt = d.find(b'\xff\xd8\xff', i + 3)
            chunk = d[i:min(i + self.SLOT, nxt if nxt >= 0 else len(d))]
            end = chunk.rfind(b'\xff\xd9')
            if end > 0:
                jpg = chunk[:end + 2]
                if self._valid(jpg):
                    self.photos.append(jpg)
            i = nxt

    @staticmethod
    def _valid(jpg):
        if Image is None:
            return True
        try:
            Image.open(io.BytesIO(jpg)).verify()
            return True
        except Exception:
            return False

    def __len__(self):
        return len(self.photos)

    def image(self, i):
        return Image.open(io.BytesIO(self.photos[i]))

    def export(self, folder, which=None):
        os.makedirs(folder, exist_ok=True)
        out = []
        for i in (range(len(self.photos)) if which is None else which):
            p = os.path.join(folder, f'pokopia_photo_{i + 1:02}.jpg')
            with open(p, 'wb') as f:
                f.write(self.photos[i])
            out.append(p)
        return out


# ---------------------------------------------------------------- backups
def list_backups(root=None):
    root = root or ps.default_backup_root()
    out = []
    if not os.path.isdir(root):
        return out
    for name in os.listdir(root):
        p = os.path.join(root, name)
        f = os.path.join(p, 'G00', 'CMNDAT.BIN')
        if not os.path.isfile(f):
            continue
        e = dict(path=p, name=name, when=datetime.datetime.fromtimestamp(os.path.getmtime(f)),
                 player='?', items=0, residents=0, playtime=None, error='')
        try:
            c = ps.CommonSave(f)
            e.update(player=c.player_name, items=len(c.filled_slots()), residents=len(c.villagers()), playtime=c.play_seconds)
        except Exception as ex:
            e['error'] = str(ex)
        out.append(e)
    out.sort(key=lambda e: e['when'], reverse=True)
    return out


def create_backup(folder, root=None, tag='manual'):
    root = root or ps.default_backup_root()
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(root, f'{tag}_{ts}')
    n = 1
    while os.path.exists(dst):
        n += 1
        dst = os.path.join(root, f'{tag}_{ts}_{n}')
    shutil.copytree(folder, dst)
    return dst


def restore_backup(backup, live, root=None):
    """Replace the save folder `live` with a copy of `backup`. The current contents are backed up first.

    Returns the path of that safety backup."""
    backup, live = os.path.abspath(backup), os.path.abspath(live)
    if os.path.normcase(backup) == os.path.normcase(live):
        raise ValueError('That backup is the folder that is open')
    ps.SaveFolder(backup)  # must be a readable save
    if not os.path.isdir(live):
        raise ValueError('Save folder does not exist')
    safety = create_backup(live, root, 'before_restore')
    staging, old = live + '.restore_tmp', live + '.old_tmp'
    for p in (staging, old):
        if os.path.exists(p):
            raise ValueError(f'Leftover folder from an earlier restore: {p}')
    shutil.copytree(backup, staging)
    os.rename(live, old)
    try:
        os.rename(staging, live)
    except OSError:
        os.rename(old, live)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)
    ps.SaveFolder(live)  # verify
    return safety


# ---------------------------------------------------------------- save detection
TITLE_ID = '0400A3A01EE4C000'          # Pokopia's save folder name in yuzu-family emulators
YUZU_FAMILY = ('eden', 'yuzu', 'suyu', 'sudachi', 'citron', 'torzu')


def _data_roots(name):
    """Where an emulator keeps its user data on this OS (default install, not portable)."""
    home = os.path.expanduser('~')
    if sys.platform == 'win32':
        bases = [os.environ.get('APPDATA', ''), os.environ.get('LOCALAPPDATA', '')]
    elif sys.platform == 'darwin':
        bases = [os.path.join(home, 'Library', 'Application Support')]
    else:
        bases = [os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share'),
                 os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')]
    out = []
    for b in bases:
        try:
            names = os.listdir(b) if b else []
        except OSError:
            continue
        out += [os.path.join(b, n) for n in names if n.lower() == name.lower() and os.path.isdir(os.path.join(b, n))]
    return out


def _configured_nand(root):
    """Custom NAND folder from a yuzu-family qt-config.ini, if the user moved it."""
    for ini in (os.path.join(root, 'config', 'qt-config.ini'), os.path.join(root, 'qt-config.ini')):
        try:
            with open(ini, encoding='utf-8', errors='replace') as f:
                for line in f:
                    if line.startswith('nand_directory='):
                        v = line.split('=', 1)[1].strip().strip('"')
                        if v:
                            return os.path.normpath(v)
        except OSError:
            pass
    return None


def save_header(folder):
    """(magic ok, version) of a candidate save folder's G00/CMNDAT.BIN, or None if it has none."""
    p = os.path.join(folder, 'G00', 'CMNDAT.BIN')
    try:
        with open(p, 'rb') as f:
            magic, ver = struct.unpack('<II', f.read(8))
    except (OSError, struct.error):
        return None
    return magic == ps.MAGIC, ver


def _walk_for_saves(root, max_depth=8):
    """Folders under root (inclusive) that contain G00/CMNDAT.BIN, for a folder the user picked by hand."""
    root = os.path.normpath(root)
    base = root.count(os.sep)
    for dp, dirs, files in os.walk(root):
        if 'G00' in dirs:
            yield dp
        if dp.count(os.sep) - base >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in ('G00', 'B00', 'S00') and not d.startswith('.')]


def find_saves(extra_roots=(), defaults=True):
    """Every Pokopia save folder found in the default emulator locations (and inside extra_roots), newest first.
    Returns dicts: folder, emulator, profile, saved (datetime), supported (bool)."""
    cands = []  # (folder, emulator, profile)
    for name in YUZU_FAMILY if defaults else ():
        for root in _data_roots(name):
            nands = [os.path.join(root, 'nand')]
            custom = _configured_nand(root)
            if custom:
                nands.insert(0, custom)
            for nand in nands:
                for f in glob.glob(os.path.join(nand, 'user', 'save', '*', '*', TITLE_ID)):
                    cands.append((f, name.capitalize(), os.path.basename(os.path.dirname(f))))
    for root in _data_roots('Ryujinx') if defaults else ():
        for f in glob.glob(os.path.join(root, 'bis', 'user', 'save', '*', '[01]')):
            cands.append((f, 'Ryujinx', os.path.basename(os.path.dirname(f))))
    for root in extra_roots:
        for f in _walk_for_saves(root):
            cands.append((f, 'Custom', ''))
    seen, out = set(), []
    for folder, emu, profile in cands:
        key = os.path.normcase(os.path.realpath(folder))
        if key in seen:
            continue
        seen.add(key)
        h = save_header(folder)
        if not h or not h[0]:
            continue
        mtime = os.path.getmtime(os.path.join(folder, 'G00', 'CMNDAT.BIN'))
        out.append(dict(folder=os.path.normpath(folder), emulator=emu, profile=profile,
                        saved=datetime.datetime.fromtimestamp(mtime), supported=h[1] == ps.VERSION))
    out.sort(key=lambda e: e['saved'], reverse=True)
    return out


def default_save():
    """The most recently saved supported Pokopia save, or None."""
    return next((e['folder'] for e in find_saves() if e['supported']), None)


# ---------------------------------------------------------------- emulator check
EMULATORS =('eglantine', 'pokedinner', 'eden','yuzu', 'ryujinx', 'citron', 'sudachi', 'suyu', 'torzu')


def running_emulators():
    """Names of Switch emulator processes that are running right now (Windows only)."""
    if sys.platform != 'win32':
        return []
    try:
        r = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        return []
    found = set()
    for line in r.stdout.splitlines():
        exe = line.split(',')[0].strip('"').lower()
        if exe.endswith('.exe') and any(exe.startswith(e) for e in EMULATORS):
            found.add(exe)
    return sorted(found)


# ---------------------------------------------------------------- icons
class Icons:
    """Maps item ids / resident indexes / moves / emotes to the PNG files fetched by tools/fetch_icons.py."""
    FALLBACK_ITEM = 565

    def __init__(self):
        icons = os.path.join(DATA, 'icons')
        self.item_dir = os.path.join(icons, 'items')
        self.vil_dir = os.path.join(icons, 'villagers')
        self.skill_dir = os.path.join(icons, 'skills')
        self.reaction_dir = os.path.join(icons, 'reactions')
        self.item_map = self._table('item_menuicon.bin')
        self.vil_map = self._table('villager_portrait.bin')
        self.available = Image is not None and os.path.isdir(self.item_dir) and bool(self.item_map)
        self.villagers_available = Image is not None and os.path.isdir(self.vil_dir) and bool(self.vil_map)

    @staticmethod
    def _table(name):
        try:
            with open(os.path.join(DATA, name), 'rb') as f:
                b = f.read()
        except OSError:
            return ()
        return struct.unpack(f'<{len(b) // 2}H', b[:len(b) // 2 * 2])

    def has_item_icon(self, item_id):
        return bool(item_id) and item_id < len(self.item_map) and bool(self.item_map[item_id])

    def item_path(self, item_id, fallback=True):
        """PNG for an item. Without an icon of its own: the leaf icon, or None when fallback=False."""
        if not item_id or not self.available:
            return None
        n = self.item_map[item_id] if item_id < len(self.item_map) else 0
        for cand in ((n, self.FALLBACK_ITEM) if fallback else (n,)):
            if cand:
                p = os.path.join(self.item_dir, f'item_{cand:04}.png')
                if os.path.isfile(p):
                    return p
        return None

    def villager_path(self, index):
        if not self.villagers_available:
            return None
        n = self.vil_map[index] if 0 <= index < len(self.vil_map) else 0
        if not n:
            return None
        p = os.path.join(self.vil_dir, f'villager_{n:04}.png')
        return p if os.path.isfile(p) else None

    def _numbered(self, folder, prefix, i):
        p = os.path.join(folder, f'{prefix}_{i:04}.png')
        return p if Image is not None and os.path.isfile(p) else None

    def skill_path(self, skill_id):
        return self._numbered(self.skill_dir, 'skill', skill_id)

    def reaction_path(self, reaction_id):
        return self._numbered(self.reaction_dir, 'reaction', reaction_id)
