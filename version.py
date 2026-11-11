"""App version, read by the window (update check) and by PokopiaEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>."""
VERSION = (1, 2, 0)
VERSION_STR = '.'.join(map(str, VERSION))
