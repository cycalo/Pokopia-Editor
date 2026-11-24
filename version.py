# Linux port modifications by frinimini, 2026-11-24. See CREDITS.md.
"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; Linux release tags use linux-v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened.
WHATS_NEW_PAGE is the page its button opens (None for no button)."""
UPSTREAM_VERSION = (1, 9, 2)
VERSION = (1, 1, 0)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Height layers', 'Inspect the terrain and objects stacked at a clicked map cell, grouped by Y height.'),
    ('Reveal a level', 'Select a layer to reveal it, step between occupied heights, or show all heights again.'),
    ('Map controls', 'Height controls sit below the island selector. Visibility switches are grouped under Map overlays.'),
]
WHATS_NEW_PAGE = 'Island Map'
