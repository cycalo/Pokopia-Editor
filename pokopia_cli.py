"""Command line Pokopia save editor.

SAVE is a save folder (the one containing G00), or "auto" for the newest save found automatically.

Examples:
  py pokopia_cli.py find-saves                (Pokopia saves in Eden/Yuzu/Suyu/Sudachi/Citron/Torzu/Ryujinx folders)
  py pokopia_cli.py info auto
  py pokopia_cli.py info SAVE
  py pokopia_cli.py inventory SAVE
  py pokopia_cli.py villagers SAVE
  py pokopia_cli.py emotes SAVE
  py pokopia_cli.py flags SAVE
  py pokopia_cli.py find-item honey
  py pokopia_cli.py diff SAVE_A SAVE_B        (what changed from A to B; use SAVE\\B00 style folders too)
  py pokopia_cli.py diff SAVE --game-backup   (the game's own B00 slot -> current G00)
  py pokopia_cli.py photos SAVE --export DIR
  py pokopia_cli.py map SAVE --export DIR
  py pokopia_cli.py backups
  py pokopia_cli.py edit SAVE --out OUTDIR --set-item 0 3994 99 --friendship 17 170 --name Mike --learn 6
  py pokopia_cli.py edit SAVE --out OUTDIR --add-item 3994 50 --learn-emote all --unlock dive --unlock boost4
  py pokopia_cli.py wardrobe SAVE                             (outfits and hairstyles with their IDs)
  py pokopia_cli.py edit SAVE --out OUTDIR --unlock-outfits   (all outfits and hairstyles)
  py pokopia_cli.py edit SAVE --out OUTDIR --unlock-wardrobe Ranger --unlock-wardrobe "hair:Side tails"
  py pokopia_cli.py edit SAVE --in-place --set-item 0 3994 99   (auto backup first)
  py pokopia_cli.py selftest SAVE
"""
import argparse, os, sys, tempfile, shutil
import pokopia_save as ps
import pokopia_extras as px


def cmd_info(a):
    s = ps.SaveFolder(a.save); c = s.common
    print('Folder :', s.folder)
    print('Player :', c.player_name)
    if c.play_seconds is not None:
        print('Played :', ps.fmt_playtime(c.play_seconds))
    print('Items  :', len(c.filled_slots()), 'filled slots of', ps.INV_COUNT)
    print('Residents:', len(c.villagers()))
    print('Moves  :', ', '.join(ps.name_of(ps.SKILL_NAMES, i, 'Move') for i in ps.PUBLIC_SKILLS if c.skill(i)[1]))
    print('Extras :', ', '.join(v[0] for k, v in ps.EXTRAS.items() if c.extra(k)) or '-')
    print('Emotes :', len([i for i in c.reactions_learned() if i in ps.PUBLIC_REACTIONS]), 'of', len(ps.PUBLIC_REACTIONS))
    print('Wardrobe:', len(c.wardrobe_unlocked()), 'of', len(ps.WARDROBE_IDS), 'outfit/hairstyle entries')
    print('Islands:', ', '.join(f'{n:02} {ps.name_of(ps.AREA_NAMES, n, "Area")}' for n in s.stage_files()))


def cmd_inventory(a):
    c = ps.SaveFolder(a.save).common
    for i in range(ps.INV_COUNT):
        iid, cnt, _ = c.get_slot(i)
        if iid or a.all:
            bar = 'main' if i < ps.INV_MAIN else 'bar2'
            print(f'{i:3} {bar} {iid:5} x{cnt:<3} {ps.item_name(iid)}')


def cmd_villagers(a):
    c = ps.SaveFolder(a.save).common
    for i in c.villagers():
        v = c.get_villager(i)
        met = v['met'].strftime('%Y-%m-%d %H:%M') if v['met'] else 'starter'
        home = '{} ({}, {}, {})'.format(v['home_area_name'], *v['home_xyz']) if v['home_xyz'] else 'no home'
        print(f"{i:4} {v['name']:<14} friendship {v['friendship']:<4} thank {v['thank_points']:<4} met {met:<16} {home}")


def cmd_emotes(a):
    c = ps.SaveFolder(a.save).common
    wheel = c.reaction_wheel()
    for i in ps.PUBLIC_REACTIONS:
        on = 'learned' if c.reaction_learned(i) else '-'
        slot = f'wheel slot {wheel.index(i) + 1}' if i in wheel else ''
        print(f'{i:3} {ps.REACTION_NAMES[i]:<20} {on:<8} {slot}')


def cmd_wardrobe(a):
    c = ps.SaveFolder(a.save).common
    for title, entries in (('Outfits', ps.OUTFITS), ('Hairstyles', ps.HAIRSTYLES)):
        print(title)
        for i, name in entries:
            state = 'default' if i in ps.WARDROBE_DEFAULTS and not (i and c.wardrobe_owned(i)) else \
                'unlocked' if c.wardrobe_owned(i) else '-'
            note = '' if i is None or i in ps.WARDROBE_CONFIRMED or i in ps.WARDROBE_DEFAULTS else '(id from mirror order)'
            print(f'  {i or "":>4} {name:<18} {state:<9} {note}')
    print('Entries set in the save:', len(c.wardrobe_unlocked()), 'of', len(ps.WARDROBE_IDS))


def cmd_flags(a):
    c = ps.SaveFolder(a.save).common
    for i in range(1, ps.FLAG_COUNT):
        if c.get_flag(i) or i in ps.KNOWN_FLAGS:
            print(f'{i:3} {"on " if c.get_flag(i) else "off"} {ps.KNOWN_FLAGS.get(i, "")}')


def cmd_find(a):
    q = a.text.lower()
    for i, n in enumerate(ps.ITEM_NAMES):
        if n and q in n.lower():
            print(i, n)


def cmd_diff(a):
    if a.game_backup:
        s = ps.SaveFolder(a.a)
        old, new = s.game_backup(), s.common
        if old is None:
            sys.exit('That save has no readable B00 slot.')
    else:
        if not a.b:
            sys.exit('Give two saves, or one save with --game-backup')
        old, new = _common(a.a), _common(a.b)
    lines = ps.describe_changes(old, new)
    print('\n'.join(lines) if lines else 'No differences in the fields this editor understands.')


def _common(path):
    """Accepts a save folder, a G00/B00 folder, or a CMNDAT.BIN file."""
    if os.path.isfile(path):
        return ps.CommonSave(path)
    direct = os.path.join(path, 'CMNDAT.BIN')
    if os.path.isfile(direct):
        return ps.CommonSave(direct)
    return ps.SaveFolder(path).common


def cmd_photos(a):
    p = ps.SaveFolder(a.save).photo_file()
    if not p:
        sys.exit('No SCSHDAT.BIN in that save.')
    album = px.PhotoAlbum(p)
    print(len(album), 'photos')
    if a.export:
        for f in album.export(a.export):
            print('  ', f)


def cmd_map(a):
    s = ps.SaveFolder(a.save)
    for area, path in s.stage_files().items():
        m = px.StageMap(path, area)
        homes = px.homes_on(s.common, area)
        print(f'{area:02} {m.name}: {m.chunks} chunks, {m.parts} placed objects, {len(homes)} resident homes')
        if a.export:
            os.makedirs(a.export, exist_ok=True)
            f = os.path.join(a.export, f'island_{area:02}.png')
            m.render().save(f)
            print('  ', f)


def cmd_find_saves(a):
    rows = px.find_saves(a.search or [])
    if not rows:
        print('No Pokopia save found in the usual emulator folders. Give the folder yourself, or --search DIR.')
    for e in rows:
        state = 'supported' if e['supported'] else 'other game version'
        print(f"{e['saved']:%Y-%m-%d %H:%M}  {e['emulator']:<8} {state:<19} {e['folder']}")


def cmd_backups(a):
    rows = px.list_backups(a.root)
    if not rows:
        print('No backups in', a.root or ps.default_backup_root())
    for e in rows:
        pt = ps.fmt_playtime(e['playtime']) if e['playtime'] is not None else '-'
        print(f"{e['when']:%Y-%m-%d %H:%M}  {e['name']:<30} {e['player']:<12} {e['residents']:3} residents {e['items']:3} items  played {pt}  {e['error']}")


def apply_edits(c, a):
    if a.name:
        c.player_name = a.name
    for slot, iid, cnt in a.set_item or []:
        c.set_slot(int(slot), int(iid), int(cnt))
    for iid, cnt in a.add_item or []:
        c.add_item(int(iid), int(cnt))
    for idx, val in a.friendship or []:
        c.set_friendship(int(idx), int(val))
    for m in a.learn or []:
        c.learn_skill(int(m))
    for e in a.learn_emote or []:
        for i in (ps.PUBLIC_REACTIONS if e == 'all' else [int(e)]):
            c.learn_reaction(i)
    for key in a.unlock or []:
        c.set_extra(key.replace(':', ''), True)
    if a.unlock_outfits:
        c.unlock_wardrobe()
    if a.unlock_wardrobe:
        c.unlock_wardrobe([ps.wardrobe_lookup(t) for t in a.unlock_wardrobe])
    if a.remove_wardrobe:
        c.lock_wardrobe([ps.wardrobe_lookup(t) for t in a.remove_wardrobe])
    for m in a.unlearn or []:
        c.forget_skill(int(m))
    for e in a.unlearn_emote or []:
        c.forget_reaction(int(e))


def cmd_edit(a):
    s = ps.SaveFolder(a.save)
    before = ps.CommonSave(s.common.path)
    apply_edits(s.common, a)
    if not s.common.edited:
        print('No changes.'); return
    if not a.in_place and not a.out:
        sys.exit('Give --out NEWFOLDER or --in-place')
    if a.in_place:
        emus = px.running_emulators()
        if emus and not a.force:
            sys.exit(f'Emulator is running ({", ".join(emus)}). Close it first, or add --force.')
    for line in ps.describe_changes(before, s.common):
        print('  ', line)
    target, backup = s.write(out_folder=a.out, in_place=a.in_place)
    if backup:
        print('Backup:', backup)
    print('Written and verified:', target)


def cmd_selftest(a):
    s = ps.SaveFolder(a.save)
    tmp = tempfile.mkdtemp(prefix='pokopia_test_')
    results = []

    def check(name, ok, note=''):
        results.append(ok)
        print(f'{"PASS" if ok else "FAIL"}  {name}{"  (" + note + ")" if note else ""}')

    try:
        out1 = os.path.join(tmp, 'noedit')
        s.write(out_folder=out1)
        same = all(ps.sha256(os.path.join(dp, f)) == ps.sha256(os.path.join(out1, os.path.relpath(dp, s.folder), f))
                   for dp, _, fs in os.walk(s.folder) for f in fs)
        check('Round trip without edits is byte-identical', same)

        s2 = ps.SaveFolder(a.save); c = s2.common
        orig = bytes(c.data)
        empty = c.first_empty()
        vil = c.villagers()[0]
        emote = next(i for i in ps.PUBLIC_REACTIONS if not c.reaction_learned(i))
        flag = next(i for i in range(200, ps.FLAG_COUNT) if not c.get_flag(i))
        had = sum(e['id'] == 3994 for e in c.export_bag())
        steps = [
            ('set slot', lambda: c.set_slot(empty, 3994, 77)),
            ('add item', lambda: c.add_item(3994, 5)),
            ('swap slots', lambda: c.swap_slots(0, empty)),
            ('sort bag', lambda: c.sort_main()),
            ('friendship', lambda: c.set_friendship(vil, 99)),
            ('name', lambda: setattr(c, 'player_name', 'TestName')),
            ('learn Surf', lambda: c.learn_skill(10)),
            ('unlock Dive', lambda: c.set_extra('dive')),
            ('Surf food boost', lambda: c.set_extra('boost10')),
            ('Rock Smash food boost', lambda: c.set_extra('boost4')),
            ('learn emote', lambda: c.learn_reaction(emote)),
            ('emote wheel', lambda: c.set_reaction_slot(0, emote)),
            ('move wheel', lambda: c.set_skill_slot(7, c.wheel()[0])),
            ('raw flag', lambda: c.set_flag(flag, True)),
        ]
        if len(c.wardrobe_unlocked()) < len(ps.WARDROBE_IDS):
            steps.append(('unlock outfits', lambda: c.unlock_wardrobe()))
        steps.append(('remove one outfit', lambda: c.lock_wardrobe([ps.wardrobe_lookup('Rascal')])))
        old_emote = next(i for i in ps.PUBLIC_REACTIONS if c.reaction_learned(i))
        steps.append(('unlearn emote', lambda: c.forget_reaction(old_emote)))
        old_move = next((m for m in (5, 4, 2, 1) if c.skill(m)[1]), None)
        if old_move:
            steps.append(('unlearn move', lambda: c.forget_skill(old_move)))
        for label, fn in steps:
            fn()
            if not c.commit(label):
                check(f'{label} changed the data', False)
        expect = dict(name=c.player_name, fr=c.get_villager(vil)['friendship'], bag=c.export_bag(), wheel=c.wheel(),
                      rwheel=c.reaction_wheel(), emote=c.reaction_learned(emote), flag=c.get_flag(flag),
                      extras={k: c.extra(k) for k in ps.EXTRAS}, surf=c.skill(10)[1], wardrobe=c.wardrobe_unlocked())
        check('Edits applied', expect['name'] == 'TestName' and expect['fr'] == 99 and expect['emote'] and expect['flag']
              and expect['wardrobe'] == [i for i in ps.WARDROBE_IDS if i != 2414]
              and not c.reaction_learned(old_emote) and old_emote not in c.reaction_wheel()
              and (old_move is None or (not c.skill(old_move)[1] and old_move not in c.wheel()
                                        and not any(c.extra(k) for k, v in ps.EXTRAS.items() if v[2] == old_move)))
              and expect['extras']['dive'] and expect['extras']['boost10'] and expect['extras']['boost4'] and expect['surf']
              and expect['rwheel'][0] == emote and expect['wheel'][7] != 0
              and sum(e['id'] == 3994 for e in expect['bag']) == had + 2)
        try:
            c.set_extra('boost1') if not c.skill(1)[1] else c.set_skill_slot(0, 10)
            check('Prerequisites are enforced', False)
        except ValueError:
            c.rollback()
            check('Prerequisites are enforced', True)

        out2 = os.path.join(tmp, 'edit')
        s2.write(out_folder=out2)
        r = ps.SaveFolder(out2).common
        got = dict(name=r.player_name, fr=r.get_villager(vil)['friendship'], bag=r.export_bag(), wheel=r.wheel(),
                   rwheel=r.reaction_wheel(), emote=r.reaction_learned(emote), flag=r.get_flag(flag),
                   extras={k: r.extra(k) for k in ps.EXTRAS}, surf=r.skill(10)[1], wardrobe=r.wardrobe_unlocked())
        diff = sum(1 for x, y in zip(r.data, orig) if x != y)
        check('Edited save parses back identically after writing', got == expect, f'{diff} bytes differ from the original')
        other = [f for dp, _, fs in os.walk(s.folder) for f in fs
                 if os.path.join(dp, f) != s.common.path
                 and ps.sha256(os.path.join(dp, f)) != ps.sha256(os.path.join(out2, os.path.relpath(dp, s.folder), f))]
        check('No other file in the save was touched', not other, ', '.join(other))

        n = 0
        while c.undo():
            n += 1
        check('Undo of every step restores the original bytes', bytes(c.data) == orig and n == len(steps), f'{n} steps')
        while c.redo():
            pass
        check('Redo reapplies every step', {k: c.extra(k) for k in ps.EXTRAS} == expect['extras'] and c.export_bag() == expect['bag'])

        gb = s.game_backup()
        if gb is not None:
            check('G00 vs B00 comparison runs', isinstance(ps.describe_changes(gb, s.common), list))
        pf = s.photo_file()
        if pf and px.Image is not None:
            album = px.PhotoAlbum(pf)
            files = album.export(os.path.join(tmp, 'photos'))
            check('Photos decode', all(album.image(i).size[0] > 0 for i in range(len(album))), f'{len(files)} photos')
        for area, path in s.stage_files().items():
            m = px.StageMap(path, area)
            check(f'Island {area:02} decodes', m.chunks > 0 and m.width > 0, f'{m.name}, {m.chunks} chunks')
        check('Source save unchanged by the test', ps.sha256(s.common.path) == ps.sha256(os.path.join(out1, ps.SaveFolder.REL)))
        sys.exit(0 if all(results) else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description='Pokopia save editor (CMNDAT 2.0.x)', epilog=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    for n, f in [('info', cmd_info), ('inventory', cmd_inventory), ('villagers', cmd_villagers), ('emotes', cmd_emotes),
                 ('flags', cmd_flags), ('wardrobe', cmd_wardrobe), ('selftest', cmd_selftest), ('photos', cmd_photos), ('map', cmd_map)]:
        q = sp.add_parser(n); q.add_argument('save'); q.set_defaults(f=f)
        if n == 'inventory': q.add_argument('--all', action='store_true')
        if n in ('photos', 'map'): q.add_argument('--export', metavar='DIR')
    q = sp.add_parser('find-item'); q.add_argument('text'); q.set_defaults(f=cmd_find)
    q = sp.add_parser('diff'); q.add_argument('a'); q.add_argument('b', nargs='?'); q.set_defaults(f=cmd_diff)
    q.add_argument('--game-backup', action='store_true', help="compare the save's B00 slot with its G00 slot")
    q = sp.add_parser('backups'); q.add_argument('--root'); q.set_defaults(f=cmd_backups)
    q = sp.add_parser('find-saves'); q.set_defaults(f=cmd_find_saves)
    q.add_argument('--search', action='append', metavar='DIR', help='also look inside this folder (e.g. a portable emulator)')
    q = sp.add_parser('edit'); q.add_argument('save'); q.set_defaults(f=cmd_edit)
    q.add_argument('--out'); q.add_argument('--in-place', action='store_true')
    q.add_argument('--force', action='store_true', help='write in place even if an emulator is running')
    q.add_argument('--name')
    q.add_argument('--set-item', nargs=3, action='append', metavar=('SLOT', 'ITEMID', 'COUNT'))
    q.add_argument('--add-item', nargs=2, action='append', metavar=('ITEMID', 'COUNT'))
    q.add_argument('--friendship', nargs=2, action='append', metavar=('RESIDENT', 'VALUE'))
    q.add_argument('--learn', action='append', metavar='MOVE')
    q.add_argument('--learn-emote', action='append', metavar='EMOTE|all')
    q.add_argument('--unlock', action='append', metavar='|'.join(ps.EXTRAS))
    q.add_argument('--unlock-outfits', action='store_true', help='unlock every outfit and hairstyle')
    q.add_argument('--unlock-wardrobe', action='append', metavar='NAME|ID',
                   help='unlock one outfit or hairstyle, e.g. Ranger, "outfit:Mermaid", "hair:Side tails", 2403')
    q.add_argument('--remove-wardrobe', action='append', metavar='NAME|ID', help='take an outfit or hairstyle away again')
    q.add_argument('--unlearn-emote', action='append', metavar='EMOTE')
    q.add_argument('--unlearn', action='append', metavar='MOVE', help='unlearn a move and switch off its extras')
    a = p.parse_args()
    for attr in ('save', 'a'):
        if getattr(a, attr, None) == 'auto':
            found = px.default_save()
            if not found:
                sys.exit('No Pokopia save found automatically. Run "find-saves", or give the folder.')
            print('Using', found)
            setattr(a, attr, found)
    try:
        a.f(a)
    except (ps.FormatError, ValueError) as e:
        sys.exit(f'Error: {e}')


if __name__ == '__main__':
    main()
