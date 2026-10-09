"""Saves a screenshot of the ESP32 보드 설정 window for the README: the real window after reading a board,
filled with an example board (name, password in the generated format, router), never a real one. No COM port
is opened. Windows only.

  python tools/screenshot_setup.py docs/images/board-setup.png
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import tkinter as tk

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import board_setup  # noqa: E402

board_setup.SetupWindow.poll = lambda self: None   # no background work: only the values set below

root = tk.Tk()
root.geometry('660x760+80+60')
ui = board_setup.SetupWindow(root, probe=False)
port = 'COM5 · CH34x'
ui.ports = {port: 'COM5'}
ui.port['values'] = [port]
ui.port.set(port)
ui.apply({'firmware': '6c13a6a', 'ap_ssid': 'ESP32-Headset-1A2B', 'ap_password': 'abcd-efgh-jkmn',
          'wifi_ssid': 'MyHomeWiFi', 'wifi_connected': True, 'router_ip': '192.168.0.50',
          'usb_mode': 'adaptive', 'usb_mode_saved': 'adaptive'})
ui.show()
ui.versions.set('설치할 펌웨어: 6c13a6a (이 프로그램에 든 것) · 지금 보드: 6c13a6a')
ui.install_button.configure(state='normal')
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
