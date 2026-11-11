==============================================================================
                           POKOPIA SAVE EDITOR  v3
                        for Pokopia 2.0.x save files
==============================================================================

Edit your bag, residents, moves, emotes and wardrobe. You can also view your
islands and photos. Every save is backed up automatically before it is
changed.


------------------------------------------------------------------------------
 GETTING STARTED
------------------------------------------------------------------------------

  1. Close your emulator.

  2. Double-click PokopiaSaveEditor.exe. No install is needed.

     If Windows shows "Windows protected your PC", click "More info"
     and then "Run anyway". The warning appears because the app is new
     and unsigned.

  The editor finds your save on its own. It works with Eden, Yuzu, Suyu,
  Sudachi, Citron, Torzu and Ryujinx. If it can't find yours, click "Open"
  and then "Browse for a folder".


------------------------------------------------------------------------------
 WHAT YOU CAN DO
------------------------------------------------------------------------------

  Overview         Rename your player, see your stats, and use quick actions:
                   max friendship, learn every emote, unlock the wardrobe,
                   fill bag stacks.

  Bag              Drag items from the list on the right into your bag.
                   Drag slots to swap them (hold Ctrl to copy).
                   Drag a slot back onto the list to remove it.

  Item Catalog     Browse and search every item. Double-click to add it.

  Residents        Set friendship, see when you met each resident, and
                   find their home on the map.

  Moves & Emotes   Click to learn or unlearn. Drag onto the wheels to
                   set them up.

  Wardrobe         Unlock any outfit or hairstyle, or all of them at once.

  Island Map       See each island from above with everything you placed.
                   Scroll to zoom, drag to move. Export as PNG.

  Photos           Browse your in-game photo album and export the photos.

  Backups          Make a backup, compare backups, or restore one.

  Advanced         Experimental settings, locked until you switch them on.
                   Only use these if you know what they do.


------------------------------------------------------------------------------
 SHORTCUTS
------------------------------------------------------------------------------

  Ctrl+O   Open a save          Ctrl+Z   Undo
  Ctrl+S   Save                 Ctrl+Y   Redo
  Ctrl+F   Search               F5       Reload
  Ctrl+1 to Ctrl+9   Switch page


------------------------------------------------------------------------------
 STAYING SAFE
------------------------------------------------------------------------------

  * Close the emulator before you save. The editor warns you if it is
    still running.

  * Before every save, you see a list of your changes. A full backup goes
    to Documents\Pokopia_Save_Backups first.

  * To undo everything, open the Backups page and restore a backup.

  * If the game saves while the editor is open, press F5 to reload before
    you make more changes.


------------------------------------------------------------------------------
 FOR ADVANCED USERS
------------------------------------------------------------------------------

  Settings are stored in %APPDATA%\Pokopia Save Editor.

  Running from source (needs Python 3):
     py -m pip install PySide6-Essentials pillow
     py pokopia_gui.py

  Command line:   py pokopia_cli.py --help
