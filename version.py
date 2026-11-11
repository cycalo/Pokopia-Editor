"""App version, read by the window (update check) and by PokopiaSaveEditor.spec (exe file version).

Bump this before building a release; the GitHub release tag should be v<VERSION>."""
VERSION = (1, 1, 0)
VERSION_STR = '.'.join(map(str, VERSION))
