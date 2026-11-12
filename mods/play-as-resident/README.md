# Play as Resident (experimental)

Turn into a resident Pokémon and walk around as it.

| Hold | Does |
|---|---|
| **ZL + D-pad Up** | Turn into the chosen Pokémon and stay that way |
| **ZL + D-pad Down** | Turn back into your character |

The files in this folder are set up for **Piplup**. To pick another Pokémon, use the Pokopia Editor's **Mods** page: choose it from the list and press Install. Restart the game after changing it.

**Known issue:** only Piplup has been tested. The other Pokémon are listed from the game's own data and may not all work.

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
The game identifies every character, including you, by a character number: your human form is 1, Ditto is 70, Piplup is 114. The `.ips` patch makes the game hold whatever number is stored in a "which form" value (0 means off). The cheat file writes that value and asks the game to switch you to it. `pokemon.json` lists the number for each Pokémon.
