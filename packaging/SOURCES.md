# Sources and bundled components

The release includes an archive of the editor source at its tagged commit,
including the Linux modifications and build scripts. The project is GPLv3.
Upstream attribution is in CREDITS.md.

The AppImage is a dynamically linked PyInstaller application. Extract it with
`--appimage-extract` to inspect the application, libraries and license notices.
Bundled notices and a dependency manifest are under
`usr/share/doc/pokopia-editor`. The release also provides these as separate assets.

Python package versions are recorded in the manifest. Their upstream sources are

- Python — https://www.python.org/downloads/source/
- PySide6 and Shiboken — https://code.qt.io/pyside/pyside-setup.git/
- Qt — https://code.qt.io/qt/ and https://download.qt.io/archive/qt/
- Pillow — https://github.com/python-pillow/Pillow
- PyInstaller and its bootloader — https://github.com/pyinstaller/pyinstaller
- AppImage runtime — https://github.com/AppImage/type2-runtime

Use the version tags matching the manifest when obtaining sources. PySide6's Qt
libraries use the same release series as the installed PySide6 package.

The system library entries include the Ubuntu binary package version, source
package name and source version. Their copyright files contain upstream source
locations and license terms. Ubuntu package sources can be obtained through the
matching Ubuntu release's source repositories with

```sh
apt-get source SOURCE_PACKAGE=SOURCE_VERSION
```

Replace the placeholders with an entry from bundled-dependencies.json. Ubuntu
source packages can also be located at https://launchpad.net/ubuntu/+source/.
