"""Include notices supplied by the installed build dependencies."""
import ast
import json
from importlib.metadata import distribution
from pathlib import Path
import shutil
import subprocess
import sys

output = Path(sys.argv[1])
manifest = {'python_packages': [], 'system_packages': []}
for name in ('PySide6-Essentials', 'shiboken6', 'Pillow', 'PyInstaller'):
    package = distribution(name)
    manifest['python_packages'].append({'name': name, 'version': package.version,
                                        'project_urls': package.metadata.get_all('Project-URL') or []})
    for entry in package.files or ():
        if any(word in entry.name.lower() for word in ('license', 'copying', 'notice')):
            target = output / name / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package.locate_file(entry), target)

# PyInstaller records the original library paths, including transitive system libraries.
toc = ast.literal_eval(Path('build/PokopiaEditor/Analysis-00.toc').read_text())
paths = set()
def binary_paths(value):
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and isinstance(value[1], str) and value[2] in ('BINARY', 'EXTENSION'):
            paths.add(value[1])
        else:
            for child in value:
                binary_paths(child)
binary_paths(toc)
packages = set()
for source in sorted(paths):
    if not source.startswith(('/usr/', '/lib/')):
        continue
    result = subprocess.run(['dpkg-query', '-S', source, str(Path(source).resolve())],
                            capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if ': ' in line:
            packages.update(line.split(': ', 1)[0].split(', '))
for name in sorted(packages):
    result = subprocess.run(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${source:Package}\t${source:Version}', name],
                            capture_output=True, text=True, check=True)
    package, version, source, source_version = result.stdout.split('\t')
    manifest['system_packages'].append(dict(name=package, version=version, source=source,
                                            source_version=source_version))
    notice = Path('/usr/share/doc') / package / 'copyright'
    if notice.is_file():
        target = output / 'system' / package / 'copyright'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(notice, target)
common = Path('/usr/share/common-licenses')
if common.is_dir():
    shutil.copytree(common, output / 'common-licenses', dirs_exist_ok=True)
(output.parent / 'bundled-dependencies.json').write_text(json.dumps(manifest, indent=2) + '\n')
