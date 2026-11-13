# Play as Pokemon (experimental)

Turn into Ditto or any other Pokémon and walk around as it. It doesn't have to live in your town.

| Hold | Does |
|---|---|
| **ZL + D-pad Left** | Turn into the chosen Pokémon and stay that way |
| **ZL + D-pad Right** | Turn back into your character |

This mod replaces **Always Ditto** and **Play as Resident**. Remove those two before using it: they use the same buttons. The Pokopia Editor's **Mods** page does that for you when you press Install or Update.

**Only for Pokopia 2.0.0, update 655360** (build ID `76A489F3BD3642FA`). On any other version the patch is not applied.

## Choosing the Pokémon

**While playing (emulator on Windows).** With the mod installed and the game running, open the editor's **Mods** page, pick a Pokémon under **Change Pokémon while playing** and press **Transform**. No restart is needed. **Turn back** returns you to your character. The button combo then uses the Pokémon you picked last. Until you pick one, it turns you into Ditto.

**A fixed Pokémon.** On the Mods page, change the Pokémon list from **Any (choose while playing)** to one Pokémon and press Install. The button combo then always turns you into that Pokémon. Restart the game after changing it. Use this on a console, where the editor can't reach the running game.

The files in this folder are the "Any" setup: `76A489F3BD3642FA.any.txt` is the cheat file it installs, and `76A489F3BD3642FA.txt` is the template for a fixed Pokémon (written for Piplup).

A Pokémon that doesn't live in your town appears a fraction of a second after the transform, because the game has to load its animations first.

**Known issue:** Ditto, Pokémon that live in your town, and Espeon, Umbreon, Jolteon, Flareon and Vaporeon have been tested. The rest are listed from the game's data and may not all work.

## Install

The easiest way is the Pokopia Editor's **Mods** page, which installs it straight into your emulator or saves it in the right folder layout.

### Emulator (Eden, Yuzu and forks)
Copy the files into the emulator's `load` folder like this, then make sure **Play as Pokemon** is ticked in the game's Properties → Add-Ons:

```
load/0400A3A01EE4C000/Play as Pokemon/exefs/76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips
load/0400A3A01EE4C000/Play as Pokemon/cheats/76A489F3BD3642FA.txt
```

Keep **Enable GDB Stub** off, and use the combos only once you're in the world, not on the title screen.

### Console with custom firmware (untested)
```
atmosphere/exefs_patches/Play as Pokemon/76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips
atmosphere/contents/0400A3A01EE4C000/cheats/76A489F3BD3642FA.txt
```

This has only been tested on an emulator. A stock console can't load patches or cheats, and modding a console can get it banned from online services.

## How it works
The game identifies every character, including you, by a character number: your human form is 1, Ditto is 70, Piplup is 114. `pokemon.json` lists the number for each Pokémon.

The `.ips` patch is applied when the game loads. Each change only acts while a "which form" value is set (0 means off):

1. The player's "desired form" reports that form, and writes to it are forced to that form.
2. The ground check always reports "in a small space", which is where the game normally allows Ditto.
3. Requests to switch back to the normal form are ignored.
4. The player's "something is in the way" animation check always passes, so Ditto's idle never starts the stand-up stretch.
5. The game only loads a Pokémon's animations while that Pokémon lives in your town, and a model without animations is drawn as nothing. So the patch loads the animations of the Pokémon you turn into, then repeats the form change once they are ready.

The cheat file only writes data: it sets the "which form" value and asks the game to switch. The "Any" cheat reads the Pokémon from a second value, which the editor sets while the game runs by writing to the emulator's memory. Neither touches your save.
