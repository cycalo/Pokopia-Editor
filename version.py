# Linux port modifications by frinimini, 2026-11-24. See CREDITS.md.
"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; Linux release tags use linux-v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened.
WHATS_NEW_PAGE is the page its button opens (None for no button)."""
UPSTREAM_VERSION = (1, 9, 2)
VERSION = (1, 0, 0)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Linux 1.0', 'First regular Linux release, based on upstream Pokopia Editor 1.9.2.'),
    ('Map brushes', 'Circle, Square and Rectangle brushes with width, depth and cell counts for painting and ground height.'),
    ('Live editing', 'Launch Lichii from the Mods page to use verified live transformation on the supported Pokopia build.'),
    ('Known issue', 'Cut and Rock Smash can fail while transformed. See the README for tested features and limitations.'),
]
WHATS_NEW_PAGE = 'Island Map'
