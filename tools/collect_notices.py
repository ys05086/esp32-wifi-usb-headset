"""Collect installed wheel notices and inventory an existing Windows bundle.

Run in the same Python environment used by PyInstaller. This is evidence
collection, not a declaration of complete license compliance.
"""
import argparse
import ctypes
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(bundle, output):
    output.mkdir(parents=True, exist_ok=True)
    records = []
    packages = ['numpy', 'sounddevice', 'soxr', 'av', 'cffi', 'pycparser']
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

    runtime = []
    # Inspect copies from this bundle, not unrelated FFmpeg executables on PATH.
    dll_dir = bundle / '_internal' / 'av.libs'
    if sys.platform == 'win32' and dll_dir.exists():
        import os
        import pefile  # Installed with the Windows PyInstaller build toolchain.
        with os.add_dll_directory(str(dll_dir.resolve())):
            for prefix in ('avcodec', 'avformat', 'avutil', 'avdevice', 'avfilter',
                           'swresample', 'swscale'):
                for dll in sorted(dll_dir.glob(prefix + '-*.dll')):
                    lib = ctypes.CDLL(str(dll.resolve()))
                    row = {'file': dll.relative_to(bundle).as_posix(),
                           'sha256': digest(dll)}
                    with pefile.PE(str(dll)) as pe:
                        row['imports'] = [entry.dll.decode('ascii') for entry in
                                          getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])]
                    for suffix in ('license', 'configuration', 'version'):
                        fn = getattr(lib, prefix + '_' + suffix)
                        fn.restype = ctypes.c_uint if suffix == 'version' else ctypes.c_char_p
                        value = fn()
                        row[suffix] = value if suffix == 'version' else value.decode('utf-8')
                    runtime.append(row)

    binaries = []
    for path in sorted((bundle / '_internal').rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.dll', '.pyd', '.dylib'):
            binaries.append({'file': path.relative_to(bundle).as_posix(),
                             'sha256': digest(path)})
    gpl_candidates = [x['file'] for x in binaries
                      if Path(x['file']).name.lower().startswith(('libx264', 'libx265'))]
    report = {'scope': 'Installed package notices and actual bundled native binaries',
              'compliance_complete': False, 'packages': records,
              'ffmpeg_runtime_self_report': runtime, 'native_binaries': binaries,
              'gpl_components_present': gpl_candidates,
              'remaining': ['Resolve exact native-library source/build provenance and notices',
                            'Provide corresponding sources and applicable relinking materials',
                            'Review FFmpeg GPL dependencies even if DLL self-report says LGPL',
                            'Review ASIO SDK and Microsoft runtime redistribution notices']}
    (output / 'inventory.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Collected {len(records)} package/runtime notice sets; '
          f'inventoried {len(binaries)} native files; GPL candidates: {len(gpl_candidates)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.bundle, args.output)
