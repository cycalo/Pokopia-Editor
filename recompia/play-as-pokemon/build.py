"""Build Play as Pokemon for Recompia (a Modtopia code mod) into dist/recompia_play_as_pokemon-<version>.pkmod.

Usage:  py recompia\\play-as-pokemon\\build.py [--zig PATH] [--clang PATH]

Steps: write src/forms.h and mod.toml from the emulator mod's Pokemon lists (mods/play-as-pokemon/pokemon.json and
experimental.json), compile src/play_as_pokemon.c for windows-x64 (mod.dll) and linux-x64 (mod.so) with zig, then pack
mod.toml + bin/ into the .pkmod (a zip) and print its sha256.

zig: --zig, else the ZIG environment variable, else `zig` on PATH. Recompia ships one in its install folder
(tools/build/zig/zig.exe), which is what this was built with. That zig has no Linux headers, so mod.so is then built with
clang + ld.lld: --clang, else the CLANG environment variable, else `clang` on PATH (llvm-mingw works).
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LISTS = os.path.join(REPO, 'mods', 'play-as-pokemon')
DIST = os.path.join(REPO, 'dist')

MOD_ID = 'play_as_pokemon'
VERSION = '1.7.0'
ABILITIES = ['Grow', 'Burn', 'Water', 'Generate']   # the order of AB_* in play_as_pokemon.c
ABILITY_AUTO = 'Auto (the Pokémon’s own)'
# Which Pokemon have each ability (the in-game specialty lists; the game's own table for it is not found yet). A Pokemon in none of
# the lists has no ability the mod can use.
ABILITY_POKEMON = {
    'Grow': 'Bellossom Bellsprout Bulbasaur Cacnea Cacturne Dartrix Decidueye Exeggcute Exeggutor Floragato Gloom Ivysaur Leafeon '
            'Meowscarada Oddish Rowlet Serperior Servine Snivy Sprigatito Tangela Tangrowth Venusaur Victreebel Vileplume Weepinbell',
    'Burn': 'Arcanine Armarouge Blaziken Carkol Ceruledge Chandelure Charcadet Charizard Charmander Charmeleon Cinderace Coalossal '
            'Combusken Cyndaquil Entei Flareon Growlithe Lampent Larvesta Litwick Magby Magmar Magmortar Ninetales Quilava Raboot '
            'Rolycoly Scorbunny Torchic Torkoal Typhlosion Volcanion Volcarona Vulpix',
    'Water': 'Azumarill Azurill Blastoise Cramorant Dragonair Dragonite Dratini Empoleon Froakie Frogadier Gastrodon Goodra Goomy '
             'Greninja Gyarados Lapras Lombre Lotad Ludicolo Marill Pelipper Piplup Politoed Poliwag Poliwhirl Poliwrath Prinplup '
             'Shellos Sliggoo Slowbro Slowking Slowpoke Squirtle Suicune Vaporeon Wartortle Wingull',
    'Generate': 'Ampharos Charjabug Electabuzz Electivire Electrode Elekid Flaaffy Jolteon Kilowattrel Magnemite Magneton Magnezone '
                'Mareep Minun Pawmi Pawmo Pawmot Pichu Pikachu Plusle Raichu Raikou Toxel Toxtricity Vikavolt Voltorb Wattrel',
}
DEFAULT_A_L, DEFAULT_M_Z, DEFAULT_EXPERIMENTAL = 'Ditto', 'Piplup', 'Ditto (Surf form)'
LIST_A_L, LIST_M_Z, LIST_EXPERIMENTAL = 'A to L', 'M to Z', 'Experimental forms'

# Every code patch of the emulator mod's IPS, as a take_over point: (name, main offset, the instruction there, what it is)
HOOKS = [
    ('form_get', 0x6671B0, 0x528B48C8, 'desired-form getter (entry): returns the form while transformed'),
    ('form_set', 0x6671BC, 0x528B48C8, 'desired-form setter (entry): stores the form while transformed'),
    ('request_state', 0x2F14E0, 0xD503237F, 'RequestState (entry): drops "back to human" while transformed'),
    ('probe', 0x6F2310, 0xD503237F, 'animation condition 0x56 (entry): no stand-up stretch for the player'),
    ('char_setup', 0x27CBD0, 0x791D2B28, 'strh w8, [x25, #0xe94]: the model setup, loads the form\'s animations'),
    ('player_tick', 0x2FACE0, 0xD63F0100, 'blr x8 in the player update: buttons, animations, flying'),
    ('to_human', 0x455580, 0xD503237F, 'turns the player human for an interaction (entry): noted, the player turns back after it (talking)'),
    ('motion_reset', 0x8D12C0, 0xD503237F, 'releases every motion set (entry), in the world reset (end of a Link Play session): the mod forgets what it loaded'),
    ('face', 0x2666C4, 0x2A1503E0, 'mov w0, w21 before setting a player character\'s face: no underwater face 22 for a Pokemon (blank eyes)'),
    ('chair_use', 0x7C1838, 0xD503237F, 'a player sits on a chair (entry): not while transformed (a Pokemon gets stuck there)'),
    ('attach', 0x2A5D5C, 0xD503237F, 'puts a model on the player hand (entry): nothing for a transformed player (a picked-up item stuck at the feet)'),
    ('bed_use', 0x79D948, 0xD503237F, 'a player lies down on a bed (entry): not while transformed (a Pokemon gets stuck there)'),
]

DESCRIPTION = (
    "Play as any Pokémon: ZL + L3 transforms you and back, ZL + R3 (or F3) lists them all. "
    "Camera judders while flying? Turn off Running jump keeps speed in Recompia's settings.")


def ascii_name(n):
    return n.replace('’', "'")


def toml_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def toml_list(items):
    return '[' + ', '.join(toml_str(i) for i in items) + ']'


def load_lists():
    with open(os.path.join(LISTS, 'pokemon.json'), encoding='utf-8') as f:
        pokemon = {ascii_name(k): v for k, v in json.load(f).items()}
    with open(os.path.join(LISTS, 'experimental.json'), encoding='utf-8') as f:
        experimental = {ascii_name(k): v for k, v in json.load(f).items()}
    names = sorted(pokemon, key=str.lower)
    a_l = [n for n in names if n[0].upper() <= 'L']
    m_z = [n for n in names if n[0].upper() > 'L']
    exp = sorted(experimental, key=str.lower)
    assert not set(exp) & set(pokemon), 'a name in both lists'
    for lst in (a_l, m_z, exp):
        assert len(lst) <= 255, 'the in-game menu shows at most 256 choices'
    assert DEFAULT_A_L in a_l and DEFAULT_M_Z in m_z and DEFAULT_EXPERIMENTAL in exp
    return pokemon, experimental, names, a_l, m_z, exp


def write_forms_h(pokemon, experimental, names, exp):
    rows = [f'    {{{pokemon[n]} PAP_NAME({json.dumps(n)})}},' for n in names] +            [f'    {{{experimental[n]} PAP_NAME({json.dumps(n)})}},' for n in exp]
    ab_rows, seen = [], {}
    for kind, (ab, members) in enumerate((a, ABILITY_POKEMON[a].split()) for a in ABILITIES):
        for n in members:
            assert n in pokemon, f'{n} ({ab}) is not in pokemon.json'
            assert n not in seen, f'{n} has two abilities'
            seen[n] = ab
            ab_rows.append(f'    {{{pokemon[n]}, {kind}}},  /* {n}: {ab} */')
    text = '\n'.join([
        '/* Generated by build.py from mods/play-as-pokemon/pokemon.json and experimental.json: do not edit. */',
        '#pragma once',
        '#ifdef PAP_SWITCH   /* the Switch build has no log or message box, and its code may hold no addresses: ids only */',
        '#define PAP_NAME(s)',
        '#define PAP_NAME_FIELD',
        '#else',
        '#define PAP_NAME(s) , s',
        '#define PAP_NAME_FIELD const char *name;',
        '#endif',
        f'#define DEFAULT_FORM {pokemon[DEFAULT_A_L]}  /* {DEFAULT_A_L} */',
        f'#define LIST_A_L {json.dumps(LIST_A_L)}',
        f'#define LIST_M_Z {json.dumps(LIST_M_Z)}',
        f'#define LIST_EXPERIMENTAL {json.dumps(LIST_EXPERIMENTAL)}',
        f'#define POKEMON_COUNT {len(names)}  /* FORMS[0 .. POKEMON_COUNT-1]: the Pokemon, A to Z; then the experimental forms */',
        f'#define FORM_COUNT {len(names) + len(exp)}',
        'static const struct { unsigned short id; PAP_NAME_FIELD } FORMS[] = {',
        *rows,
        '};',
        f'#define ABILITY_COUNT {len(ab_rows)}',
        'static const struct { unsigned short id; unsigned char ability; } ABILITY_OF[] = {   /* ability: AB_GROW, AB_BURN, AB_WATER */',
        *ab_rows,
        '};',
        '',
    ])
    with open(os.path.join(HERE, 'src', 'forms.h'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def write_mod_toml(a_l, m_z, exp):
    L = [
        '# Generated by build.py: edit it there.',
        f'id = "{MOD_ID}"',
        'name = "Play as Pokemon"',
        f'version = "{VERSION}"',
        'authors = ["cycalo"]',
        f'description = {toml_str(DESCRIPTION)}',
        'license = "GPL-3.0-or-later"',
        'homepage = "https://github.com/cycalo/Pokopia-Editor"',
        'loader = ">=0.6.0 <1.0.0"',
        'game = ["2.0.1"]',
        'affects = "gameplay"',
        '',
        '[[settings]]',
        'key = "list"',
        'type = "choice"',
        f'choices = {toml_list([LIST_A_L, LIST_M_Z, LIST_EXPERIMENTAL])}',
        f'default = "{LIST_A_L}"',
        'label = "Which list below picks the Pokémon"',
        'description = "The game\'s menu shows at most 256 names in one list, so the Pokémon are split in two. Experimental forms are not Pokémon: story objects and the shapes Ditto takes for its moves (the towers are huge)."',
        '',
        '[[settings]]',
        'key = "pokemon_a_l"',
        'type = "choice"',
        f'choices = {toml_list(a_l)}',
        f'default = {toml_str(DEFAULT_A_L)}',
        'label = "Pokémon, A to L"',
        '',
        '[[settings]]',
        'key = "pokemon_m_z"',
        'type = "choice"',
        f'choices = {toml_list(m_z)}',
        f'default = {toml_str(DEFAULT_M_Z)}',
        'label = "Pokémon, M to Z"',
        '',
        '[[settings]]',
        'key = "experimental"',
        'type = "choice"',
        f'choices = {toml_list(exp)}',
        f'default = {toml_str(DEFAULT_EXPERIMENTAL)}',
        'label = "Experimental form"',
        '',
        '[[settings]]',
        'key = "fly"',
        'type = "bool"',
        'default = true',
        'label = "Flying Pokémon can fly (ZR up, ZL down, ZL + ZR drop)"',
        'description = "If the camera judders while flying, turn off Running jump keeps speed in Recompia (Settings > Game > Gameplay)."',
        '',
        '[[settings]]',
        'key = "fly_speed"',
        'type = "choice"',
        'choices = ["Slow", "Normal", "Fast"]',
        'default = "Normal"',
        'label = "Flying: top speed up and down"',
        'description = "A tap of ZR or ZL moves you a little; holding it speeds up to this, and letting go slows you to a hover. Slow: 2.5 blocks a second, Normal: 4, Fast: 6."',
        '',
        '[[settings]]',
        'key = "abilities"',
        'type = "bool"',
        'default = true',
        'label = "Abilities: ZR, or ZL + D-pad Down, uses the ability below"',
        'description = "Flying Pokémon keep ZR for flying and use ZL + D-pad Down. Stand facing the plants, the campfire or the soil."',
        '',
        '[[settings]]',
        'key = "ability"',
        'type = "choice"',
        f'choices = {toml_list([ABILITY_AUTO] + ABILITIES)}',
        f'default = {toml_str(ABILITY_AUTO)}',
        'label = "Ability"',
        'description = "Grow: the crops and plants in front of you grow a stage, each once, as with a resident\'s Grow. Burn: the object in front of you is burnt (a campfire, Squish Clay). Water: Bubble on sludge that is not bubbled yet, otherwise the Water Gun on what is in front of you (soil, plants, bubbled sludge). Generate: the light or machine in front of you is powered. Auto: the Pokémon’s own specialty, if it is one of these."',
        '',
        '[[settings]]',
        'key = "interact"',
        'type = "bool"',
        'default = true',
        'label = "Use doors, the crafting bench, the bag and building while transformed"',
        'description = "The game otherwise treats a transformed player like its Ditto blob and keeps these to the human. Chairs and beds stay for the human: a Pokémon has no sitting or lying-down animation."',
        '',
        '[[settings]]',
        'key = "cycle"',
        'type = "bool"',
        'default = true',
        'label = "ZL + D-pad Left / Right picks the previous / next Pokémon while playing"',
        'description = "Until the next start or the next change here: the lists above stay as they are."',
        '',
        '[[settings]]',
        'key = "messages"',
        'type = "bool"',
        'default = true',
        'label = "Show the Pokémon\'s name when transforming"',
        '',
        '[[settings]]',
        'key = "key_transform"',
        'type = "key"',
        'default = ""',
        'label = "Keyboard key: turn into the Pokémon (ZL + L3 does both)"',
        '',
        '[[settings]]',
        'key = "key_turn_back"',
        'type = "key"',
        'default = ""',
        'label = "Keyboard key: turn back"',
        '',
        '[[settings]]',
        'key = "key_ability"',
        'type = "key"',
        'default = ""',
        'label = "Keyboard key: use the ability (as ZR)"',
        '',
        '[[settings]]',
        'key = "key_menu"',
        'type = "key"',
        'default = "F3"',
        'label = "Keyboard key: open the list of Pokémon (as ZL + R3)"',
        'description = "In the list: Up / Down move, Left / Right move by 10, L / R jump to the next letter, A or Enter chooses, B or Esc closes. The choice lasts until the next start."',
        '',
        '# The code patches of the emulator version (an IPS for main build 76a489f3bd3642fa) but the two small-space ground writers, as a take_over point.',
    ]
    for name, off, word, what in HOOKS:
        L += ['', '[[hooks."2.0.1"]]', f'name = "{name}"   # {what}', f'target = "main+{off:#x}"', f'word = {word:#010x}',
              'kind = "take_over"']
    with open(os.path.join(HERE, 'mod.toml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L) + '\n')


def find_zig(arg):
    for z in (arg, os.environ.get('ZIG'), shutil.which('zig')):
        if z and os.path.isfile(z):
            return z
    sys.exit('zig not found: pass --zig PATH (Recompia has one at <install>/tools/build/zig/zig.exe)')


# The Linux library without Linux headers: Recompia's zig has Windows headers only, so when it cannot build mod.so, clang and
# lld (any LLVM, e.g. llvm-mingw) build it with declarations of the few libc functions the mod calls and a stub libc.so.6 to
# link against. The result needs glibc 2.17 or newer. A new libc call fails this build (-Werror): declare it here.
LINUX_SHIM = {
    'stdio.h': '#pragma once\n#include <stdarg.h>\n#include <stddef.h>\n'
               'int snprintf(char *restrict s, size_t n, const char *restrict fmt, ...);\n'
               'int vsnprintf(char *restrict s, size_t n, const char *restrict fmt, va_list ap);\n',
    'string.h': '#pragma once\n#include <stddef.h>\n'
                'void *memset(void *s, int c, size_t n);\nint strcmp(const char *a, const char *b);\n',
    'time.h': '#pragma once\ntypedef long time_t;\ntypedef int clockid_t;\n'
              'struct timespec { time_t tv_sec; long tv_nsec; };\n#define CLOCK_MONOTONIC 1\n'
              'int clock_gettime(clockid_t clk, struct timespec *tp);\n',
}
LIBC_STUB = ('#include <stdarg.h>\n#include <stddef.h>\n'
             'int snprintf(char *s, size_t n, const char *f, ...) { return 0; }\n'
             'int vsnprintf(char *s, size_t n, const char *f, va_list ap) { return 0; }\n'
             'void *memset(void *s, int c, size_t n) { return s; }\n'
             'int strcmp(const char *a, const char *b) { return 0; }\n'
             'int clock_gettime(int c, void *t) { return 0; }\n')
LIBC_VERSIONS = ('GLIBC_2.2.5 { global: snprintf; vsnprintf; memset; strcmp; local: *; };\n'
                 'GLIBC_2.17 { global: clock_gettime; } GLIBC_2.2.5;\n')


def find_clang(arg):
    for c in (arg, os.environ.get('CLANG'), shutil.which('clang')):
        if c and os.path.isfile(c) and (shutil.which('ld.lld') or os.path.isfile(os.path.join(os.path.dirname(c), 'ld.lld.exe'))
                                        or os.path.isfile(os.path.join(os.path.dirname(c), 'ld.lld'))):
            return c
    return None


def build_linux_with_clang(clang, flags, src, dst):
    work = os.path.join(HERE, 'build', 'linux-sdk')
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, 'include'))
    for name, text in LINUX_SHIM.items():
        with open(os.path.join(work, 'include', name), 'w', encoding='ascii', newline='\n') as f:
            f.write(text)
    for name, text in (('libc_stub.c', LIBC_STUB), ('libc.map', LIBC_VERSIONS)):
        with open(os.path.join(work, name), 'w', encoding='ascii', newline='\n') as f:
            f.write(text)
    libc = os.path.join(work, 'libc.so.6')
    base = [clang, '-target', 'x86_64-linux-gnu', '-ffreestanding', '-nostdlib', '-shared', '-fPIC', '-fuse-ld=lld']
    cmds = [base + ['-Wl,-soname,libc.so.6', '-Wl,--version-script,' + os.path.join(work, 'libc.map'), '-o', libc,
                    os.path.join(work, 'libc_stub.c')],
            base + [*flags, '-nostdlibinc', '-isystem', os.path.join(work, 'include'), '-fvisibility=hidden',
                    '-Wl,--no-undefined', '-Wl,-z,now', '-Wl,-z,relro', '-o', dst, src, libc]]
    for cmd in cmds:
        print(' '.join(cmd))
        if subprocess.run(cmd).returncode:
            return False
    return True


def compile_all(zig, clang, out):
    src, inc = os.path.join(HERE, 'src', 'play_as_pokemon.c'), os.path.join(HERE, 'include')
    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Wno-unused-parameter', '-Werror', '-I', inc, '-I', os.path.join(HERE, 'src')]
    # (platform, zig target, library, extra flags). Both are required: Recompia on Linux lists a mod without mod.so as
    # having no code for linux-x64 and shows it as "Not loaded".
    targets = [('windows-x64', 'x86_64-windows-gnu', 'mod.dll', []),
               ('linux-x64', 'x86_64-linux-gnu', 'mod.so', ['-fPIC', '-fvisibility=hidden'])]
    built = []
    for plat, triple, lib, extra in targets:
        d = os.path.join(out, 'bin', plat)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, lib)
        cmd = [zig, 'cc', '-target', triple, '-shared', *flags, *extra, '-o', dst, src]
        print(' '.join(cmd))
        if subprocess.run(cmd).returncode:
            if plat != 'linux-x64':
                sys.exit(f'the {plat} build failed')
            print('note: this zig cannot build the Linux library (no Linux headers); trying clang + lld')
            if not clang:
                sys.exit('no clang with ld.lld for the Linux library: pass --clang PATH (any LLVM, e.g. llvm-mingw)')
            if not build_linux_with_clang(clang, flags, src, dst):
                sys.exit('the linux-x64 build failed')
        for junk in ('mod.lib', 'mod.pdb'):   # import library / symbols zig leaves beside the dll
            p = os.path.join(d, junk)
            if os.path.exists(p):
                os.remove(p)
        built.append(f'bin/{plat}/{lib}')
    return built


def pack(stage, files, out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(stage, rel), 'rb') as f:
                z.writestr(info, f.read())
    with open(out, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zig')
    ap.add_argument('--clang', help='clang with ld.lld beside it, for the Linux library when zig has no Linux headers')
    a = ap.parse_args()
    pokemon, experimental, names, a_l, m_z, exp = load_lists()
    write_forms_h(pokemon, experimental, names, exp)
    write_mod_toml(a_l, m_z, exp)
    stage = os.path.join(HERE, 'build', 'stage')
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    shutil.copy(os.path.join(HERE, 'mod.toml'), stage)
    files = ['mod.toml'] + compile_all(find_zig(a.zig), find_clang(a.clang), stage)
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f'recompia_{MOD_ID}-{VERSION}.pkmod')
    sha = pack(stage, files, out)
    with open(out + '.sha256', 'w', encoding='ascii', newline='\n') as f:
        f.write(f'{sha}  {os.path.basename(out)}\n')
    print(out)
    print('sha256', sha)


if __name__ == '__main__':
    main()
