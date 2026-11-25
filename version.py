"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened.
WHATS_NEW_PAGE is the page its button opens (None for no button)."""
VERSION = (1, 9, 2)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Play as Pokemon 1.7', 'While transformed you can open doors, use the crafting bench and boxes, open the bag and build. Also while flying. Headbutting a fruit tree drops its fruit.'),
    ('Swimming and diving', 'A Pokemon no longer gets stuck drowning, and Dive works while transformed: ZL dives, ZR rises. Tilt the stick all the way to fly or swim fast at once.'),
    ("Fixes", "Abilities no longer work only once, eyes no longer go blank while swimming, items no longer stick to other players' faces in co-op, and ZL + D-pad moves and rotates a held block or object."),
    ('Quests (experimental)', 'A new page under Tools shows where every quest stands and can finish one that is stuck, for example after Link Play.'),
    ('Reinstall the mod', 'The Mods page shows Play as Pokemon as outdated: install it again. Everyone in a Link Play session needs 1.7.1.'),
]
WHATS_NEW_PAGE = 'Mods'
