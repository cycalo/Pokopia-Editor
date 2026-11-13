# Always Ditto (experimental)

Turn into Ditto anywhere, not only inside small spaces.

| Hold | Does |
|---|---|
| **ZL + D-pad Left** | Ditto mode on: you turn into Ditto and stay Ditto |
| **ZL + D-pad Right** | Ditto mode off: the game turns you back into your character |

While Ditto mode is off, the game plays exactly as normal.

**Only for Pokopia 2.0.0, update 655360** (build ID `76A489F3BD3642FA`). On any other version the patch is not applied.

## Install

The easiest way is the Pokopia Editor's **Mods** page, which can install it straight into your emulator or save it in the right folder layout.

### Emulator (Eden, Yuzu and forks)
Copy the files into the emulator's `load` folder like this, then make sure **Always Ditto** is ticked in the game's Properties → Add-Ons:

```
load/0400A3A01EE4C000/Always Ditto/exefs/76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips
load/0400A3A01EE4C000/Always Ditto/cheats/76A489F3BD3642FA.txt
```

Use the combos only once you're in the world, not on the title screen.

### Console with custom firmware (untested)
For Atmosphère-style custom firmware, the files go on the SD card here:

```
atmosphere/exefs_patches/Always Ditto/76A489F3BD3642FA5E18BD83D32C98BACC5F7D0E.ips
atmosphere/contents/0400A3A01EE4C000/cheats/76A489F3BD3642FA.txt
```

This has only been tested on an emulator. A stock console can't load patches or cheats, and modding a console can get it banned from online services.

## How it works
The `.ips` patch is applied when the game loads. It changes five small pieces of the game's code, and each one only acts while a "which form" value is set (0 means off, 70 is Ditto):

1. The player's "desired form" reports Ditto.
2. Writes to the stored desired form are forced to Ditto.
3. The ground check always reports "in a small space".
4. Requests to switch back to the normal form are ignored.
5. The player's "something is in the way" animation check always passes, so Ditto's idle never starts the stand-up stretch.

The cheat file only writes data. ZL + D-pad Left sets the value to Ditto and asks the game to switch. ZL + D-pad Right clears it.

The same patch file is shared with the Play as Resident mod, so both can be ticked at once. Since 0.6 it also contains that mod's animation loading, which does nothing for Ditto.
