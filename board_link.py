"""The board's setup commands over its COM port (the USB-serial chip, not the audio USB port).

The firmware answers "@get", "@set {json}", "@new-password" and "@reboot" with one "@ok {json}" or
"@err message" line; everything else on the port is its log. Opening the port must not reset the board,
so DTR and RTS stay released (on these boards they drive EN and IO0).
"""
import json
import time

# USB-serial chips found on ESP32-S3 boards: WCH CH34x, Silicon Labs CP210x, FTDI, and the S3's own
# USB serial (present only in download mode with this firmware, which uses the native port for audio).
KNOWN_VIDS = {0x1A86: 'CH34x', 0x10C4: 'CP210x', 0x0403: 'FTDI', 0x303A: 'ESP32-S3'}


class BoardError(Exception):
    pass


def ap_password_problem(text):
    """None if the board takes `text` as its own Wi-Fi password (WPA2: 8-63 printable ASCII), else why not."""
    if text != text.strip():
        return '앞뒤 공백은 빼 주세요. 휴대폰에서 칠 때 헷갈려요.'
    if not 8 <= len(text) <= 63:
        return '8~63자로 정하세요.'
    if any(not ' ' <= c <= '~' for c in text):
        return '영문, 숫자, 기호만 쓸 수 있어요 (한글·이모지는 Wi-Fi 비밀번호에 못 써요).'
    return None


def open_port(name, baud=115200):
    import serial
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = name, baud, 0.05
    port.dtr = port.rts = False
    port.open()
    return port


def list_ports():
    """[(device, label, known)], the likely boards first; known: a USB-serial chip ESP32 boards use."""
    from serial.tools import list_ports as lp
    found = []
    for p in lp.comports():
        chip = KNOWN_VIDS.get(p.vid)
        label = f'{p.device} · {chip or p.description}'
        found.append((chip is None, p.device, label))
    return [(device, label, not unknown) for unknown, device, label in sorted(found)]


class BoardLink:
    def __init__(self, port, clock=time.monotonic):
        self.port, self.clock = port, clock
        self.log = []    # recent log lines from the board, for the window

    def command(self, text, timeout=2.0):
        self.port.reset_input_buffer()
        # The newline first: a command counts only at the start of a line.
        self.port.write(b'\n@' + text.encode('utf-8') + b'\n')
        deadline, buffer = self.clock() + timeout, b''
        while self.clock() < deadline:
            buffer += self.port.read(max(1, self.port.in_waiting))
            while b'\n' in buffer:
                raw, buffer = buffer.split(b'\n', 1)
                line = raw.decode('utf-8', 'replace').strip()
                if line.startswith('@ok '):
                    return json.loads(line[4:])
                if line.startswith('@err '):
                    raise BoardError(line[5:])
                if line:
                    self.log = (self.log + [line])[-20:]
        # Firmware without setup commands took the 't' in the line as its probe-tone key: stop that tone.
        self.port.write(b's')
        raise BoardError('보드가 답하지 않아요')

    def get(self):
        state = self.command('get')
        if state.get('board') != 'esp32-wifi-usb-headset':
            raise BoardError('이 펌웨어의 보드가 아니에요')
        return state

    def set(self, **fields):
        return self.command('set ' + json.dumps(fields, ensure_ascii=False, separators=(',', ':')), timeout=5)

    def new_password(self):
        return self.command('new-password', timeout=5)

    def close(self):
        self.port.close()
