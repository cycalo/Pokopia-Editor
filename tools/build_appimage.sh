#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Run with the Python environment containing the pinned build dependencies.
PYTHON="${PYTHON:-.build-venv/bin/python}"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"
version="$("$PYTHON" -c 'from version import VERSION_STR; print(VERSION_STR)')"
appdir="$PWD/build/PokopiaEditor.AppDir"
"$PYTHON" -m PyInstaller --noconfirm --clean --onedir --windowed \
    --specpath build/linux --name PokopiaEditor --add-data "$PWD/data:data" --add-data "$PWD/mods:mods" \
    --add-data "$PWD/LICENSE:." --exclude-module tkinter \
    --exclude-module unittest pokopia_gui.py
mkdir -p "$appdir/usr/bin"
rm -rf "$appdir/usr/bin/PokopiaEditor"
cp -a dist/PokopiaEditor "$appdir/usr/bin/"
cp packaging/AppRun "$appdir/AppRun"
cp packaging/pokopia-editor.desktop "$appdir/"
cp data/app.png "$appdir/pokopia-editor.png"
docdir="$appdir/usr/share/doc/pokopia-editor"
mkdir -p "$docdir/licenses"
cp LICENSE CREDITS.md CONTRIBUTING.md packaging/SOURCES.md "$docdir/"
cp packaging/licenses/* "$docdir/licenses/"
"$PYTHON" tools/collect_dependency_licenses.py "$docdir/licenses"
chmod +x "$appdir/AppRun"
output="dist/PokopiaEditor-${version}-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" "$appdir" "$output.tmp"
mv -f "$output.tmp" "$output"
