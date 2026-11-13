"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened."""
VERSION = (1, 3, 0)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Play as Pokemon', 'Always Ditto and Play as Resident are now one mod. Turn into Ditto or any other Pokémon.'),
    ('Any Pokémon works', 'Pokémon that don\'t live in your town are no longer invisible.'),
    ('Change Pokémon while playing', 'With the game running, pick a Pokémon on the Mods page and press Transform. '
                                     'No restart needed.'),
    ('New buttons', 'ZL + D-pad Left turns you into the Pokémon you picked. ZL + D-pad Right turns you back.'),
    ('Updating', 'Open the Mods page and press Update. It replaces the two old mods. Then restart the game and '
                 'tick Play as Pokemon under Properties → Add-Ons.'),
]
