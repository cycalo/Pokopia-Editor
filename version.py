"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened."""
VERSION = (1, 3, 1)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('Fly as flying Pokémon', 'As Charizard, Scyther, Noctowl or another Pokémon that flies, press ZR to take off. '
                              'Hold ZR to rise, ZL to descend, and let go to hover. ZL + ZR drops you out of the air.'),
    ('Their own animations', "You use the Pokémon's own hover and flying animations."),
    ('Updating', 'Open the Mods page and press Update, then restart the game.'),
]
