# Linux port modifications by frinimini, 2026-11-24. See CREDITS.md.
"""Talk to a running Pokopia in a yuzu-family emulator (Windows and Linux): change the player's form while playing.

The emulator maps the game's memory into its own process in one block ("fastmem"), so a game address is at
host address = arena + game address. This module finds that block, checks that the mod's patch is loaded,
and writes the same few values the mod's button-combo cheat writes. It never touches a save file.

Offsets are for Pokopia 2.0.0, update 655360 (build 76A489F3BD3642FA), the build the mods are made for.
"""
import ctypes, glob, hashlib, os, struct, subprocess, sys

import pokopia_extras as px

BUILD_ID = '76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E'
HEAD_SHA256 = 'a8e03f9572c9688f55057ef2e8d8bd4c1faa36549c9dbe081ea8fdeb1f6effe7'  # first 0x100 bytes of main
SELF_PTR = (0x3483AB8, 0x35618F0)  # main+a holds the game address of main+b: gives the game-side base of main
PLAYER_PTR = 0x3561928             # player object = [[main + this] + 0x30]
FORM = 0x3D14C00                   # u16 the patch reads: form to hold (0 = off)
SELECTED = 0x3D14C06               # u16 the cheat reads: form its button combo turns you into
POSITION = 0x3D14C1A               # u16 the cheat keeps: SELECTED's place in the A-Z list + 1 (0 = not in it)
P_CURRENT, P_DESIRED = 0x5A44, 0x5A46
P_STATE, P_ANIM, P_GO = 0x3788, 0x378A, 0x378C
ANIM_TRANSFORM = 0x3B2
HUMAN = 1

PROCESS_ACCESS = 0x400 | 0x10 | 0x20 | 0x8  # query, read, write, operation
MEM_COMMIT, MEM_MAPPED = 0x1000, 0x40000


class LiveError(Exception):
    """A message that can be shown to the user as is."""


class _MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', ctypes.c_uint32), ('PartitionId', ctypes.c_uint16),
                ('RegionSize', ctypes.c_size_t), ('State', ctypes.c_uint32),
                ('Protect', ctypes.c_uint32), ('Type', ctypes.c_uint32)]


def _kernel32():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    vp, sz = ctypes.c_void_p, ctypes.c_size_t
    k.OpenProcess.restype = vp
    k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    k.CloseHandle.argtypes = [vp]
    k.VirtualQueryEx.restype = sz
    k.VirtualQueryEx.argtypes = [vp, vp, ctypes.POINTER(_MBI), sz]
    k.ReadProcessMemory.argtypes = [vp, vp, vp, sz, ctypes.POINTER(sz)]
    k.WriteProcessMemory.argtypes = [vp, vp, vp, sz, ctypes.POINTER(sz)]
    return k


def emulator_pids():
    """[(pid, exe name)] of running Switch emulators."""
    if sys.platform.startswith('linux'):
        out = []
        for entry in glob.glob('/proc/[0-9]*/comm'):
            try:
                with open(entry) as f:
                    name = f.read().strip().lower()
                try:
                    executable = os.path.basename(os.readlink(os.path.join(os.path.dirname(entry), 'exe'))).lower()
                except OSError:
                    executable = name
                if executable.endswith('.appimage'):
                    continue  # AppImage's mount helper is a separate process
                if any(executable.startswith(e) or name.startswith(e) for e in px.EMULATORS):
                    out.append((int(entry.split('/')[2]), executable))
            except OSError:
                pass
        return out
    if sys.platform != 'win32':
        return []
    try:
        r = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[1].isdigit():
            exe = parts[0].lower()
            if exe.endswith('.exe') and any(exe.startswith(e) for e in px.EMULATORS):
                out.append((int(parts[1]), exe))
    return out


def ips_records(data):
    """[(offset in main, bytes)] of an .ips or IPS32 patch for an NSO (file offset = main offset + 0x100)."""
    if data[:5] == b'PATCH':
        i, w, eof = 5, 3, b'EOF'
    elif data[:5] == b'IPS32':
        i, w, eof = 5, 4, b'EEOF'
    else:
        raise ValueError('not an IPS patch')
    out = []
    while data[i:i + w] != eof and i + w + 2 <= len(data):
        off = int.from_bytes(data[i:i + w], 'big')
        n = int.from_bytes(data[i + w:i + w + 2], 'big')
        out.append((off - 0x100, data[i + w + 2:i + w + 2 + n]))
        i += w + 2 + n
    return out


class Game:
    """A running, supported Pokopia inside one emulator process."""

    def __init__(self, k, handle, pid, exe, arena, main):
        self.k, self.handle, self.pid, self.exe, self.arena, self.main = k, handle, pid, exe, arena, main

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None

    # ---- raw access (game addresses) ----
    def read(self, addr, n):
        buf, got = ctypes.create_string_buffer(n), ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.handle, self.arena + addr, buf, n, ctypes.byref(got)) or got.value != n:
            raise LiveError('Lost contact with the game. Is it still running?')
        return buf.raw

    def write(self, addr, data):
        got = ctypes.c_size_t()
        if not self.k.WriteProcessMemory(self.handle, self.arena + addr, data, len(data), ctypes.byref(got)) \
                or got.value != len(data):
            raise LiveError('Could not write to the game. Is it still running?')

    def u16(self, addr):
        return struct.unpack('<H', self.read(addr, 2))[0]

    def u64(self, addr):
        return struct.unpack('<Q', self.read(addr, 8))[0]

    # ---- state ----
    def alive(self):
        try:
            return hashlib.sha256(self.read(self.main, 0x100)).hexdigest() == HEAD_SHA256
        except LiveError:
            return False

    def patch_loaded(self, ips):
        """True if every record of the mod's .ips patch is present in the game's code."""
        return all(self.read(self.main + off, len(data)) == data for off, data in ips_records(ips))

    def player(self):
        """Game address of the player object, or 0 before you are in the world."""
        holder = self.u64(self.main + PLAYER_PTR)
        return self.u64(holder + 0x30) if holder else 0

    def form(self):
        """(form the mod is holding or 0, form the player is in right now or 0)."""
        p = self.player()
        return self.u16(self.main + FORM), (self.u16(p + P_CURRENT) if p else 0)

    def select(self, form, position=0):
        """Set the form the button combo turns you into. position: its place in the A-Z Pokémon list, from 1
        (0 = not in the list); ZL + D-pad Left / Right go on from there."""
        self.write(self.main + SELECTED, struct.pack('<H', form))
        self.write(self.main + POSITION, struct.pack('<H', position))

    def transform(self, form):
        """Turn the player into `form` now (0 = back to your character). Same writes as the button combos."""
        p = self.player()
        if not p:
            raise LiveError('Load into the world first, then try again.')
        target = struct.pack('<H', form or HUMAN)
        self.write(self.main + FORM, struct.pack('<H', form))
        self.write(p + P_DESIRED, target)
        self.write(p + P_ANIM, struct.pack('<H', ANIM_TRANSFORM))
        self.write(p + P_STATE, target)
        self.write(p + P_GO, b'\x01')



class LinuxGame(Game):
    """Access an emulator through Linux procfs with the current user's permissions."""

    def close(self):
        if self.handle is not None:
            os.close(self.handle)
            self.handle = None

    def read(self, addr, n):
        try:
            data = os.pread(self.handle, n, self.arena + addr)
        except OSError as error:
            raise LiveError('Lost contact with the game. Is it still running?') from error
        if len(data) != n:
            raise LiveError('Could not read the complete game memory region.')
        return data

    def write(self, addr, data):
        try:
            written = os.pwrite(self.handle, data, self.arena + addr)
        except OSError as error:
            raise LiveError('Could not write to the game. Is it still running?') from error
        if written != len(data):
            raise LiveError('Could not write the complete game memory region.')


def _attach_linux(pid, exe):
    try:
        handle = os.open(f'/proc/{pid}/mem', os.O_RDWR)
    except PermissionError as error:
        raise LiveError('Linux denied access to the emulator memory. The emulator must allow this '
                        'editor to attach under the system ptrace policy.') from error
    except FileNotFoundError:
        return None
    attached = False
    try:
        with open(f'/proc/{pid}/maps') as maps:
            for line in maps:
                fields = line.split()
                if not fields[1].startswith('r'):
                    continue
                base, end = (int(value, 16) for value in fields[0].split('-'))
                if end - base < 0x100:
                    continue
                try:
                    head = os.pread(handle, 0x100, base)
                    if hashlib.sha256(head).hexdigest() != HEAD_SHA256:
                        continue
                    pointer = os.pread(handle, 8, base + SELF_PTR[0])
                    if len(pointer) != 8:
                        continue
                    main = struct.unpack('<Q', pointer)[0] - SELF_PTR[1]
                    game = LinuxGame(None, handle, pid, exe, base - main, main)
                    if main > 0 and game.alive():
                        attached = True
                        return game
                except OSError:
                    continue  # mappings can disappear while the process runs
    finally:
        if not attached:
            os.close(handle)
    return None


def _attach(k, pid, exe):
    handle = k.OpenProcess(PROCESS_ACCESS, False, pid)
    if not handle:
        return None
    mbi, addr = _MBI(), 0
    head, got = ctypes.create_string_buffer(0x100), ctypes.c_size_t()
    while k.VirtualQueryEx(handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_MAPPED and size >= 0x100 \
                and k.ReadProcessMemory(handle, base, head, 0x100, ctypes.byref(got)) and got.value == 0x100 \
                and head.raw[:4] == b'\x01\0\0\0' and hashlib.sha256(head.raw).hexdigest() == HEAD_SHA256:
            ptr = ctypes.create_string_buffer(8)
            if k.ReadProcessMemory(handle, base + SELF_PTR[0], ptr, 8, ctypes.byref(got)) and got.value == 8:
                main = struct.unpack('<Q', ptr.raw)[0] - SELF_PTR[1]
                game = Game(k, handle, pid, exe, base - main, main)
                if main > 0 and game.alive():
                    return game
        addr = base + size
        if addr >= 0x7FFFFFFF0000:
            break
    k.CloseHandle(handle)
    return None


def connect():
    """Find the running game. Raises LiveError with the reason when it can't."""
    if sys.platform != 'win32' and not sys.platform.startswith('linux'):
        raise LiveError('Live memory editing is supported on Windows and Linux.')
    pids = emulator_pids()
    if not pids:
        raise LiveError('No emulator is running.')
    k = _kernel32() if sys.platform == 'win32' else None
    errors = []
    for pid, exe in pids:
        if k:
            game = _attach(k, pid, exe)
        else:
            try:
                game = _attach_linux(pid, exe)
            except (LiveError, OSError) as error:
                errors.append(f'{exe} (PID {pid}): {error}')
                continue
        if game:
            return game
    if errors:
        raise LiveError('Could not inspect every emulator process. ' + '; '.join(errors) +
                        ' No supported game was found in the accessible processes.')
    raise LiveError('An emulator is running, but Pokopia 2.0.0 (update 655360) was not found in it. '
                    'Start the game first. Emulators other than the Yuzu family are not supported.')
