"""Build data/item_tag.bin from a RomFS dump: one byte per item ID, 0 = base game, 1 = Expansion Pass, 2 = event.

Usage: py tools\\extract_item_tags.py ROMFS_DIR

The game's item table is entry 983 of LD_C0_R.BIN (index in LI_C0_R.IDX): a 0x40-byte header, then one 68-byte record
per item ID. Byte 57 is the collection group the game files the item under (1 main, 2 event, 3 Bubbly Basin) and
byte 60 is set on items that need the Expansion Pass. Own finding, 2026-11-14; nothing is downloaded.
"""
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'item_tag.bin')
ITEM_TABLE, HEADER, RECORD = 983, 0x40, 68
BASE, DLC, EVENT = 0, 1, 2


def read_entry(romfs, n):
    with open(os.path.join(romfs, 'LI_C0_R.IDX'), 'rb') as f:
        f.seek(n * 32)
        off, size, packed, compressed = struct.unpack('<QQQQ', f.read(32))
    with open(os.path.join(romfs, 'LD_C0_R.BIN'), 'rb') as f:
        f.seek(off)
        buf = f.read(packed)
    if not compressed:
        return buf
    _, chunks, total = struct.unpack_from('<III', buf, 0)
    sizes = struct.unpack_from(f'<{chunks}I', buf, 12)
    pos = (12 + 4 * chunks + 0x7f) & ~0x7f
    out = bytearray()
    for s in sizes:
        n_bytes = struct.unpack_from('<I', buf, pos)[0]
        out += zlib.decompress(buf[pos + 4:pos + 4 + n_bytes])
        pos = (pos + s + 0x7f) & ~0x7f
    if len(out) != total or len(out) != size:
        raise ValueError(f'unpacked {len(out)} bytes, expected {size}')
    return bytes(out)


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: py tools\\extract_item_tags.py ROMFS_DIR')
    romfs = sys.argv[1]
    if not os.path.isfile(os.path.join(romfs, 'LI_C0_R.IDX')):
        sys.exit(f'No LI_C0_R.IDX in {romfs}; point this at the dumped romfs folder.')
    table = read_entry(romfs, ITEM_TABLE)
    count = (len(table) - HEADER) // RECORD
    tags = bytearray(count)
    for i in range(count):
        r = table[HEADER + i * RECORD:HEADER + (i + 1) * RECORD]
        tags[i] = DLC if r[57] == 3 or r[60] == 1 else EVENT if r[57] == 2 else BASE
    with open(OUT, 'wb') as f:
        f.write(tags)
    print(f'{count} items -> {OUT}: {tags.count(DLC)} Expansion Pass, {tags.count(EVENT)} event')


if __name__ == '__main__':
    main()
