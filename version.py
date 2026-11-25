# Linux port modifications by frinimini, 2026-11-24. See CREDITS.md.
"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; Linux release tags use linux-v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened.
WHATS_NEW_PAGE is the page its button opens (None for no button)."""
UPSTREAM_VERSION = (1, 9, 2)
VERSION = (1, 1, 0)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Paint rectangles and layers', 'Shift-drag in Paint ground to paint a rectangle on release. Enable Paint all terrain layers below to recolour existing terrain beneath the surface, preserving bedrock, water, air and objects.'),
    ('Spacebar panning', 'Hold Space and drag over the map to pan, even after using a height control. Release Space to return to your tool.'),
    ('Height rectangles', 'With Ground height selected, hold Shift and drag a rectangle. Release to apply Raise, Lower or Flatten to the selected area. Esc cancels before release.'),
    ('Lift objects with terrain', 'Enable Move objects and placed items up in Ground height to lift obstructing objects and their stacks when raising or flattening terrain. The setting is remembered; undo restores terrain and objects together.'),
    ('Glowing Blocks', 'Gold markers reveal saved treasure spots, including buried ones, with read-only entries in height layers and tile contents.'),
    ('Remember tools', 'Tool preferences, map brushes, filters and the last page are restored when you reopen the editor.'),
    ('Tile contents', 'Click a tile stack badge to browse its objects and terrain with icons and select a particular entry.'),
    ('Height layers', 'Inspect the terrain and objects stacked at a clicked map cell, grouped by Y height.'),
    ('Reveal a level', 'Select a layer to reveal it, step between occupied heights, or show all heights again.'),
    ('Map controls', 'Height controls sit below the island selector. Visibility switches are grouped under Map overlays.'),
]
WHATS_NEW_PAGE = 'Island Map'
