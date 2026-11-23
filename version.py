"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened.
WHATS_NEW_PAGE is the page its button opens (None for no button)."""
VERSION = (1, 9, 2)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Play as Pokemon 1.7', 'While transformed you can open doors, use the crafting bench and boxes, open the bag and build. Also while flying.'),
    ('Fixes', 'Abilities no longer work only once, eyes no longer go blank while swimming, and ZL + D-pad moves and rotates a held block or object instead of using the ability or picking a Pokemon.'),
    ('Reinstall the mod', 'The Mods page shows Play as Pokemon as outdated: install it again. Everyone in a Link Play session needs 1.7.'),
]
WHATS_NEW_PAGE = 'Mods'
