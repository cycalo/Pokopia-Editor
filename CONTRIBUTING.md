# Contributing

Open issues and pull requests at https://github.com/cycalo/Pokopia-Editor.
Preserve existing author, copyright and license notices. Contributions must be
compatible with the project's GPLv3 license. Identify the source and license of
added third-party code or assets, and include the applicable notices.

For Linux source setup and AppImage builds, see the Linux section in `README.md`.
Run the regression checks with:

```sh
.build-venv/bin/python -m unittest discover -s tests -v
```

For packaging changes, build with `bash tools/build_appimage.sh` and verify startup
from the resulting AppImage. Report the distribution and architecture tested,
and distinguish startup checks from validation using a backed-up save.
