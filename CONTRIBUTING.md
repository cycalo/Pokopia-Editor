# Contributing

This fork maintains the Linux port of cycalo's Pokopia Editor. Open Linux issues
and pull requests at https://github.com/frinimini/Pokopia-Editor-Linux.
Credit upstream work and preserve existing author, copyright and license notices.
Contributions must be compatible with the project's GPLv3 license. Identify the
source and license of any added third-party code or assets and include its notices.

Follow the Linux source setup in `README.md`, then run the regression checks.

```sh
.build-venv/bin/python -m unittest discover -s tests -v
```

For packaging changes, rebuild with `bash tools/build_appimage.sh` and verify GUI
startup from the resulting AppImage. Report the distribution and architecture used
and distinguish startup checks from tests using an actual save.
