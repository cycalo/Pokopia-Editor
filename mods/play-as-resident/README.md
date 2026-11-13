# Play as Resident (experimental)

Turn into a Pokémon and walk around as it. It doesn't have to live in your town.

| Hold | Does |
|---|---|
| **ZL + D-pad Up** | Turn into the chosen Pokémon and stay that way |
| **ZL + D-pad Down** | Turn back into your character |

The files in this folder are set up for **Piplup**. To pick another Pokémon, use the Pokopia Editor's **Mods** page: choose it from the list and press Install. Restart the game after changing it.

## Change Pokémon while playing (emulator on Windows)

With the mod installed and the game running, the editor's **Mods** page can change your Pokémon on the spot: under **Change Pokémon while playing**, pick one and press **Transform**. No restart is needed. **Turn back** returns you to your character.

To make the button combo follow that choice too, pick **Any (choose while playing)** in the Pokémon list before you press Install. ZL + D-pad Up then turns you into the last Pokémon you picked in the editor, and does nothing until you have picked one. That cheat file is `76A489F3BD3642FA.any.txt`.

This works by writing to the running emulator's memory, so it needs a Yuzu-family emulator on the same Windows PC as the editor. It does not work on a console, and it never touches your save.

A Pokémon that doesn't live in your town appears a fraction of a second after the transform, because the game has to load its animations first.

**Known issue:** pokémon that live in your town, plus Espeon, Umbreon, Jolteon, Flareon and Vaporeon, have been tested. The rest are listed from the game's data and may not all work.

**Only for Pokopia 2.0.0, update 655360** (build ID `76A489F3BD3642FA`). On any other version the patch is not applied.

## Works next to Always Ditto

This mod and Always Ditto ship the same `.ips` patch and have their own button combos, so both can be ticked at once. Use Always Ditto 0.5 or newer; the older 0.4 patch is not compatible with this mod.

## Install

### Emulator (Eden, Yuzu and forks)
Copy the files into the emulator's `load` folder like this, then make sure **Play as Resident** is ticked in the game's Properties → Add-Ons:

```
load/0400A3A01EE4C000/Play as Resident/exefs/76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips
load/0400A3A01EE4C000/Play as Resident/cheats/76A489F3BD3642FA.txt
```

Use the combos only once you're in the world, not on the title screen.

### Console with custom firmware (untested)
```
atmosphere/exefs_patches/Play as Resident/76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips
atmosphere/contents/0400A3A01EE4C000/cheats/76A489F3BD3642FA.txt
```

On an SD card both mods use the same cheat file path. To use both, paste the contents of one cheat file under the other in a single file.

## How it works
The game identifies every character, including you, by a character number: your human form is 1, Ditto is 70, Piplup is 114. The `.ips` patch makes the game hold whatever number is stored in a "which form" value (0 means off). The cheat file writes that value and asks the game to switch you to it. `pokemon.json` lists the number for each Pokémon. The "Any" cheat reads the number from a second value, which the editor sets while the game runs.

The game only loads a Pokémon's animations while that Pokémon lives in your town, and a model without animations is drawn as nothing. So the patch also loads the animations of the Pokémon you turn into, then repeats the form change once they are ready.
