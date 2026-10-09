"""The firmware that ships next to the setup program: firmware/manifest.json plus the images it lists.

manifest.json (written by CI):
  {"board": "esp32-wifi-usb-headset", "version": "abc1234", "chip": "esp32s3", "flash_size": "16MB",
   "files": [{"name": "bootloader", "offset": 0, "file": "bootloader.bin", "sha256": "..."}, ...]}
Writing bootloader, partition table and app separately leaves the settings (NVS) in between untouched.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys

BOARD = 'esp32-wifi-usb-headset'


def default_folder():
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    return base / 'firmware'


@dataclass
class Image:
    name: str
    offset: int
    data: bytes


@dataclass
class Bundle:
    version: str
    flash_size: int
    images: list
    folder: Path

    @property
    def nvs(self):
        """(offset, size) of the settings partition, from the bundled partition table."""
        table = next((x.data for x in self.images if x.name == 'partition-table'), b'')
        return nvs_region(table)


def flash_bytes(text):
    if not text.upper().endswith('MB'):
        raise ValueError(f'unexpected flash size {text}')
    return int(text[:-2]) << 20


def load(folder=None):
    folder = Path(folder or default_folder())
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('board') != BOARD or manifest.get('chip') != 'esp32s3':
        raise ValueError('이 보드용 펌웨어가 아니에요 (manifest.json)')
    images = []
    for entry in manifest['files']:
        data = (folder / entry['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f"{entry['file']} 파일이 손상됐어요 (SHA-256 불일치)")
        images.append(Image(entry['name'], int(entry['offset']), data))
    names = {x.name for x in images}
    if not {'bootloader', 'partition-table', 'app'} <= names:
        raise ValueError('manifest.json에 bootloader, partition-table, app이 모두 있어야 해요')
    return Bundle(str(manifest.get('version', '?')), flash_bytes(manifest['flash_size']),
                  sorted(images, key=lambda x: x.offset), folder)


def install(port, bundle, reset_settings=False, progress=None, baud=460800, reset=True, loader=None):
    """Writes the bundle through the ROM loader, each region checked by MD5, then boots it.
    reset_settings also blanks the NVS partition: a new board Wi-Fi password, no router, Standard USB mode.
    progress(fraction, text) is called from this (worker) thread."""
    from esp_rom import RomLoader, Unsupported
    loader = loader or RomLoader(port)
    say = progress or (lambda fraction, text: None)
    say(0, '다운로드 모드로 들어가는 중')
    loader.connect(reset=reset)
    if baud and baud != port.baudrate:
        loader.change_baud(baud)
    loader.attach_flash(bundle.flash_size)
    jobs = [(x.name, x.offset, x.data) for x in bundle.images]
    if reset_settings:
        if not bundle.nvs:
            raise ValueError('파티션 표에 설정(NVS) 영역이 없어요')
        offset, size = bundle.nvs
        jobs.append(('settings', offset, b'\xff' * size))
    total, done, compress = sum(len(data) for _, _, data in jobs), 0, True
    for name, offset, data in jobs:
        show = lambda f, done=done, size=len(data): say((done + f * size) / total, f'{name} 쓰는 중 (0x{offset:x})')
        try:
            loader.write(offset, data, show, compress)
        except Unsupported:
            if not compress:
                raise
            compress = False    # this ROM wants plain writes: slower, same result
            loader.write(offset, data, show, compress)
        done += len(data)
    say(1, '확인 끝, 새 펌웨어로 시작하는 중')
    loader.hard_reset()


def nvs_region(table):
    """ESP-IDF partition table: 32-byte entries (magic AA 50, type, subtype, offset, size, label, flags)."""
    for i in range(0, len(table) - 31, 32):
        magic, kind, subtype, offset, size = struct.unpack_from('<HBBII', table, i)
        if magic != 0x50AA:
            break
        if kind == 1 and subtype == 2:   # data / nvs
            return offset, size
    return None
