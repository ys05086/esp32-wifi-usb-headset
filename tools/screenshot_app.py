"""Saves a screenshot of the ESP32 Audio Bridge window for the README: the real window, as it looks while
connected, with example values in place of this PC's board address and audio devices. Nothing connects or
sends, settings.json is not written, and the board is not asked for its status. Windows only.

  python tools/screenshot_app.py docs/images/audio-bridge.png
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import tkinter as tk

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as bridge  # noqa: E402
from protocol import slider_position  # noqa: E402

bridge.App.poll = lambda self: None   # no board queries and no live state: only the values set below

root = tk.Tk()
root.geometry('700x760+80+60')
ui = bridge.App(root)
ui.host.set('192.168.0.50')
ui.input.set('마이크 (USB Audio Device) · Windows WASAPI')
ui.output.set('헤드폰 (USB Audio Device) · Windows WASAPI')
ui.usb_mode.set('현재 USB 모드 · Adaptive · 피드백 없음 (실험)')
ui.volume.set(slider_position(-17.5))
ui.volume_label.set('듣기 크기 · -17.5 dB · 폰 볼륨')
# As the window looks while connected (App.poll): settings locked, the stop button, a few minutes of counters.
ui.button.configure(text='연결 중지')
ui.host_entry.configure(state='disabled')
ui.buffer.configure(state='disabled')
for widget in (ui.input, ui.output):
    widget.configure(state='disabled')
ui.refresh_button.configure(state='disabled')
ui.status.set('양방향 연결됨 · 기기 소리는 선택한 출력으로 재생')
ui.stats.set('입력 48000 Hz → 전송 48000 Hz → 출력 48000 Hz\n송신: 보냄 36012 · 보드 수신 36008 · 보드 버퍼 부족 0\n'
             '듣기: 수신 35987 · 버퍼 80 ms · 누락 0\n듣기 버퍼 부족 0 · 출력 장치 오류 0 · 입력 버림 0\n'
             '듣기 속도 보정 +4 ppm (−0/+0 프레임)')
root.attributes('-topmost', True)
root.lift()
for _ in range(5):
    root.update()
    time.sleep(.1)

# The window's visible bounds, without the invisible resize border Windows 10/11 adds around it.
frame = wintypes.HWND(int(root.wm_frame(), 16))
rect = wintypes.RECT()
ctypes.windll.dwmapi.DwmGetWindowAttribute(frame, 9, ctypes.byref(rect), ctypes.sizeof(rect))  # extended frame bounds
image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
image.save(out, optimize=True)
print(out, image.size)
root.destroy()
