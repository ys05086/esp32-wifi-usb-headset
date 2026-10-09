import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import esp_rom
import firmware_bundle
from board_link import BoardError, BoardLink
from esp_rom import RomError, RomLoader, SlipReader, slip_encode


class Port:
    """The pyserial surface the code uses; subclasses answer what is written."""
    def __init__(self):
        self.out = bytearray()
        self.timeout, self.baudrate = 0.05, 115200
        self._dtr = self._rts = False
        self.lines = []

    @property
    def dtr(self): return self._dtr

    @dtr.setter
    def dtr(self, value): self._dtr = value; self.lines.append(('dtr', value)); self.changed()

    @property
    def rts(self): return self._rts

    @rts.setter
    def rts(self, value):
        falling = self._rts and not value
        self._rts = value; self.lines.append(('rts', value))
        if falling:
            self.released()
        self.changed()

    def changed(self): pass
    def released(self): pass

    @property
    def in_waiting(self): return len(self.out)

    def read(self, n):
        data = bytes(self.out[:n]); del self.out[:n]
        return data

    def reset_input_buffer(self): self.out.clear()
    def close(self): pass


class FakeRom(Port):
    """An ESP32-S3 in ROM download mode, as far as the protocol goes."""
    def __init__(self, chip=esp_rom.ESP32S3_CHIP_ID, flash_size=2 << 20, status_bytes=4, deflate=True):
        super().__init__()
        self.chip, self.status_bytes, self.deflate = chip, status_bytes, deflate
        self.flash = bytearray(b'\xff' * flash_size)
        self.mode = 'firmware'
        self.reader = SlipReader()
        self.fail_data_at = None
        self.corrupt = False
        self.bauds, self.params = [], None
        self.inflate = self.cursor = self.expected = None

    def released(self):
        # EN rises: IO0 (DTR) low means download mode, else the firmware boots.
        self.mode = 'download' if self.dtr else 'firmware'
        self.out += b'ESP-ROM:esp32s3-20210327\r\nwaiting for download\r\n' if self.dtr else b'I (31) boot: ESP-IDF\r\n'

    def reply(self, op, value=0, data=b'', ok=True, reason=0):
        status = bytes([0 if ok else 1, reason]) + bytes(self.status_bytes - 2)
        payload = data + status
        self.out += slip_encode(struct.pack('<BBHI', 1, op, len(payload), value) + payload)

    def write(self, data):
        for frame in self.reader.feed(data):
            if self.mode == 'download':
                self.handle(frame)
        return len(data)

    def handle(self, frame):
        _, op, size, check = struct.unpack_from('<BBHI', frame)
        body = frame[8:8 + size]
        if op == esp_rom.SYNC:
            for _ in range(8):
                self.reply(op, 0x20120707)
        elif op == esp_rom.SECURITY_INFO:
            self.reply(op, data=struct.pack('<IB7BII', 0, 0, *bytes(7), self.chip, 0))
        elif op == esp_rom.READ_REG:
            (address,) = struct.unpack('<I', body)
            self.reply(op, self.chip if address == esp_rom.CHIP_MAGIC_REG else 0)
        elif op == esp_rom.SPI_ATTACH:
            assert len(body) == 8, 'the ROM takes 8 bytes here'
            self.reply(op)
        elif op == esp_rom.SPI_SET_PARAMS:
            self.params = struct.unpack('<IIIIII', body); self.reply(op)
        elif op == esp_rom.CHANGE_BAUD:
            self.bauds.append(struct.unpack('<II', body)); self.reply(op)
        elif op in (esp_rom.DEFL_BEGIN, esp_rom.FLASH_BEGIN):
            if op == esp_rom.DEFL_BEGIN and not self.deflate:
                self.reply(op, ok=False, reason=0x05); return
            erase, blocks, block, offset, encrypted = struct.unpack('<IIIII', body)
            assert block == esp_rom.BLOCK and encrypted == 0
            erase = (erase + esp_rom.SECTOR - 1) // esp_rom.SECTOR * esp_rom.SECTOR   # whole sectors
            self.flash[offset:offset + erase] = b'\xff' * erase
            self.inflate = zlib.decompressobj() if op == esp_rom.DEFL_BEGIN else None
            self.cursor, self.expected = offset, 0
            self.reply(op)
        elif op in (esp_rom.DEFL_DATA, esp_rom.FLASH_DATA):
            length, seq, _, _ = struct.unpack_from('<IIII', body)
            block = body[16:16 + length]
            assert seq == self.expected and check == esp_rom.checksum(block)
            self.expected += 1
            if self.fail_data_at == seq:
                self.reply(op, ok=False, reason=0x63); return
            out = self.inflate.decompress(block) if self.inflate else block
            self.flash[self.cursor:self.cursor + len(out)] = out
            self.cursor += len(out)
            self.reply(op)
        elif op == esp_rom.FLASH_MD5:
            offset, length, _, _ = struct.unpack('<IIII', body)
            region = bytearray(self.flash[offset:offset + length])
            if self.corrupt and region:
                region[0] ^= 1
            self.reply(op, data=hashlib.md5(region).hexdigest().encode())
        else:
            self.reply(op, ok=False, reason=0x05)


def partition_table(nvs=(0x9000, 0x6000), app=(0x10000, 0x100000)):
    entry = lambda kind, sub, offset, size, label: struct.pack('<HBBII16sI', 0x50AA, kind, sub, offset, size, label, 0)
    return (entry(1, 2, *nvs, b'nvs') + entry(1, 1, 0xF000, 0x1000, b'phy_init') + entry(0, 0, *app, b'factory')
            + b'\xff' * 32)


def make_bundle(folder, app=None):
    folder = Path(folder)
    images = {'bootloader': (0, bytes(range(256)) * 80), 'partition-table': (0x8000, partition_table()),
              'app': (0x10000, app if app is not None else bytes((i * 7919) % 251 for i in range(300_000)))}
    files = []
    for name, (offset, data) in images.items():
        (folder / f'{name}.bin').write_bytes(data)
        files.append({'name': name, 'offset': offset, 'file': f'{name}.bin', 'sha256': hashlib.sha256(data).hexdigest()})
    (folder / 'manifest.json').write_text(json.dumps({'board': firmware_bundle.BOARD, 'version': 'abc1234',
                                                      'chip': 'esp32s3', 'flash_size': '2MB', 'files': files}))
    return images


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): self.t += 0.01; return self.t


def loader(port):
    return RomLoader(port, sleep=lambda s: None, clock=Clock())


class SlipTests(unittest.TestCase):
    def test_escapes_and_noise_between_frames(self):
        packet = bytes([1, 0xC0, 2, 0xDB, 3])
        encoded = slip_encode(packet)
        self.assertEqual(encoded, b'\xc0\x01\xdb\xdc\x02\xdb\xdd\x03\xc0')
        reader = SlipReader()
        frames = reader.feed(b'boot log\r\n' + encoded[:4]) + reader.feed(encoded[4:] + b'more' + encoded)
        self.assertEqual(frames, [packet, packet])


class FlashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.images = make_bundle(self.temp.name)
        self.bundle = firmware_bundle.load(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_install_writes_each_image_keeps_settings_and_boots(self):
        rom = FakeRom()
        rom.flash[0x9000:0x9008] = b'settings'
        steps = []
        firmware_bundle.install(rom, self.bundle, progress=lambda f, text: steps.append(f),
                                loader=loader(rom))
        for name, (offset, data) in self.images.items():
            self.assertEqual(bytes(rom.flash[offset:offset + len(data)]), data, name)
        self.assertEqual(bytes(rom.flash[0x9000:0x9008]), b'settings')
        self.assertEqual(rom.mode, 'firmware')                    # reset into the new firmware
        self.assertEqual(rom.bauds, [(460800, 0)])
        self.assertEqual(rom.params[1], 2 << 20)
        self.assertEqual(steps[-1], 1)
        self.assertEqual(steps, sorted(steps))

    def test_reset_settings_blanks_nvs(self):
        rom = FakeRom()
        rom.flash[0x9000:0x9008] = b'settings'
        self.assertEqual(self.bundle.nvs, (0x9000, 0x6000))
        firmware_bundle.install(rom, self.bundle, reset_settings=True, loader=loader(rom))
        self.assertEqual(bytes(rom.flash[0x9000:0xF000]), b'\xff' * 0x6000)

    def test_download_mode_needs_io0_low_when_en_rises(self):
        rom = FakeRom()
        l = loader(rom)
        l.connect()
        self.assertEqual(rom.mode, 'download')
        # DTR is set before RTS falls, and every RTS change is followed by a DTR restatement
        falls = [i for i, (line, value) in enumerate(rom.lines) if line == 'rts' and value is False]
        self.assertTrue(all(rom.lines[i + 1][0] == 'dtr' for i in falls))
        self.assertTrue(rom.lines[falls[0] - 1] == ('dtr', True))
        l.hard_reset()
        self.assertEqual(rom.mode, 'firmware')

    def test_two_byte_status_and_failures(self):
        rom = FakeRom(status_bytes=2)
        l = loader(rom); l.connect(); l.attach_flash(2 << 20)
        l.write(0x20000, b'x' * 5000)
        rom.fail_data_at = 0
        with self.assertRaisesRegex(RomError, 'reason 0x63'):
            l.write(0x20000, b'y' * 5000)
        rom.fail_data_at, rom.corrupt = None, True
        with self.assertRaisesRegex(RomError, 'verify failed'):
            l.write(0x20000, b'z' * 5000)

    def test_refuses_other_chips_and_silent_ports(self):
        with self.assertRaisesRegex(RomError, 'not an ESP32-S3'):
            loader(FakeRom(chip=5)).connect()
        silent = FakeRom()
        silent.released = lambda: None                            # never enters download mode
        with self.assertRaisesRegex(RomError, 'did not enter download mode'):
            loader(silent).connect(attempts=2)

    def test_plain_writes_when_the_rom_will_not_inflate(self):
        rom = FakeRom(deflate=False)
        firmware_bundle.install(rom, self.bundle, loader=loader(rom))
        for name, (offset, data) in self.images.items():
            self.assertEqual(bytes(rom.flash[offset:offset + len(data)]), data, name)

    def test_damaged_bundle_is_refused(self):
        app = Path(self.temp.name) / 'app.bin'
        app.write_bytes(app.read_bytes()[:-1] + b'!')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            firmware_bundle.load(self.temp.name)


class FakeBoard(Port):
    """The firmware's COM side: log lines, and one answer per '@' command."""
    def __init__(self):
        super().__init__()
        self.state = {'board': 'esp32-wifi-usb-headset', 'firmware': 'abc1234', 'ap_ssid': 'ESP32-Headset-1A2B',
                      'ap_password': 'abcd-efgh-jkmn', 'wifi_ssid': '', 'usb_mode': 'standard'}
        self.received = b''
        self.commands = []

    def write(self, data):
        self.received += data
        while b'\n' in self.received:
            line, self.received = self.received.split(b'\n', 1)
            if not line.startswith(b'@'):
                continue
            text = line[1:].decode()
            self.commands.append(text)
            self.out += b'I (5012) wifi_pcm: ROUTER IP: 192.168.0.14\r\n'
            if text == 'get':
                self.out += b'@ok ' + json.dumps(self.state).encode() + b'\r\n'
            elif text.startswith('set '):
                self.state.update(json.loads(text[4:]))
                self.out += b'@ok ' + json.dumps(self.state).encode() + b'\r\n'
            else:
                self.out += b'@err unknown command; try @help\r\n'
        return len(data)


class LinkTests(unittest.TestCase):
    def test_get_and_set_through_the_log(self):
        board = FakeBoard()
        link = BoardLink(board, clock=Clock())
        self.assertEqual(link.get()['ap_ssid'], 'ESP32-Headset-1A2B')
        state = link.set(wifi_ssid='우리집 2.4G', wifi_password='12345678')
        self.assertEqual(state['wifi_ssid'], '우리집 2.4G')
        self.assertEqual(board.commands[-1], 'set {"wifi_ssid":"우리집 2.4G","wifi_password":"12345678"}')
        self.assertIn('ROUTER IP: 192.168.0.14', link.log[-1])

    def test_errors_and_silence(self):
        board = FakeBoard()
        link = BoardLink(board, clock=Clock())
        with self.assertRaisesRegex(BoardError, 'unknown command'):
            link.command('nope')
        sent = []
        board.write = lambda data: sent.append(data) or len(data)   # old firmware: no answer
        with self.assertRaises(BoardError):
            link.get()
        self.assertEqual(sent[-1], b's')                              # its probe tone, started by 't', is stopped


if __name__ == '__main__':
    unittest.main()
