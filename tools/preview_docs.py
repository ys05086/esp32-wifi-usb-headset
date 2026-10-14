"""Open the real UI with example data for documentation screenshots.

python tools/preview_docs.py --view app --language en
python tools/preview_docs.py --view setup --language ko

No audio devices, network or COM ports are opened. Real settings are not read or
written. Capture the resulting window with a window screenshot tool, then close it.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app
import board_setup
from client import HeadsetClient
from i18n import tr


def show_app(root, language, config):
    def devices(ui):
        microphone = 'Microphone' if language == 'en' else '마이크'
        headphones = 'Headphones' if language == 'en' else '헤드폰'
        ui.inputs = {f'{microphone} (USB Audio Device) · Windows WASAPI': 0}
        ui.outputs = {f'{headphones} (USB Audio Device) · Windows WASAPI': 1}
        for widget, choices in [(ui.input, ui.inputs), (ui.output, ui.outputs)]:
            widget['values'] = list(choices)
            widget.set(next(iter(choices)))

    with patch.object(app, 'CONFIG', config), patch.object(app.App, 'refresh', devices), patch.object(app.App, 'poll'):
        ui = app.App(root)
        client = HeadsetClient('192.168.0.50', None, None)
        client.thread = SimpleNamespace(is_alive=lambda: True)
        client.status = tr('양방향 연결됨 · 기기 소리는 선택한 출력으로 재생')
        client.sent, client.board_received, client.returns.received = 36012, 36008, 35987
        client.returns.blocks = {n: bytes(960) for n in range(8)}
        client.listening.linked, client.listening.phone_sets = True, True
        client.listening.db, client.listening.changes = -17.5, 1
        client.level.rate = 4 * 48000 / 1e6
        ui.client = client
        ui.board.data = {'usb_mode': 'adaptive'}
        ui.update_display()
        # The screenshot is a display fixture; no controls may start real work.
        for widget in walk(root):
            if 'command' in widget.keys():widget.configure(command=lambda: None)
        ui.language_picker.unbind('<<ComboboxSelected>>')
        root.protocol('WM_DELETE_WINDOW', root.destroy)
        root.title('ESP32 Audio Bridge · ' + ('Documentation preview' if language == 'en' else '문서 미리보기'))
        root.mainloop()


def walk(widget):
    yield widget
    for child in widget.winfo_children():yield from walk(child)


def show_setup(root, language):
    with patch.object(board_setup.SetupWindow, 'poll'), patch.object(board_setup.firmware_bundle, 'load', return_value=None):
        ui = board_setup.SetupWindow(root, probe=False, language=language)
        ui.bundle = SimpleNamespace(version='6c13a6a', folder=board_setup.firmware_bundle.default_folder())
        port = 'COM5 · CH34x'
        ui.ports = {port: 'COM5'}
        ui.port['values'] = [port]; ui.port.set(port)
        ui.port.unbind('<<ComboboxSelected>>')
        ui.apply({'firmware':'6c13a6a','ap_ssid':'ESP32-Headset-1A2B','ap_password':'abcd-efgh-jkmn',
                  'wifi_ssid':'MyHomeWiFi','wifi_connected':True,'router_ip':'192.168.0.50',
                  'usb_mode':'adaptive','usb_mode_saved':'adaptive'})
        ui.show()
        for widget in walk(root):
            if 'command' in widget.keys():widget.configure(command=lambda: None)
        root.title(str(tr('ESP32 보드 설정')) + ' · ' + ('Documentation preview' if language == 'en' else '문서 미리보기'))
        root.mainloop()


def main(default_view=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--view',choices=['app','setup'],default=default_view or 'app')
    parser.add_argument('--language',choices=['en','ko'],default='en')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='esp32-doc-preview-') as folder:
        config=Path(folder)/'settings.json'
        config.write_text(json.dumps({'language':args.language,'host':'192.168.0.50'}),encoding='utf-8')
        root=tk.Tk()
        if args.view=='app':show_app(root,args.language,config)
        else:show_setup(root,args.language)


if __name__=='__main__':main()
