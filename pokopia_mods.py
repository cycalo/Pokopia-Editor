"""Game mods shipped with Pokopia Editor (mods/<id>/mod.json + files/).

Install into an emulator's load folder, remove again, or export in an emulator or SD-card (Atmosphère) layout.
Only files listed in a mod's manifest are ever written or deleted.
"""
import json, os, shutil, sys

import pokopia_extras as px

HERE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
MODS_DIR = os.path.join(HERE, 'mods')
LAYOUTS = {'emulator': 'Emulator (Eden, Yuzu and forks)', 'sd': 'Switch SD card (Atmosphère-style custom firmware)'}


class Mod:
    def __init__(self, folder):
        self.folder = folder
        with open(os.path.join(folder, 'mod.json'), encoding='utf-8') as f:
            self.meta = json.load(f)
        m = self.meta
        self.id, self.name, self.title_id, self.build_id = m['id'], m['name'], m['title_id'], m['build_id']
        self.files = m['files']  # kind -> file name; kinds: exefs, cheats

    def source(self, kind):
        return os.path.join(self.folder, 'files', self.files[kind])

    def targets(self, root, layout='emulator'):
        """Destination path for each file, below `root` (an emulator load folder, or an SD card / folder)."""
        out = {}
        for kind, fn in self.files.items():
            if layout == 'emulator':
                out[kind] = os.path.join(root, self.title_id, self.name, kind, fn)
            elif kind == 'exefs':
                out[kind] = os.path.join(root, 'atmosphere', 'exefs_patches', self.name, fn)
            else:
                out[kind] = os.path.join(root, 'atmosphere', 'contents', self.title_id, kind, fn)
        return out

    def status(self, load_dir):
        """'installed', 'outdated' (different files there), or 'missing'."""
        states = []
        for kind, dst in self.targets(load_dir).items():
            if not os.path.isfile(dst):
                states.append('missing')
            else:
                with open(dst, 'rb') as a, open(self.source(kind), 'rb') as b:
                    states.append('installed' if a.read() == b.read() else 'outdated')
        if all(s == 'installed' for s in states):
            return 'installed'
        return 'missing' if all(s == 'missing' for s in states) else 'outdated'

    def write(self, root, layout='emulator'):
        written = []
        for kind, dst in self.targets(root, layout).items():
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(self.source(kind), dst)
            written.append(dst)
        return written

    def remove(self, load_dir):
        """Delete this mod's files from an emulator load folder, then its folders if they are left empty."""
        removed = []
        for dst in self.targets(load_dir).values():
            if os.path.isfile(dst):
                os.remove(dst)
                removed.append(dst)
        mod_root = os.path.join(load_dir, self.title_id, self.name)
        for d in (os.path.join(mod_root, k) for k in self.files):
            _rmdir_if_empty(d)
        _rmdir_if_empty(mod_root)
        _rmdir_if_empty(os.path.join(load_dir, self.title_id))
        return removed


def _rmdir_if_empty(d):
    try:
        os.rmdir(d)
    except OSError:
        pass


def list_mods(mods_dir=MODS_DIR):
    out = []
    try:
        names = sorted(os.listdir(mods_dir))
    except OSError:
        return out
    for n in names:
        if os.path.isfile(os.path.join(mods_dir, n, 'mod.json')):
            try:
                out.append(Mod(os.path.join(mods_dir, n)))
            except (OSError, ValueError, KeyError):
                pass
    return out


def _configured_load(root):
    for ini in (os.path.join(root, 'config', 'qt-config.ini'), os.path.join(root, 'qt-config.ini')):
        try:
            with open(ini, encoding='utf-8', errors='replace') as f:
                for line in f:
                    if line.startswith('load_directory='):
                        v = line.split('=', 1)[1].strip().strip('"')
                        if v:
                            return os.path.normpath(v)
        except OSError:
            pass
    return None


def find_load_dirs():
    """[(emulator name, load folder)] for installed yuzu-family emulators (default user folders).

    POKOPIA_MODS_LOAD_DIR replaces the search with one folder (used for testing against a copy)."""
    test = os.environ.get('POKOPIA_MODS_LOAD_DIR')
    if test:
        return [('test folder', test)]
    out, seen = [], set()
    for name in px.YUZU_FAMILY:
        for root in px._data_roots(name):
            d = _configured_load(root) or os.path.join(root, 'load')
            key = os.path.normcase(os.path.abspath(d))
            if key not in seen:
                seen.add(key)
                out.append((os.path.basename(root), d))
    return out
