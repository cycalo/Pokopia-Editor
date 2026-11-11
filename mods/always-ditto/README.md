# Always Ditto (experimental)

Turn into Ditto anywhere, not only inside small spaces.

| Hold | Does |
|---|---|
| **ZL + A** | Ditto mode on: you turn into Ditto and stay Ditto |
| **ZL + B** | Ditto mode off: the game turns you back into your character |

While Ditto mode is off, the game plays exactly as normal.

**Known issue:** out in the open, Ditto keeps flashing and stretching about twice a second. You stay Ditto, but it doesn't look like the flat, squashed shape it has in a small space yet.

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
The `.ips` patch is applied when the game loads. It changes four small pieces of the game's player code, and each one only acts while an on/off byte is set:

1. The player's "desired form" reports Ditto.
2. Writes to the stored desired form are forced to Ditto.
3. The ground check always reports "in a small space".
4. Requests to switch back to the normal form are ignored.

The cheat file only writes data. ZL + A sets the byte and asks the game to switch to Ditto. ZL + B clears it.
