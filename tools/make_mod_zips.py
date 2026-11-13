"""Build the standalone mod downloads for a release: dist/z-<Mod>-emulator.zip and dist/z-<Mod>-SD-card.zip.

Usage:  py tools\\make_mod_zips.py
Each zip holds the mod's files in that layout (default option) plus its README.
"""
import os, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import pokopia_mods as pm

DIST = os.path.join(HERE, 'dist')
os.makedirs(DIST, exist_ok=True)
for mod in pm.list_mods():
    for layout, tag in (('emulator', 'emulator'), ('sd', 'SD-card')):
        camel = ''.join(w[:1].upper() + w[1:] for w in mod.name.split())  # "Play as Pokemon" -> PlayAsPokemon
        out = os.path.join(DIST, f'z-{camel}-{tag}.zip')
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for path in mod.write(tmp, layout):
                z.write(path, os.path.relpath(path, tmp).replace(os.sep, '/'))
            z.write(os.path.join(mod.folder, 'README.md'), f'{mod.name} README.md')
        print(out)
