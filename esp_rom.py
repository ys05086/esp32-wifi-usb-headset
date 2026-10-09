"""Writes firmware through the ESP32-S3's own ROM download mode, over the board's COM (USB-serial) port.

Only what this board needs: the DTR/RTS reset into download mode, SYNC, attaching the SPI flash,
compressed writes that the ROM inflates, an MD5 read-back of every region, and a reset into the new firmware.
It talks to the chip's ROM loader directly (Espressif's documented serial protocol) and uploads no flasher stub.
"""
import hashlib
import struct
import time
import zlib

SLIP_END, SLIP_ESC = 0xC0, 0xDB
FLASH_BEGIN, FLASH_DATA = 0x02, 0x03
SYNC, READ_REG, SPI_SET_PARAMS, SPI_ATTACH, CHANGE_BAUD = 0x08, 0x0A, 0x0B, 0x0D, 0x0F
DEFL_BEGIN, DEFL_DATA, FLASH_MD5, SECURITY_INFO = 0x10, 0x11, 0x13, 0x14
BLOCK = 0x400                       # the ROM loader's write block
SECTOR = 0x1000
ESP32S3_CHIP_ID = 9                 # in the security info (ESP32-S3 and later)
CHIP_MAGIC_REG = 0x40001000         # the older way: a ROM word that differs per chip (also 9 on the S3)


class RomError(Exception):
    pass


class Unsupported(RomError):
    """The ROM refused a compressed write: write plainly instead."""


def slip_encode(packet):
    out = bytearray([SLIP_END])
    for b in packet:
        out += b'\xdb\xdc' if b == SLIP_END else b'\xdb\xdd' if b == SLIP_ESC else bytes([b])
    out.append(SLIP_END)
    return bytes(out)


class SlipReader:
    """SLIP frames out of a byte stream; text between frames (the boot log) is skipped."""
    def __init__(self):
        self.frame, self.escape = None, False

    def feed(self, data):
        frames = []
        for b in data:
            if self.frame is None:
                if b == SLIP_END:
                    self.frame = bytearray()
                continue
            if self.escape:
                self.escape = False
                if b in (0xDC, 0xDD):
                    self.frame.append(SLIP_END if b == 0xDC else SLIP_ESC)
                else:
                    self.frame = None   # broken frame: wait for the next start
            elif b == SLIP_ESC:
                self.escape = True
            elif b == SLIP_END:
                if self.frame:
                    frames.append(bytes(self.frame))
                    self.frame = None
            else:
                self.frame.append(b)
        return frames


def checksum(data):
    value = 0xEF
    for b in data:
        value ^= b
    return value


def per_mb(seconds, size, least=3.0):
    return max(least, seconds * size / 1e6)


class RomLoader:
    """`port` is an open pyserial-like port (read, write, in_waiting, timeout, baudrate, dtr, rts,
    reset_input_buffer)."""
    def __init__(self, port, sleep=time.sleep, clock=time.monotonic):
        self.port, self.sleep, self.clock = port, sleep, clock
        self.reader, self.pending = SlipReader(), []

    # --- lines and packets

    def _lines(self, dtr=None, rts=None):
        # DTR first: IO0 must already be low when RTS lets EN rise.
        if dtr is not None:
            self.port.dtr = dtr
        if rts is not None:
            self.port.rts = rts
            # Windows' usbser.sys only sends RTS together with a DTR change: restate DTR.
            self.port.dtr = self.port.dtr

    def _flush(self):
        self.port.reset_input_buffer()
        self.reader, self.pending = SlipReader(), []

    def _send(self, op, data=b'', check=0):
        self.port.write(slip_encode(struct.pack('<BBHI', 0, op, len(data), check) + data))

    def _response(self, op, timeout):
        deadline = self.clock() + timeout
        while True:
            while self.pending:
                frame = self.pending.pop(0)
                if len(frame) < 8:
                    continue
                direction, got, size, value = struct.unpack_from('<BBHI', frame)
                if direction == 1 and got == op and len(frame) >= 8 + size:
                    return value, frame[8:8 + size]
            left = deadline - self.clock()
            if left <= 0:
                raise RomError(f'no answer to ROM command 0x{op:02x}')
            self.port.timeout = min(left, 0.05)
            data = self.port.read(max(1, self.port.in_waiting))
            if data:
                self.pending += self.reader.feed(data)

    def command(self, op, data=b'', check=0, timeout=3.0, result=0):
        """Sends one command; returns (value, the first `result` bytes of data). The status bytes follow
        the result (two or four, by ROM): the first is 0 on success, the second the reason."""
        self._send(op, data, check)
        value, payload = self._response(op, timeout)
        status = payload[result:]
        if len(status) < 2:
            raise RomError(f'short answer to ROM command 0x{op:02x}')
        if status[0]:
            raise RomError(f'ROM command 0x{op:02x} failed (reason 0x{status[1]:02x})')
        return value, payload[:result]

    # --- steps

    def enter_download_mode(self):
        # The board's transistor pair: RTS low pulls EN (reset), DTR low pulls IO0 (download mode).
        self._lines(dtr=False, rts=True)
        self.sleep(0.1)
        self._lines(dtr=True, rts=False)
        self.sleep(0.05)
        self._lines(dtr=False)

    def connect(self, attempts=4, reset=True):
        """Resets into download mode and syncs. reset=False when the user held BOOT and pressed RESET."""
        for attempt in range(attempts):
            if reset:
                self.enter_download_mode()
            self.sleep(0.05)
            self._flush()
            for _ in range(5):
                try:
                    self._send(SYNC, b'\x07\x07\x12\x20' + b'\x55' * 32)
                    self._response(SYNC, 0.1)
                except RomError:
                    continue
                for _ in range(7):   # the ROM answers one SYNC several times
                    try:
                        self._response(SYNC, 0.1)
                    except RomError:
                        break
                chip = self.chip_id()
                if chip != ESP32S3_CHIP_ID:
                    raise RomError(f'this is not an ESP32-S3 (chip id {chip})')
                return
        raise RomError('the board did not enter download mode')

    def chip_id(self):
        try:
            # flags, flash_crypt_cnt, 7 key purposes, chip id, API version
            _, info = self.command(SECURITY_INFO, result=20)
            return struct.unpack_from('<I', info, 12)[0]
        except RomError:
            self._flush()
            return self.command(READ_REG, struct.pack('<I', CHIP_MAGIC_REG))[0]

    def change_baud(self, baud):
        self.command(CHANGE_BAUD, struct.pack('<II', baud, 0))
        self.port.baudrate = baud
        self.sleep(0.05)
        self._flush()
        self.chip_id()   # still talking at the new speed

    def attach_flash(self, size):
        self.command(SPI_ATTACH, struct.pack('<IBBBB', 0, 0, 0, 0, 0))
        self.command(SPI_SET_PARAMS, struct.pack('<IIIIII', 0, size, 0x10000, SECTOR, 0x100, 0xFFFF))

    def md5(self, offset, size):
        _, digest = self.command(FLASH_MD5, struct.pack('<IIII', offset, size, 0, 0),
                                 timeout=per_mb(8, size), result=32)
        return digest.decode('ascii').lower()

    def write(self, offset, data, progress=None, compress=True):
        """Writes `data` at `offset` (sector aligned), compressed unless told not to, then checks it by MD5.
        The ROM erases the region up front; the last field of each begin means "not encrypted"."""
        if offset % SECTOR:
            raise ValueError('flash offset must be sector aligned')
        size = (len(data) + BLOCK - 1) // BLOCK * BLOCK
        if compress:
            packed = zlib.compress(data, 9)
            blocks = (len(packed) + BLOCK - 1) // BLOCK
            try:
                self.command(DEFL_BEGIN, struct.pack('<IIIII', size, blocks, BLOCK, offset, 0),
                             timeout=per_mb(30, size))
            except RomError as error:
                raise Unsupported(str(error)) from error
            inflate = zlib.decompressobj()
            for seq in range(blocks):
                block = packed[seq * BLOCK:(seq + 1) * BLOCK]
                written = len(inflate.decompress(block))
                self.command(DEFL_DATA, struct.pack('<IIII', len(block), seq, 0, 0) + block,
                             check=checksum(block), timeout=per_mb(40, written))
                if progress:
                    progress((seq + 1) / blocks)
        else:
            blocks = size // BLOCK
            self.command(FLASH_BEGIN, struct.pack('<IIIII', len(data), blocks, BLOCK, offset, 0),
                         timeout=per_mb(30, size))
            for seq in range(blocks):
                block = data[seq * BLOCK:(seq + 1) * BLOCK].ljust(BLOCK, b'\xff')
                self.command(FLASH_DATA, struct.pack('<IIII', BLOCK, seq, 0, 0) + block,
                             check=checksum(block), timeout=per_mb(40, BLOCK))
                if progress:
                    progress((seq + 1) / blocks)
        if self.md5(offset, len(data)) != hashlib.md5(data).hexdigest():
            raise RomError(f'verify failed at 0x{offset:x}')

    def hard_reset(self):
        """Out of download mode, into the firmware (IO0 released, EN pulsed)."""
        self._lines(dtr=False, rts=True)
        self.sleep(0.1)
        self._lines(rts=False)
