"""Include notices supplied by the installed build dependencies."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

output = Path(sys.argv[1])
for name in ('PySide6-Essentials', 'shiboken6', 'Pillow', 'PyInstaller'):
    package = distribution(name)
    for entry in package.files or ():
        if any(word in entry.name.lower() for word in ('license', 'copying', 'notice')):
            target = output / name / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package.locate_file(entry), target)
