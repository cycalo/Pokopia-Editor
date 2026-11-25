"""Build data/quests.json (what each quest does) from a RomFS dump.

Usage: py tools\\extract_quest_table.py ROMFS_DIR [--check]

Quest ids 0-1000 live in six LINKDATA tables (entries of LD_C0_R.BIN, index in LI_C0_R.IDX), each a 0x40-byte
header and 184-byte records. Record i of a table is quest base + i (own finding, 2026-11-25: the moves the
records teach line up with the quests a player saw teach them):

  1206 Withered Wasteland   0-160     1204 Bleak Beach         160-320    1205 Rocky Ridges     320-480
  1210 Sparkling Skylands 480-640     1207 641-800 (painting)  640-800    1203 Bubbly Basin     800-1000

Each record holds 4 commands run when the quest completes (type bytes +0xA9..+0xAC, params at +0x0E + 16*slot) and
4 run when it starts (types +0xB1..+0xB4, table 1203 +0xB3..+0xB6; params at +0x68 + 16*slot). A command is a
type byte and 8 u16 params. Byte +0xA8 is a kind (1 = Pokémon request, 7/9 = main story; not fully decoded).
Unused records (all zero) are left out. Nothing is downloaded.

Titles (own finding, 2026-11-25): for kind 1 (Pokémon requests) u16 +0 is a row of the English request-title text
table 5195. Checked against titles a player wrote down while playing: "Water dry grass!" teaches Leafage, "Sturdy
sticks, please!" teaches Cut, "Househunting!", "Grow some beans!", "Rock Smash your way to treasure!", "Place the
Ditto flag!". Other kinds use +0 for something else, so they get no title. Title placeholders are filled from the
item table 983 (u16 +34 = row of the item-name table 4646: singular, -, plural) and data/skill.txt, habitat.txt,
villager.txt.
"""
import re
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_item_tags import read_entry  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'quests.json')
HEADER, SIZE = 0x40, 184
TABLES = ((1206, 0, 161), (1204, 160, 161), (1205, 320, 161), (1210, 480, 161), (1207, 640, 161), (1203, 800, 201))


def commands(rec, types, params):
    out = []
    for s in range(4):
        t = rec[types + s]
        if t:
            p = list(struct.unpack_from('<8H', rec, params + 16 * s))
            while p and not p[-1]:
                p.pop()
            out.append([t] + p)
    return out


REQUEST_KIND, REQUEST_TITLES, ITEM_TABLE, ITEM_NAMES = 1, 5195, 983, 4646


def text_at(t, field):
    s = field + struct.unpack_from('<I', t, field)[0]
    return t[s:t.index(b'\0', s)].decode('utf-8')


def lines(name):
    with open(os.path.join(ROOT, 'data', name), encoding='utf-8') as f:
        return f.read().replace('\r', '').split('\n')


class Titles:
    def __init__(self, romfs):
        self.req = read_entry(romfs, REQUEST_TITLES)
        self.items = read_entry(romfs, ITEM_TABLE)
        self.names = read_entry(romfs, ITEM_NAMES)
        self.word = {'sklname': lines('skill.txt'), 'hatname': lines('habitat.txt'), 'cname': lines('villager.txt')}
        self.unknown = set()

    def item(self, i, plural):
        row = struct.unpack_from('<H', self.items, HEADER + i * 68 + 34)[0]
        field = HEADER + row * 32 + (8 if plural else 0)
        return text_at(self.names, field) if row and struct.unpack_from('<I', self.names, field)[0] else ''

    def title(self, row):
        if not 0 < row < struct.unpack_from('<I', self.req)[0]:
            return ''
        raw = text_at(self.req, HEADER + row * 8)
        out, cap, plural = '', False, False
        for tag, word in re.findall(r'<([^<>]*)>|([^<]+)', raw):
            if word:
                out += word
                continue
            m = re.fullmatch(r'\$?(\w+)(?:;\d+)?\(?(\d*)\)?', tag)
            name, arg = (m.group(1), int(m.group(2) or 0)) if m else (tag, 0)
            text = ''
            if name == 'fcap':
                cap = True
            elif name == 'fqty':
                plural = arg != 1
            elif name == 'iname':
                text = self.item(arg, plural)
            elif name in self.word:
                lst = self.word[name]
                text = lst[arg] if arg < len(lst) else ''
            elif name not in ('cdef', '/color', 'iicon'):
                self.unknown.add(name)   # a word the editor cannot fill: no title rather than a broken one
                return ''
            if text:
                out += text[:1].upper() + text[1:] if cap or not out else text
                cap = plural = False
        return re.sub(r'\s+', ' ', out).replace(' !', '!').strip()


def build(romfs):
    titles = Titles(romfs)
    quests = {}
    for entry, base, count in TABLES:
        t = read_entry(romfs, entry)
        if struct.unpack_from('<I', t)[0] != count or len(t) < HEADER + count * SIZE:
            raise ValueError(f'table {entry} does not look like {count} x {SIZE} records; different game version?')
        start_types = 0xB3 if entry == 1203 else 0xB1
        for i in range(1, count):
            rec = t[HEADER + i * SIZE:HEADER + (i + 1) * SIZE]
            if not any(rec):
                continue
            q = {'kind': rec[0xA8]}
            if rec[0xA8] == REQUEST_KIND:
                title = titles.title(struct.unpack_from('<H', rec, 0)[0])
                if title:
                    q['title'] = title
            done, start = commands(rec, 0xA9, 0x0E), commands(rec, start_types, 0x68)
            if done:
                q['done'] = done
            if start:
                q['start'] = start
            quests[str(base + i)] = q
    if titles.unknown:
        print('titles left out for placeholders:', ', '.join(sorted(titles.unknown)), file=sys.stderr)
    return json.dumps(quests, ensure_ascii=False, separators=(',', ':'), sort_keys=False) + '\n'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        sys.exit(__doc__)
    romfs = args[0]
    if not os.path.isfile(os.path.join(romfs, 'LI_C0_R.IDX')):
        sys.exit(f'No LI_C0_R.IDX in {romfs}; point this at the dumped romfs folder.')
    text = build(romfs)
    if '--check' in sys.argv:
        with open(OUT, encoding='utf-8') as f:
            same = f.read() == text
        print('data/quests.json is up to date' if same else 'data/quests.json differs from the game files')
        sys.exit(0 if same else 1)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(f'wrote {OUT}: {len(json.loads(text))} quests')


if __name__ == '__main__':
    main()
