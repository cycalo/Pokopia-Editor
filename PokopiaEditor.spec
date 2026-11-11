# PyInstaller build for the single-file Windows release.
#   .build-venv\Scripts\python -m PyInstaller PokopiaEditor.spec --noconfirm
# Output: dist\PokopiaEditor.exe
from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
                                                 StringStruct, VarFileInfo, VarStruct)

import sys
sys.path.insert(0, SPECPATH)
from version import VERSION as _APP_VERSION  # single source, also used by the update check

VERSION = tuple(_APP_VERSION) + (0,)
VERSION_STR = '.'.join(map(str, VERSION[:3]))

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION, prodvers=VERSION),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('FileDescription', 'Pokopia Editor'),
            StringStruct('ProductName', 'Pokopia Editor'),
            StringStruct('FileVersion', VERSION_STR),
            StringStruct('ProductVersion', VERSION_STR),
            StringStruct('OriginalFilename', 'PokopiaEditor.exe'),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

a = Analysis(
    ['pokopia_gui.py'],
    pathex=['.'],
    datas=[('data', 'data'), ('mods', 'mods')],
    hiddenimports=[
        'gui.pages.overview', 'gui.pages.bag', 'gui.pages.residents', 'gui.pages.moves',
        'gui.pages.wardrobe', 'gui.pages.map', 'gui.pages.photos', 'gui.pages.backups', 'gui.pages.advanced', 'gui.pages.mods', 'gui.pages.welcome',
    ],
    excludes=['tkinter', 'unittest', 'pydoc', 'test'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='PokopiaEditor',
    icon='data/app.ico',
    version=version_info,
    console=False,
    upx=False,
)
