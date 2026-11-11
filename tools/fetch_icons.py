"""Extract item / resident / move / emote icons and map_parts.bin from a source repo zip.

Usage:  py tools\\fetch_icons.py REPO.zip

Only files whose *base name* matches a known pattern are extracted, and they are
written under data\\ with that base name. Paths inside the archive are never trusted.
"""
import io, os, re, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
RULES = [
    (re.compile(r'^item_\d{4,6}\.png$'), os.path.join(DATA, 'icons', 'items')),
    (re.compile(r'^villager_\d{4,6}\.png$'), os.path.join(DATA, 'icons', 'villagers')),
    (re.compile(r'^skill_\d{4,6}\.png$'), os.path.join(DATA, 'icons', 'skills')),
    (re.compile(r'^reaction_\d{4,6}\.png$'), os.path.join(DATA, 'icons', 'reactions')),
    (re.compile(r'^(item_menuicon|villager_portrait|map_parts)\.bin$'), DATA),
]
MAX_FILE = 4 << 20


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage: py tools\\fetch_icons.py REPO.zip')
    with open(sys.argv[1], 'rb') as f:
        blob = f.read()
    print(f'Archive: {len(blob) / 1e6:.1f} MB')
    counts = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            if info.is_dir() or info.file_size > MAX_FILE:
                continue
            base = info.filename.replace('\\', '/').rsplit('/', 1)[-1]
            for rx, dest in RULES:
                if rx.match(base):
                    os.makedirs(dest, exist_ok=True)
                    with open(os.path.join(dest, base), 'wb') as f:
                        f.write(z.read(info))
                    counts[dest] = counts.get(dest, 0) + 1
                    break
    for dest, n in counts.items():
        print(f'{n:5} files -> {dest}')
    if not counts:
        sys.exit('No icon files found in the archive.')


if __name__ == '__main__':
    main()
