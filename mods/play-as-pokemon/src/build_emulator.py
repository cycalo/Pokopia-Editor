"""Build the emulator / Switch (SD card) version of Play as Pokemon from the Recompia mod's own source.

  py mods\\play-as-pokemon\\src\\build_emulator.py --llvm DIR_WITH_clang_ld.lld_llvm-objcopy_llvm-objdump

Since 1.5 the emulator version is the Recompia mod itself: recompia/play-as-pokemon/src/play_as_pokemon.c compiled for AArch64 with
PAP_SWITCH, plus src/switch/switch_host.c in place of Modtopia (memory, guest calls, the controller through the game's own
nn::hid imports, the clock). It runs inside the game:

  code       main+0x6B32C0, a function nothing calls or points to (the build checks the bytes it replaces: 0x4798 of them)
  variables  unused bss main+0x3D15000..0x3D16000 (zero at start; the initialised ones are copied there at the first hook)
  hooks      every hook point of the Recompia mod's mod.toml (build.py HOOKS) (the same game instructions, checked here): each becomes a branch
             to a trampoline that saves every register, calls the handler, and then either runs the game's own instruction and
             goes on (MT_CONTINUE) or returns from the game's function (MT_HANDLED), as Modtopia's take_over does
  choice     u16 main+0x3D14C06 = the Pokemon ZL + L3 turns you into: the cheat sets it, the Pokopia Editor's live controls too
             (u16 main+0x3D14C00 = the form held, as before)

Every address in the result is PC-relative, so it runs wherever the system loads main. Writes files/<build id>.ips (IPS32) and the
two cheat files (the chosen Pokemon, and "Any"), replacing the 1.3 patch and its cheats.
"""
import argparse, importlib.util, os, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(MOD))
RECOMPIA = os.path.join(REPO, 'recompia', 'play-as-pokemon')
FILES = os.path.join(MOD, 'files')
MAIN_TEXT = os.path.join(REPO, 're', 'build', 'main_text.bin')   # main's code, unpatched (game 2.0.0, update 655360)
IPS_NAME = '76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips'
CHEATS = {'76A489F3BD3642FA.txt': 0x72, '76A489F3BD3642FA.any.txt': 0x46}   # file -> the Pokemon it sets (mod.json default_value)
CHEAT_NAMES = {'76A489F3BD3642FA.txt': 'Play as Pokemon - the chosen Pokemon', '76A489F3BD3642FA.any.txt': 'Play as Pokemon - Any (Ditto first)'}

# Two functions nothing calls, jumps to or points to (Ghidra: no reference, and no qword in the program equals their address;
# re/dump.ps1 dead: and find8:), twins of 0x4798 bytes, debug drawing code: the mod's own code goes in the first; the trampolines,
# switch_host.c, the read-only data and the image of the initialised variables in the second. The live function between them stays.
CAVE, CAVE_END = 0x6B32C0, 0x6B7A58
CAVE2, CAVE2_END = 0x6B8BA0, 0x6BD338
CAVE_HEAD = bytes.fromhex('7f2303d5eb2bb86d')    # pacibsp; stp d11, d10, [sp, #-0x80]! (both)
RAM, RAM_END = 0x3D15000, 0x3D16000           # bss nothing refers to (re/dump.ps1 refsin:)
FORM, SELECTED = 0x3D14C00, 0x3D14C06
HID = {'hid_style_set': 0x27468A0, 'hid_state_fullkey': 0x27468B0, 'hid_state_handheld': 0x27468C0, 'hid_state_joydual': 0x27468D0}
PC_RELATIVE = {'R_AARCH64_ADR_PREL_PG_HI21', 'R_AARCH64_ADD_ABS_LO12_NC', 'R_AARCH64_CALL26', 'R_AARCH64_JUMP26',
               'R_AARCH64_CONDBR19', 'R_AARCH64_TSTBR14', 'R_AARCH64_ADR_PREL_LO21', 'R_AARCH64_LD_PREL_LO19',
               'R_AARCH64_PREL32', 'R_AARCH64_PREL64'} | {f'R_AARCH64_LDST{n}_ABS_LO12_NC' for n in (8, 16, 32, 64, 128)}


def recompia_build():
    spec = importlib.util.spec_from_file_location('recompia_build', os.path.join(RECOMPIA, 'build.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(' '.join(cmd) + '\n' + r.stdout + r.stderr)
    return r.stdout


MID = {'char_setup', 'player_tick', 'face', 'air_menu'}   # hook points inside a function: everything may be live there


def test_branch(off, word):
    """tbz / tbnz at main+off -> (mnemonic, register, bit, target), else None. The trampoline cannot run such an instruction where
    it is (its target is relative to it), so it runs the same test with a branch to the game's target instead."""
    if word & 0x7E000000 != 0x36000000:
        return None
    imm = (word >> 5) & 0x3FFF
    imm -= (1 << 14) if imm & (1 << 13) else 0
    b5 = word >> 31
    return ('tbnz' if word & (1 << 24) else 'tbz', ('x' if b5 else 'w') + str(word & 31), (b5 << 5) | ((word >> 19) & 31), off + 4 * imm)


def trampolines(hooks):
    """One trampoline a hook point. It saves the registers into an MtHookCtx (x[r] at r * 8), calls pap_hook_<name>(it), restores
    them, and then for MT_CONTINUE runs the game's own instruction and goes back to the next one, for MT_HANDLED returns from the
    game's function. At a function's entry only x0..x18, x30 and q0..q7 can hold anything; inside a function (MID) all of x0..x30,
    nzcv and q0..q31 are kept. x16 carries the answer past the restore: nothing at these points uses it (an entry and a call site
    by the ABI, and the model setup main+0x27CAD0..0x27CE6C never touches x16 or x17)."""
    out = ['.section .text.tramp, "ax", %progbits', '.p2align 2']
    for name, off, word, _ in hooks:
        mid = name in MID
        frame, xs, qs = (0x320, range(0, 30, 2), range(0, 32, 2)) if mid else (0x180, range(0, 18, 2), range(0, 8, 2))
        save = [f'  sub sp, sp, #{frame:#x}'] + [f'  stp x{i}, x{i + 1}, [sp, #{i * 8:#x}]' for i in xs]
        save += ['  str x30, [sp, #0xf0]'] + ([] if mid else ['  str x18, [sp, #0x90]'])
        save += ['  mrs x9, nzcv', '  str x9, [sp, #0xf8]'] if mid else []
        save += [f'  stp q{i}, q{i + 1}, [sp, #{0x100 + i * 16:#x}]' for i in qs]
        restore = [f'  ldp q{i}, q{i + 1}, [sp, #{0x100 + i * 16:#x}]' for i in qs]
        restore += ['  ldr x9, [sp, #0xf8]', '  msr nzcv, x9'] if mid else []
        restore += [f'  ldp x{i}, x{i + 1}, [sp, #{i * 8:#x}]' for i in xs if i != 16]   # x16 holds the answer
        restore += ['  ldr x17, [sp, #0x88]'] + ([] if mid else ['  ldr x18, [sp, #0x90]'])
        restore += ['  ldr x30, [sp, #0xf0]', f'  add sp, sp, #{frame:#x}']
        out += [f'.global tramp_{name}', f'tramp_{name}:'] + save + ['  mov x0, sp', f'  bl pap_hook_{name}', '  mov x16, x0']
        tb = test_branch(off, word)
        game = ([f'  {tb[0]} {tb[1]}, #{tb[2]}, 2f   // the test of the game at main+{off:#x}', f'  b ret_{name}', f'2: b tgt_{name}']
                if tb else [f'  .inst {word:#010x}   // the instruction of the game at main+{off:#x}', f'  b ret_{name}'])
        out += restore + ['  cbnz w16, 1f'] + game + ['1:', '  ret', '']
    return '\n'.join(out) + '\n'


def read_ips(d):
    i, w, eof = (5, 3, b'EOF') if d[:5] == b'PATCH' else (5, 4, b'EEOF')
    out = []
    while d[i:i + w] != eof:
        off, n = int.from_bytes(d[i:i + w], 'big'), int.from_bytes(d[i + w:i + w + 2], 'big')
        out.append((off - 0x100, d[i + w + 2:i + w + 2 + n]))
        i += w + 2 + n
    return out


def write_ips32(recs):
    o = bytearray(b'IPS32')
    for off, data in sorted(recs):
        for k in range(0, len(data), 0xF000):   # a record holds at most 0xFFFF bytes
            part = data[k:k + 0xF000]
            o += (off + k + 0x100).to_bytes(4, 'big') + len(part).to_bytes(2, 'big') + part
    return bytes(o + b'EEOF')


def branch(at, to):
    d = (to - at) >> 2
    assert -(1 << 25) <= d < (1 << 25)
    return 0x14000000 | (d & 0x3FFFFFF)


def cheat(file):
    v = CHEATS[file]
    return '\r\n'.join([
        f'[{CHEAT_NAMES[file]}]',
        '400F0000 00000000 00000000',
        f'12050000 {SELECTED:08X} 00000000',   # once, while nothing is chosen (the editor's live controls may choose later)
        f'020F0000 {SELECTED:08X} {v:08X}',
        '20000000', '']) + '\r\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--llvm', required=True, help='folder with clang, ld.lld, llvm-objcopy, llvm-objdump (llvm-mingw has them)')
    a = ap.parse_args()
    tool = lambda n: os.path.join(a.llvm, n + ('.exe' if os.name == 'nt' else ''))
    rb = recompia_build()
    pokemon, experimental, names, a_l, m_z, exp = rb.load_lists()
    rb.write_forms_h(pokemon, experimental, names, exp)
    text = open(MAIN_TEXT, 'rb').read()
    for name, off, word, _ in rb.HOOKS:   # the game instructions the hooks replace must be the ones the Recompia mod expects
        assert struct.unpack_from('<I', text, off)[0] == word, f'{name}: main+{off:#x} is not {word:#x}'
    for at in (CAVE, CAVE2):
        assert text[at:at + len(CAVE_HEAD)] == CAVE_HEAD, f'the unused function at main+{at:#x} is not where it should be'

    build = os.path.join(HERE, 'build')
    os.makedirs(build, exist_ok=True)
    with open(os.path.join(build, 'trampolines.S'), 'w', newline='\n') as f:
        f.write(trampolines(rb.HOOKS))
    flags = ['-target', 'aarch64-none-elf', '-Os', '-std=gnu11', '-ffreestanding', '-fno-builtin', '-fno-pic', '-fno-pie',
             '-fno-jump-tables', '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-mno-outline-atomics', '-mbranch-protection=bti', '-ffunction-sections', '-fdata-sections', '-fno-common', '-DPAP_SWITCH',
             '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable',
             '-Wno-unused-but-set-variable', '-Wno-unused-const-variable',
             '-I', os.path.join(HERE, 'switch'), '-I', os.path.join(RECOMPIA, 'src')]
    objs = []
    for src in (os.path.join(RECOMPIA, 'src', 'play_as_pokemon.c'), os.path.join(HERE, 'switch', 'switch_host.c'),
                os.path.join(build, 'trampolines.S')):
        obj = os.path.join(build, os.path.splitext(os.path.basename(src))[0] + '.o')
        run([tool('clang'), *flags, '-c', src, '-o', obj])
        bad = [l for l in run([tool('llvm-objdump'), '-r', obj]).splitlines()
               if 'R_AARCH64' in l and l.split()[1] not in PC_RELATIVE]
        assert not bad, f'{src}: relocations that depend on where main is loaded (a table of addresses?):\n' + '\n'.join(bad)
        objs.append(obj)

    script = os.path.join(build, 'play_as_pokemon.ld')
    syms = {'pap_main_base': 0, 'pap_form': FORM, 'pap_selected': SELECTED, **HID,
            **{f'ret_{name}': off + 4 for name, off, _, _ in rb.HOOKS},
            **{f'tgt_{name}': test_branch(off, word)[3] for name, off, word, _ in rb.HOOKS if test_branch(off, word)}}
    with open(script, 'w', newline='\n') as f:
        for k, v in syms.items():
            f.write(f'{k} = {v:#x};\n')
        f.write(f'SECTIONS {{\n  . = {CAVE:#x};\n'
                '  .text : { *play_as_pokemon.o(.text .text.*) }\n'
                f'  . = {CAVE2:#x};\n'
                '  .text2 : { KEEP(*(.text.tramp)) *(.text .text.* .text2.*) *(.rodata .rodata.*) }\n'   # .text2.*: mod code marked CAVE2_FN
                '  pap_data_load = ALIGN(16);\n'
                f'  .data {RAM:#x} : AT(pap_data_load) {{ pap_data_start = .; *(.data .data.*) . = ALIGN(16); pap_data_end = .; }}\n'
                '  .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) pap_bss_end = .; }\n'
                '  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.ARM.attributes) *(.llvm_addrsig) }\n}\n')
    elf = os.path.join(build, 'play_as_pokemon.elf')
    run([tool('ld.lld'), '-T', script, '-nostdlib', '--no-undefined', '--gc-sections', '-o', elf, *objs])
    heads = run([tool('llvm-objdump'), '-h', elf])
    for bad in ('.got', '.rela', '.dynamic'):
        assert bad not in heads, f'{bad} in the result: it must be position independent without a loader'
    table = {}
    for l in run([tool('llvm-objdump'), '-t', elf]).splitlines():
        p = l.split()
        if len(p) >= 2 and len(p[0]) == 16 and all(ch in '0123456789abcdef' for ch in p[0]):
            table[p[-1]] = int(p[0], 16)
    blobs = []
    for secs, at, end in ((('.text',), CAVE, CAVE_END), (('.text2', '.data'), CAVE2, CAVE2_END)):
        binf = os.path.join(build, f'cave_{at:x}.bin')
        run([tool('llvm-objcopy'), '-O', 'binary', *[x for sec in secs for x in ('-j', sec)], elf, binf])
        blob = open(binf, 'rb').read()
        assert at + len(blob) <= end, f'{len(blob)} bytes for main+{at:#x}, {end - at} fit'
        blobs.append((at, blob))
    data_size, bss_end = table['pap_data_end'] - table['pap_data_start'], table['pap_bss_end']
    assert CAVE2 + len(blobs[1][1]) == table['pap_data_load'] + data_size, 'the second part is not code + data image'
    assert bss_end <= RAM_END, f'the variables end at main+{bss_end:#x}, past main+{RAM_END:#x}'

    recs = blobs + [(off, struct.pack('<I', branch(off, table[f'tramp_{name}']))) for name, off, _, _ in rb.HOOKS]
    for off, data in recs:   # nothing else in the game is touched
        assert off in (CAVE, CAVE2) or len(data) == 4
    with open(os.path.join(FILES, IPS_NAME), 'wb') as f:
        f.write(write_ips32(recs))
    assert read_ips(open(os.path.join(FILES, IPS_NAME), 'rb').read())   # it reads back
    for file in CHEATS:
        with open(os.path.join(FILES, file), 'w', newline='') as f:
            f.write(cheat(file))
    print(f'mod {len(blobs[0][1])} of {CAVE_END - CAVE} bytes at main+{CAVE:#x}; trampolines, host, read-only data and data image '
          f'{len(blobs[1][1])} of {CAVE2_END - CAVE2} at main+{CAVE2:#x}; variables main+{RAM:#x}..main+{bss_end:#x} '
          f'({data_size} initialised); {len(rb.HOOKS)} hook points')
    for name, off, _, _ in rb.HOOKS:
        print(f'  main+{off:#x} {name} -> main+{table[f"tramp_{name}"]:#x}')


if __name__ == '__main__':
    main()
