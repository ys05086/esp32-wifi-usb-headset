"""Collect installed wheel notices and inventory an existing Windows bundle.

Run in the same Python environment used by PyInstaller. This is evidence
collection, not a declaration of complete license compliance.
"""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(bundle, output):
    output.mkdir(parents=True, exist_ok=True)
    records = []
    packages = ['numpy', 'sounddevice', 'soxr', 'cffi', 'pycparser', 'pyserial']
    # Wheels that ship no license file: the text from the tagged source, kept in this repository.
    reference = {'pyserial': Path(__file__).resolve().parents[1] / 'licenses' / 'python-packages' / 'pyserial'}
    # Optional modules observed in a PyInstaller build are also distributed code.
    for folder, package in [('PIL', 'Pillow'), ('yaml', 'PyYAML')]:
        if (bundle / '_internal' / folder).exists():
            packages.append(package)
    for name in packages:
        dist = metadata.distribution(name)
        copied = []
        for file in dist.files or []:
            path = Path(str(file))
            if not any(path.name.lower().startswith(prefix) for prefix in
                       ('license', 'licence', 'copying', 'notice', 'authors')):
                continue
            if path.suffix.lower() in ('.py', '.pyc'):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            target = output / 'python-packages' / name / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append({'file': target.relative_to(output).as_posix(),
                           'sha256': digest(target)})
        if not copied and name in reference:
            for source in sorted(reference[name].iterdir()):
                target = output / 'python-packages' / name / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                copied.append({'file': target.relative_to(output).as_posix(), 'sha256': digest(target)})
        if not copied:
            raise RuntimeError(f'No installed license text found for {name}')
        records.append({'package': name, 'version': dist.version,
                        'license_expression': dist.metadata.get('License-Expression'),
                        'files': copied})

    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python installation LICENSE.txt not found')
    target = output / 'python-runtime' / 'LICENSE.txt'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(python_license, target)
    records.append({'package': 'CPython', 'version': platform.python_version(),
                    'files': [{'file': target.relative_to(output).as_posix(),
                               'sha256': digest(target)}]})

    # The AAC comparison runs the bundled minimal FFmpeg (tools/build_ffmpeg.sh), not a library in _internal.
    ffmpeg = bundle / 'ffmpeg' / 'ffmpeg.exe'
    if not ffmpeg.is_file():
        raise RuntimeError('Bundled ffmpeg/ffmpeg.exe not found')
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    version = subprocess.run([str(ffmpeg), '-hide_banner', '-version'], capture_output=True, text=True,
                             creationflags=flags, check=True).stdout
    license_text = subprocess.run([str(ffmpeg), '-hide_banner', '-L'], capture_output=True, text=True,
                                  creationflags=flags, check=True).stdout
    configuration = next((line for line in version.splitlines() if line.startswith('configuration:')), '')
    if '--enable-gpl' in configuration or '--enable-nonfree' in configuration or 'GNU Lesser General Public' not in license_text:
        raise RuntimeError('Bundled ffmpeg is not an LGPL build')
    sources = sorted((bundle / 'ffmpeg' / 'source').glob('ffmpeg-*.tar.xz'))
    if not sources:
        raise RuntimeError('FFmpeg source tarball missing next to the bundled ffmpeg')
    runtime = {'file': ffmpeg.relative_to(bundle).as_posix(), 'sha256': digest(ffmpeg),
               'version': version.splitlines()[0], 'configuration': configuration,
               'license': 'LGPL version 2.1 or later',
               'source': [{'file': x.relative_to(bundle).as_posix(), 'sha256': digest(x)} for x in sources]}

    binaries = []
    # _internal: ESP32AudioBridge.exe; setup_files: ESP32BoardSetup.exe
    for path in sorted(p for folder in ('_internal', 'setup_files') for p in (bundle / folder).rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.dll', '.pyd', '.dylib'):
            binaries.append({'file': path.relative_to(bundle).as_posix(),
                             'sha256': digest(path)})
    gpl_candidates = [x['file'] for x in binaries
                      if Path(x['file']).name.lower().startswith(('libx264', 'libx265', 'avcodec'))]
    report = {'scope': 'Installed package notices and actual bundled native binaries',
              'compliance_complete': False, 'packages': records,
              'ffmpeg': runtime, 'native_binaries': binaries,
              'gpl_components_present': gpl_candidates,
              'remaining': ['Resolve exact native-library source/build provenance and notices',
                            'Provide corresponding sources for soxr (LGPL) and other bundled native libraries',
                            'Review ASIO SDK and Microsoft runtime redistribution notices']}
    (output / 'inventory.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Collected {len(records)} package/runtime notice sets; '
          f'inventoried {len(binaries)} native files; GPL candidates: {len(gpl_candidates)}; '
          f'ffmpeg {runtime["version"]}')
    if gpl_candidates:
        raise RuntimeError(f'GPL libraries in the bundle: {gpl_candidates}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.bundle, args.output)
