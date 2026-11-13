"""Talk to a running Pokopia in a yuzu-family emulator (Windows only): change the player's form while playing.

The emulator maps the game's memory into its own process in one block ("fastmem"), so a game address is at
host address = arena + game address. This module finds that block, checks that the mod's patch is loaded,
and writes the same few values the mod's button-combo cheat writes. It never touches a save file.

Offsets are for Pokopia 2.0.0, update 655360 (build 76A489F3BD3642FA), the build the mods are made for.
"""
import ctypes, hashlib, struct, subprocess, sys

import pokopia_extras as px

BUILD_ID = '76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E'
HEAD_SHA256 = 'a8e03f9572c9688f55057ef2e8d8bd4c1faa36549c9dbe081ea8fdeb1f6effe7'  # first 0x100 bytes of main
SELF_PTR = (0x3483AB8, 0x35618F0)  # main+a holds the game address of main+b: gives the game-side base of main
PLAYER_PTR = 0x3561928             # player object = [[main + this] + 0x30]
FORM = 0x3D14C00                   # u16 the patch reads: form to hold (0 = off)
SELECTED = 0x3D14C06               # u16 the "Any" cheat reads: form its button combo turns you into
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
    """[(offset in main, bytes)] of an .ips patch for an NSO (file offset = main offset + 0x100)."""
    if data[:5] != b'PATCH':
        raise ValueError('not an IPS patch')
    out, i = [], 5
    while data[i:i + 3] != b'EOF' and i + 5 <= len(data):
        off = int.from_bytes(data[i:i + 3], 'big')
        n = int.from_bytes(data[i + 3:i + 5], 'big')
        out.append((off - 0x100, data[i + 5:i + 5 + n]))
        i += 5 + n
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

    def select(self, form):
        """Set the form the "Any" button combo turns you into."""
        self.write(self.main + SELECTED, struct.pack('<H', form))

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
    if sys.platform != 'win32':
        raise LiveError('Changing form while playing only works on Windows.')
    pids = emulator_pids()
    if not pids:
        raise LiveError('No emulator is running.')
    k = _kernel32()
    for pid, exe in pids:
        game = _attach(k, pid, exe)
        if game:
            return game
    raise LiveError('An emulator is running, but Pokopia 2.0.0 (update 655360) was not found in it. '
                    'Start the game first. Emulators other than the Yuzu family are not supported.')
