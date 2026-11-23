# Play as Pokemon for Recompia

The [Play as Pokemon](../../mods/play-as-pokemon/README.md) mod for [Recompia](https://github.com/Dittobyte/Recompia), the PC port of Pokopia. Turn into any Pokémon in Pokopia. Use their abilities: flying Pokémon can fly, and Grow, Burn, Water and Generate Pokémon can use their ability. Works in co-op / Link Play: every player needs the mod installed.

**Game version 2.0.1 only** (the version Recompia needs). Windows and Linux (x86-64; the Linux library needs glibc 2.17 or newer). The Linux build is untested in game so far.

## Controls

| Press | Does |
|---|---|
| **ZL + L3** (left stick click) | Turn into the chosen Pokémon; press again to turn back |
| **F3** or **ZL + R3** | Open the list of all Pokémon and forms: Up / Down move, Left / Right move by 10, L / R jump to the next letter, A or Enter chooses, B or Esc closes |
| **ZL + D-pad Left / Right** | Pick the previous / next Pokémon (A to Z). While transformed you change as soon as you stop flicking through |
| **ZR** as a flying Pokémon | Take off; tap to rise a little, hold to keep rising faster |
| **ZL** while flying | Descend the same way; keep holding it on the ground to land |
| **ZL + ZR** held while flying | Drop out of the air (press ZR again to take off) |
| **ZR** (Pokémon that can't fly) or **ZL + D-pad Down** (any) | Use the Pokémon's ability on what is in front of you. Not ZL + D-pad Down while you hold a block or other item: the game raises and lowers it with ZL + D-pad Up / Down (1.7.1) |
| **A** | Open doors, use the crafting bench and boxes, pick things up, as the human does (1.7.0) |
| **The bag** | Opens while flying too (1.7.1) |

Keyboard players can also set a key for "turn into", "turn back" and the ability, and change the F3 key, in the mod's settings.

## Install

1. Copy `recompia_play_as_pokemon-1.7.1.pkmod` into Recompia's `mods` folder (on Windows, next to `pkp.exe`), and remove an older version of it.
2. Open `PokopiaLauncher.exe`, go to **Mods**, and allow the new mod's code when it asks.
3. The first time these hook points are installed, the launcher rebuilds the game once before the next start (a few minutes). Updating from a version older than 1.5.0 rebuilds once more (1.5.0 added the hook point `motion_reset`); 1.6.0 added none; 1.7.0 adds `face`, `chair_use`, `bed_use` and `attach`, and 1.7.1 adds `air_menu`, so each of those updates rebuilds once more. Then press **Play**.

The game log (`pkp.log`) should show `play_as_pokemon 1.7.1 started` and `[play_as_pokemon] ready: ZL + L3 turns into Ditto and back, ...`.

## Choosing the Pokémon

In the launcher's **Mods** page, or in game with **F1 → Mods**:

- **Which list below picks the Pokémon**: `A to L`, `M to Z` or `Experimental forms`. The in-game menu shows at most 256 names in one list, so the Pokémon are split in two.
- **Pokémon, A to L** / **Pokémon, M to Z**: the Pokémon. Default: Ditto.
- **Experimental form**: story objects and the shapes Ditto takes for its moves. The two towers are far larger than the camera expects.

The F3 / ZL + R3 list opens on the Pokémon you are, or the one ZL + L3 would turn you into, and lists only Pokémon and forms: turn back with ZL + L3 (1.7.1). A change made in F1 while you are transformed turns you into the new Pokémon at once. The list and ZL + D-pad Left / Right pick one for this session only: the settings stay as they are.

The other settings switch flying, the Left / Right picking, the name message and using doors and the rest while transformed off.

## Flying

Since 1.5.0 climbing and descending handle like a ship: a tap of **ZR** (or **ZL**) moves you up (or down) a little, about a quarter of a block; holding it speeds up to the top speed; letting go slows you down to a hover. Pressing the other trigger first slows you down, then turns you round. The setting **Flying: top speed up and down** is `Normal` (4 blocks a second) by default, or `Slow` (2.5) or `Fast` (6).

The speeds are now the same at any frame rate. Up to 1.4.0 the mod gave the game one fixed speed every frame, and Recompia shortens the game's step above 60 fps, so how far a press took you changed with the frame rate. The mod now measures in flight how far the game moves you for a given speed and works from that; `pkp.log` notes it (`flying: one unit of vertical speed moves N cm a second`).

**Camera judder while flying:** Recompia's own **Running jump keeps speed** option (Settings > Game > Gameplay, on by default) treats the whole flight as a running jump. After you take off from a run it speeds up your flying steps by up to two times, by a factor it works out again every frame, so the camera jerks. Taking off while standing still doesn't trigger it, which is why it comes and goes. To fly smoothly, switch that option off (or set `[pkp] jump_momentum = 0` in `pkp.ini`; it applies on the next start).

## Abilities

A transformed Pokémon can use its town specialty: press **ZR**, or **ZL + D-pad Down** (flying Pokémon keep ZR for flying). It plays the Pokémon's own specialty animation and then acts on what is in front of you:

| Ability | Pokémon | Does |
|---|---|---|
| **Grow** | Bulbasaur, Oddish, Snivy, Rowlet, ... (26) | The crops and plants in front of you grow a stage, each once, as when a resident uses Grow |
| **Burn** | Charmander, Vulpix, Torchic, Litwick, ... (34) | The object in front of you is burnt: a campfire lights |
| **Water** | Squirtle, Piplup, Marill, Lapras, ... (37) | Sludge that is not bubbled yet (Bleak Beach) gets Bubbled, with the Bubble animation. Otherwise the Water Gun: it waters soil and plants and washes bubbled sludge away |
| **Generate** | Pikachu, Pawmi, Mareep, Magnemite, ... (27) | The light or machine in front of you is powered |

The setting **Ability** is `Auto` by default: each Pokémon uses its own specialty. Pick Grow, Burn, Water or Generate there to use that one with any Pokémon. A Pokémon without one of these says so when you press the button. Flying Pokémon with one of these (Charizard: Burn and Fly) fly with ZR and use the other with ZL + D-pad Down.

Burn, Generate and Bubble act as one of the Pokémon living in the area (the game only lets a town Pokémon light a campfire), so a Pokémon must live where you are. The other specialties (Chop, Crush, Recycle, Search, ...) are not in yet: the game does those inside each Pokémon's job routine, not as an effect the mod can call. Which Pokémon has which specialty comes from the lists on pokopialab.com.

Press the button once you have finished transforming: a press during the transformation is ignored (`busy` in `pkp.log`).

`pkp.log` notes each use: `ability Grow: animation started, cell in front (x, y, z) ...` and `worked at` or `nothing at`.

## Talking to Pokémon

Talking to most Pokémon makes the game turn you back into your usual character: the conversation needs it (the Pokémon that comment on your transformation don't). Since 1.2.2 the mod lets that happen and turns you back into your Pokémon when the conversation is over and you walk off.

If the game changes your form any other way, the mod turns you into your Pokémon again half a second later. If that keeps happening (more than 3 times in 20 seconds), the mod leaves it and you count as turned back: ZL + L3 transforms you again.

`pkp.log` notes each of these (`an interaction turns the player human`, `the interaction is over`, `the game turned the player into form ...`, `the game asked to turn the player into form ...`), plus `trace` lines of every form change while transformed. Please include those lines when you report a problem.

## Doors, crafting, the bag and building (1.7.0)

Since 1.7.0 a transformed player can open doors, use the crafting bench and boxes, open the bag, pick things up, and hold and place blocks, as the human does. Before, none of their prompts showed while you were transformed.

Why they were hidden: the game gives every non-human form of the player a flag (`isDitto`, player `+0x378D`) that makes it treat you as its Ditto blob and skip the human's things: the placement preview, held items, the bag and the button prompts. The mod clears that flag once you have transformed (the game sets it again on every form change, so the mod clears it each time). The setting **Use doors, the crafting bench, the bag and building while transformed** (on by default) switches this off.

Some of the human's things don't suit a Pokémon, so the mod keeps them away:

- **Chairs and beds:** the prompt still shows, but A does nothing while you're transformed. A Pokémon has no sitting or lying-down animation: in a test build, sitting down as a Pokémon locked moving, menus, moves and prompts, even after turning back, until the save was reloaded. The mod answers "no" where the game asks whether you can sit on that chair or lie on that bed (hook points `chair_use` and `bed_use`), before anything changes. Turn back with ZL + L3 to sit.
- **Items in your hand:** whatever you pick up goes into the bag as usual, but nothing is shown in your Pokémon's hand. The game puts the picked-up item on the human's hand; a Pokémon has no such hand, so the item stayed at your Pokémon's feet until you opened the bag (hook point `attach`).
- **ZR:** with the flag cleared, the game would also start the human's ZR action, which looks like an emote on a Pokémon and blocks the ability. While you're transformed the game doesn't see ZR, so it stays the ability and flying button.

`pkp.log` notes these: `interacting: <Pokémon> (form N) can use doors, the bench, the bag and build`, `no sitting for ...`, `no lying down for ...` and `nothing in hand for ...`.

**Building with an item in hand** (1.7.1): ZL + D-pad Up / Down raise and lower the block you're about to place, but ZL + D-pad Down also used the ability. While you hold something to place (a block, furniture) the mod leaves ZL + D-pad Down to the game; ZR (Pokémon that can't fly) and the ability key still work. The mod tells from the player's item-in-hand state (`+0x53A8` = 2, the held item `+0x2AD8`, the placement preview `+0x36A0`). Placing blocks while flying works as on the ground.

**The bag while flying** (1.7.1): the game ignores every button while the player is in the air (bit 0 of the body flags), unless it is the Ditto blob, so the bag didn't open while flying. A new hook point, `air_menu` (`main+0x3164A4`, the in-air test in the player's button handler), lets your Pokémon's buttons through while it is flying. A jump in the air still ignores them, as for the human.

## Link Play

The mod changes gameplay, so every player in a Link Play session needs it.

Since 1.4.0 the other players see your Pokémon, walking and moving with its own animations, and you see theirs. Before, they saw your usual character standing still in its idle pose (only your shoes and backpack changed colour).

Why: the game does send your chosen form to the other players, but a game only changes another player's form by playing that form's transformation, and only the game's own forms (Ditto and its move forms) have one. So the Pokémon arrived and was never shown, and the movements the others received were played for a Pokémon on a human model, which stood still. Now each player's mod shows the other players' Pokémon itself, the way it shows your own: it turns their character into the Pokémon, loads that Pokémon's animations for it (a Pokémon that doesn't live in the town would be invisible otherwise) and turns them back when they do. The game's own forms, such as the Ditto blob in a small space, are still left to the game.

Tested in Link Play with 1.4.0: transforming, walking, running, jumping and flying, changing Pokémon, turning back, both players in the same Pokémon, pushing each other, abilities (the other player sees the animation and the result) and talking to Pokémon while transformed.

**Ending a session while transformed** (fixed in 1.5.0): back in your own game, the host's Pokémon looked broken until they changed Pokémon, and the guest's own character stayed broken until a restart. When a session ends the game resets the world and unloads every Pokémon's animations, but the mod still counted the ones it had loaded as loaded, so it skipped loading them again (the host). The end-of-session message also turns the guest human, and the mod then took a hold on the human animations and let it go after the reset, which took away the game's own hold on them (the guest). 1.5.0 notices the reset (a new hook point, `motion_reset`) and forgets what it had loaded, and never touches the human animations. `pkp.log` notes the reset: `the game reset every Pokemon's animations ...`.

**Abilities working only once** (fixed in 1.7.0): Grow (and sometimes the others) worked once, then said "busy" until you jumped or transformed again. On a resident the game's own Pokémon code ends the Grow action; on you nothing did, so the game thought it was still playing and refused the next one. The mod now ends the action it started once the effect has happened (when you use the ability again, or 3 seconds later), with the same call the game uses when a jump interrupts an action.

**Blank eyes while swimming** (fixed in 1.7.0): as Froakie, Greninja, Cramorant and others, the eyes vanished in water. In water the game gives a player character its underwater face (face 22, made for the human and Ditto's Surf form); a Pokémon's model has no such face. The new hook point `face` (`main+0x2666C4`, just before the game sets the face) keeps the Pokémon's usual face instead, for you and for other players shown as a Pokémon.

**Crashes with three or four players** (fixed in 1.6.0): a game could crash (`pkp_crash.txt`: access violation reading `0xffffffffffffffff` in `f_71006a10e0`) right after another player changed into a Pokémon. Up to 1.5.0 the mod asked for the Pokémon form first and loaded its animations afterwards. But the game builds a model only when its animations are loaded: it threw the old model away, built nothing, and a job the game runs every frame for the four players kept using the thrown-away model until the mod built it again a few frames later. Usually that memory was still intact; when something had reused it, the game crashed. Every game sees every other player's changes, so with more players (and someone flicking through Pokémon) it became likely. Since 1.6.0 the mod loads a Pokémon's animations first and only then asks for the form, for your own character and the others', so the model is built once, with its animations. A model the game sets up by itself before they are loaded is built as the usual character for that moment instead. The animations stay loaded while the character is in that Pokémon (also while a talk turns you human) and are let go 3 seconds after it changes. The same applied to your own transformations, alone too, just far more rarely.

Since 1.2.2 the mod only touches your own character's controls and form. Before, a transformed player's game could also act on the other players' characters, for example by stopping them from turning back.

While a Link Play session is open, `pkp.log` also gets lines for the other players' characters: `remote player id 0x....` when one is seen, `remote trace` for each change of their form, `wants <Pokémon> (form N): loading it first`, `is <Pokémon> (form N): shown here` and `turns from <Pokémon> into form N` when the mod changes their form, and `remote model` for each model built. For every character, `loading <Pokémon> (form N)` and `<Pokémon> (form N) loaded in N ms` show the animations loading, and `... as the human until they are` a model the game set up before they were loaded. Please send every player's log with a report.

## How it works

The emulator version is an IPS patch plus a cheat file. Recompia runs the game as native code, so neither works there. This version is a Modtopia code mod (`mod.dll`):

- six of the IPS's eight code patches are `take_over` hook points at the same game instructions (`mod.toml` lists them with the instruction each one expects; the two small-space ground writers are not needed here since 1.2.2), plus two more (`to_human`, the game's "turn the player human for an interaction", and `motion_reset`, below);
- the cheat's button combos and memory writes run in the player's per-frame hook, with the player's controller read through Modtopia (`pad_read`);
- the animation loading (so non-resident Pokémon are not invisible) calls the game's own package and motion-set functions (`call_guest`), as the patch did. Since 1.6.0 it happens before the form is requested: a form's definition record is looked up the way the game's model setup does it (the definitions table's vfuncs 0x38 and 0x30), its packages (animations: the motion set's resource; model: definition `+0xC6`, which the model build `main+0x69DBE0` checks) are requested, and the motion set is acquired once they have loaded. The model setup hook builds the human instead of a form whose packages are not loaded, because the game would otherwise leave the model slot empty while the per-frame model parameter job (`main+0x6A10E0`) still reads it (the 1.5.0 Link Play crash). The mod's calls to these functions go one at a time (several players' updates run on different threads);
- world reset (1.5.0): the game's "release every motion set" (`main+0x8D12C0`, called only from its world reset `main+0xB6320`, which also runs when a Link Play session ends) is a hook point too; the mod forgets the animations it had loaded there, without releasing anything;
- Link Play (1.4.0): the same update runs for the other players' characters. Each game receives the others' wanted form (`main+0x271360` stores it), but changes their form only through a form's transformation action (`main+0x2F6FCC`), which only the game's own forms have. So the mod loads the Pokémon's animations, then requests the form on their character itself, turns them back the same way, and keeps the stand-up stretch off them in the probe hook;
- interacting (1.7.0): the player's `isDitto` byte (`+0x378D`) is cleared once the form has settled; a chair's "can this player sit" (`main+0x7C1838`) and a bed's (`main+0x79D948`) answer no for a transformed player at their entry, before they start the sit motion and set the player's activity (`[main+0x35650E8] + 0x140`, 15 for sitting, which stayed set); the player's hand-attachment manager (player `+0xFB0`, 14 slots of a fixed kind, the picked-up item is kind 7) gets nothing from `main+0x2A5D5C` while transformed;
- abilities: the residents' specialty actions (Burn 700, Water 703, Bubble 705, Grow 706, Generate 709) only animate when the player asks for them, because the game applies their effect for residents only. So the mod plays the action for the animation and calls the effect itself on the cell in front of the player (found as the game finds the target of the player's own moves): Grow `main+0x1F1200`, Burn and Generate `main+0x77CEA0` (the object at the cell, as a town Pokémon), Bubble the handler of action 705, the Water Gun's hit `main+0x3694C0`.

A test slot in unused game memory (`main+0x3D14D00`, used by nothing in normal play) lets a script on the PC run single ability steps; it does nothing unless a script writes its marker.

The source is `src/play_as_pokemon.c`. `include/modtopia/modtopia.h` is the Modtopia SDK header (MIT, see the LICENSE beside it).

## Build

```bash
py recompia\play-as-pokemon\build.py --zig "C:\path\to\recompia\tools\build\zig\zig.exe"
```

It writes `src/forms.h` and `mod.toml` from `mods/play-as-pokemon/pokemon.json` and `experimental.json`, compiles `mod.dll` with zig (Recompia ships one under `tools/build/zig`) and `mod.so` for Linux (with zig if it has Linux headers, else with clang + ld.lld: `--clang PATH`, e.g. llvm-mingw's), and packs `dist/recompia_play_as_pokemon-<version>.pkmod` with a `.sha256` file beside it.
