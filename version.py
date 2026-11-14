"""App version, read by the window (update check, What's New) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>.
Rewrite WHATS_NEW for each release: it is shown once, the first time that version is opened."""
VERSION = (1, 4, 0)
VERSION_STR = '.'.join(map(str, VERSION))

WHATS_NEW = [
    ('DLC and Event tags', 'Items, outfits, hairstyles and residents from the Expansion Pass or a limited-time event '
                           'are now marked. The item browser has DLC and Event filters.'),
    ('Three more outfits', 'Rad, Cheerful and Triathlete can be unlocked on the Wardrobe page.'),
    ('Backups', 'Delete backups you no longer need, refresh the list, and choose whether a restore backs up the '
                'current save first.'),
    ('Experimental forms', 'Play as Pokemon can now turn you into things that are not Pokémon, such as the '
                           'Master Ball or Ditto\'s Surf and Glide forms. Tinkaton was added to the Pokémon list. '
                           'Find them on the Mods page while the game is running.'),
]
