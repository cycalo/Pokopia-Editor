"""Extract outfit and hairstyle icons from your own Pokopia RomFS dump.

Usage:  py tools\\extract_wardrobe_icons.py ROMFS_DIR

ROMFS_DIR is the dumped romfs folder (the one holding motor_asset_re). The game files are only read.
Icons are written to data\\icons\\wardrobe as outfit_<name>.png and hair_<name>.png; the Wardrobe page
uses them in place of its emoji tiles. Needs Pillow.

How the files are laid out (Koei Tecmo "motor" engine, Switch 2):
  *.fdata    PDRK header, then IDRK entries: u64 entry size, u64 packed size, u64 size, u32, u32 id, u32 type.
             The payload is one or more zlib streams.
  G1T        texture container; BC3 (0x62), BC7 (0x66) or RGBA8 (0x0a), in a block-linear layout whose
             64x8 GOB order differs from the Switch 1 one (see deswizzle).
  atlas      UI sprite table: u32 count, then 0x68-byte records of name[0x40], u32 page, 8 floats (UV quad).
"""
import glob, os, struct, sys, unicodedata, zlib

try:
    from PIL import Image
except ImportError:
    sys.exit('Pillow is needed: py -m pip install pillow')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'icons', 'wardrobe')

TYPE_TEXTURE = 0xafbec60c
TYPE_ATLAS = 0xf20de437
# (atlas table id, texture id): the base-game character-creator atlas, and the one added by an update
ATLASES = ((0x042ec9ac, 0x58e68df7), (0xff01327b, 0x8a33b646))

# Sprite numbers. The outfit sprites follow the game's outfit name list except for three swapped pairs
# (Cool/Fresh, Chic/Sporty, Sightseer/Professor); the hairstyle sprites are in their own order.
# Matched by eye against named in-game screenshots.
OUTFIT_SPRITE = {
    'Familiar 1': 1, 'Familiar 2': 2, 'Pokémon Center': 3, 'Team Rocket': 4, 'Rock-solid': 5, 'Ranger': 6,
    'Ninja': 7, 'Psychic Master': 8, 'Black Belt': 9, 'Sailor': 10, 'Super Nerd': 11, 'Roughneck': 12,
    'Bird Keeper': 13, 'Red': 14, 'Cool': 15, 'Fresh': 16, 'Rascal': 17, 'Cozy': 18, 'Chic': 19, 'Sporty': 20,
    'Sightseer': 21, 'Professor': 22, 'Mermaid': 23, 'Preschooler': 24, 'Triathlete': 27}
HAIR_SPRITE = {
    'Buns': 1, 'Two-block cut': 2, 'Braided pigtails': 3, 'Locs': 4, 'Curly': 5, 'Shaved': 6, 'Parted': 7,
    'Fluffy': 8, 'Mermaid': 9, 'Winged pigtails': 10, 'Sideswept': 11, 'Simple': 12, 'Long bangs': 13,
    'Short': 14, 'Pigtails': 15, 'Long': 16, 'Crested': 17, 'Ponytail': 18, 'Messy short': 19, 'Side tails': 20}


def slug(name):
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return ''.join(c if c.isalnum() else '_' for c in s).strip('_')


# ---------- fdata ----------
def _inflate(buf, size):
    out, pos = bytearray(), 0
    while len(out) < size:
        i = buf.find(b'\x78', pos)
        if i < 0:
            break
        d = zlib.decompressobj()
        try:
            out += d.decompress(buf[i:])
        except zlib.error:
            pos = i + 1
            continue
        pos = len(buf) - len(d.unused_data)
    if len(out) != size:
        raise ValueError(f'unpacked {len(out)} bytes, expected {size}')
    return bytes(out)


def find_entries(romfs, wanted):
    """{(type, id): payload} for the wanted entries, searched across every fdata archive."""
    found = {}
    for path in glob.glob(os.path.join(romfs, 'motor_asset_re', '*', '**', '*.fdata'), recursive=True):
        with open(path, 'rb') as f:
            if f.read(8) != b'PDRK0000':
                continue
            off = struct.unpack('<Q', f.read(8))[0]
            while True:
                f.seek(off)
                h = f.read(0x2c)
                if len(h) < 0x2c or h[:8] != b'IDRK0000':
                    break
                esize, packed, size = struct.unpack_from('<QQQ', h, 8)
                eid, etype = struct.unpack_from('<II', h, 0x24)
                if (etype, eid) in wanted and (etype, eid) not in found:
                    f.seek(off + esize - packed)
                    found[(etype, eid)] = _inflate(f.read(packed), size)
                off = (off + esize + 15) & ~15
        if len(found) == len(wanted):
            break
    return found


# ---------- textures ----------
def deswizzle(src, w, h, bpp):
    """Switch 2 block-linear to linear. w, h in elements (BC blocks or pixels), bpp bytes per element."""
    if bpp == 4:              # treat 4 pixels as one 16-byte element; the GOB layout is byte based
        w, bpp = w // 4, 16
    bh = 1
    while bh < 16 and bh * 8 < h:
        bh *= 2
    gobs_w = (w * bpp + 63) // 64
    out = bytearray(w * h * bpp)
    for y in range(h):
        yi = y % 8
        base = (y // (8 * bh)) * 512 * bh * gobs_w + ((y % (8 * bh)) // 8) * 512
        ybits = (yi & 1) | ((yi >> 1 & 1) << 1) | ((yi >> 2 & 1) << 3)
        for x in range(w):
            xi = x % 4
            a = base + (x // 4) * 512 * bh + (ybits | ((xi & 1) << 2) | ((xi >> 1 & 1) << 4)) * 16
            o = (y * w + x) * bpp
            out[o:o + bpp] = src[a:a + bpp]
    return bytes(out)


def g1t_pages(d):
    if d[:4] != b'GT1G':
        raise ValueError('not a G1T texture')
    table, count = struct.unpack_from('<I', d, 0x0c)[0], struct.unpack_from('<I', d, 0x10)[0]
    offs = [table + struct.unpack_from('<I', d, table + 4 * i)[0] for i in range(count)] + [len(d)]
    pages = []
    for i in range(count):
        o = offs[i]
        fmt, dims = d[o + 1], d[o + 2]
        w, h = 1 << (dims & 15), 1 << (dims >> 4)
        raw = d[o + 8 + struct.unpack_from('<I', d, o + 8)[0]:offs[i + 1]]
        if fmt in (0x62, 0x66):
            px = deswizzle(raw, w // 4, h // 4, 16)
            pages.append(Image.frombytes('RGBA', (w, h), px, 'bcn', (3 if fmt == 0x62 else 7,)))
        elif fmt == 0x0a:
            pages.append(Image.frombytes('RGBA', (w, h), deswizzle(raw, w, h, 4)))
        else:
            pages.append(None)
    return pages


def sprites(table):
    n = struct.unpack_from('<I', table, 0)[0]
    for i in range(n):
        r = 4 + i * 0x68
        name = table[r:r + 0x40].split(b'\0')[0].decode('ascii', 'replace')
        page = struct.unpack_from('<I', table, r + 0x40)[0]
        uv = struct.unpack_from('<8f', table, r + 0x44)
        yield name, page, (min(uv[0::2]), min(uv[1::2]), max(uv[0::2]), max(uv[1::2]))


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: py tools\\extract_wardrobe_icons.py ROMFS_DIR')
    romfs = sys.argv[1]
    if not os.path.isdir(os.path.join(romfs, 'motor_asset_re')):
        sys.exit(f'No motor_asset_re folder in {romfs}; point this at the dumped romfs folder.')
    wanted = {(TYPE_ATLAS, a) for a, _ in ATLASES} | {(TYPE_TEXTURE, t) for _, t in ATLASES}
    print('Searching the archives...')
    found = find_entries(romfs, wanted)
    want = {f'icon_characre_preset_{n:04d}': f'outfit_{slug(k)}' for k, n in OUTFIT_SPRITE.items()}
    want.update({f'icon_characre_hair_{n:04d}': f'hair_{slug(k)}' for k, n in HAIR_SPRITE.items()})
    os.makedirs(OUT, exist_ok=True)
    done = set()
    for atlas, tex in ATLASES:
        if (TYPE_ATLAS, atlas) not in found or (TYPE_TEXTURE, tex) not in found:
            print(f'  atlas {atlas:08x} not found, skipped')
            continue
        pages = g1t_pages(found[(TYPE_TEXTURE, tex)])
        for name, page, (u0, v0, u1, v1) in sprites(found[(TYPE_ATLAS, atlas)]):
            key = name[:-3] if name.endswith('_00') else name   # Familiar 1/2: first colour variant
            if key not in want or key in done or page >= len(pages) or pages[page] is None:
                continue
            im = pages[page]
            W, H = im.size
            icon = im.crop((round(u0 * W), round(v0 * H), round(u1 * W), round(v1 * H)))
            icon.save(os.path.join(OUT, want[key] + '.png'))
            done.add(key)
    missing = sorted(want[k] for k in want if k not in done)
    print(f'{len(done)} icons -> {OUT}')
    if missing:
        print('Missing:', ', '.join(missing))


if __name__ == '__main__':
    main()
