# Credits and licenses

## Upstream project

Pokopia Editor was created by cycalo and its upstream contributors.
This fork derives from upstream commit `d0dd2f7` and preserves its Git history.
The editor is distributed under GNU GPL version 3, with the full text in `LICENSE`.

Upstream source and contributor history are available at
https://github.com/cycalo/Pokopia-Editor.

The upstream project credits berichan's PokoHex for save data and research.
https://github.com/berichan/PokoHex

## Linux port

Linux modifications by frinimini, November 24, 2026, add AppImage packaging,
Linux settings storage, folder opening, emulator detection, bundled UI icons,
experimental procfs live memory access and launching emulators as child processes.
The fork also updates setup documentation and release links.
These changes are distributed under the project's GPLv3 license.

Source and build instructions are available at
https://github.com/frinimini/Pokopia-Editor-Linux.

## Third-party material

- Microsoft Fluent System Icons and the Linux icon mapping use the MIT-licensed
  icon project. Copyright (c) 2020 Microsoft Corporation. The complete notice is
  in `data/fonts/LICENSE-FluentSystemIcons.txt`. Font and mapping source are at
  https://github.com/microsoft/fluentui-system-icons/tree/main/fonts.
- Upstream Modtopia headers retain their MIT license and contributor copyright
  in `recompia/play-as-pokemon/include/modtopia/LICENSE`.
- Pokémon names, icons and game assets belong to their respective rights holders,
  including Nintendo, Game Freak and The Pokémon Company, as credited upstream.
  Their inclusion does not grant a separate license to those assets.

## Packaged dependencies

The Linux build uses Python, PySide6/Qt, Shiboken, Pillow and the PyInstaller
bootloader. Their licenses apply to their respective components. Build packaging
copies available dependency license notices into `usr/share/doc/pokopia-editor/licenses`
and includes the Qt GPLv3 and LGPLv3 license texts.

Version pins are in `packaging/requirements-linux.txt`. Dependency source locations
are https://www.python.org/downloads/source/, https://code.qt.io/pyside/pyside-setup.git/,
https://code.qt.io/qt/, https://github.com/python-pillow/Pillow and
https://github.com/pyinstaller/pyinstaller.

Before publishing binary releases, check the exact bundled runtime components and
provide the corresponding source and notices required by their licenses.
