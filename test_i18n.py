import ast
import json
from pathlib import Path
import re
from string import Formatter
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import app
import board_setup
from client import HeadsetClient
from i18n import EN, get_language, preferred_language, set_language, tr
from quality_dialog import show_quality
from audio_quality import QualitySettings


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.old_language=get_language()

    def tearDown(self):
        set_language(self.old_language)

    def test_catalog_coverage_and_format_fields(self):
        files=['app.py','board_setup.py','quality_dialog.py','board_status.py','client.py',
               'audio_quality.py','audio_format.py','board_link.py','firmware_bundle.py']
        for name in files:
            for node in ast.walk(ast.parse(Path(name).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr':
                    if node.args and isinstance(node.args[0],ast.Constant):
                        source=node.args[0].value
                        self.assertIn(source,EN,(name,source))
        fields=lambda text:sorted((name,spec,conversion) for _,name,spec,conversion in Formatter().parse(text) if name is not None)
        for source,english in EN.items():
            self.assertEqual(fields(source),fields(english),source)
            self.assertFalse(re.search('[가-힣]',english),source)

    def test_preference_and_retained_status(self):
        self.assertEqual(preferred_language({'language':'en'}),'en')
        with patch('i18n.locale.getlocale',return_value=('Korean_Korea','1252')):
            self.assertEqual(preferred_language({}),'ko')
        with patch('i18n.locale.getlocale',return_value=('de_DE','UTF-8')):
            self.assertEqual(preferred_language({'language':'invalid'}),'en')
        set_language('ko'); status=tr('보드 응답 대기')
        set_language('en');self.assertEqual(tr(status),'Waiting for board')
        # Values, including Korean device names and braces, must never be translated.
        self.assertIn('내 마이크 {test}',tr('AAC 처리 실패: {v0}',v0='내 마이크 {test}'))

    def test_live_switch_keeps_connection_gain_and_selection_and_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'settings.json'
            config.write_text(json.dumps({'language':'ko','host':'127.0.0.1','microphone_volume_percent':150}))
            with patch.object(app,'CONFIG',config),patch.object(app.App,'refresh'),patch.object(app.App,'poll'):
                root=tk.Tk();root.withdraw();ui=app.App(root)
                try:
                    ui.input.set('내 마이크');ui.output.set('Headphones')
                    client=HeadsetClient('127.0.0.1',None,None)
                    # No real connection/device is opened. active is a read-only property.
                    with patch.object(type(client),'active',new_callable=unittest.mock.PropertyMock,return_value=True):
                        ui.client=client;ui.controls()
                        client.status=tr('보드 응답 대기')
                        ui.language.set('English');ui.change_language()
                        self.assertIs(ui.client,client)
                        self.assertFalse(client.stop_event.is_set())
                        self.assertEqual(client.input_gain,1.5)
                        self.assertEqual(ui.input.get(),'내 마이크')
                        self.assertEqual(ui.button.cget('text'),'Disconnect')
                        self.assertEqual(ui.status.get(),'Waiting for board')
                        self.assertEqual(json.loads(config.read_text())['language'],'en')
                        ui.quality=QualitySettings('aac');client.quality=ui.quality
                        ui.update_display();root.update_idletasks()
                        self.assertLessEqual(root.winfo_reqheight(),760)
                        self.assertLessEqual(root.winfo_reqwidth(),700)
                        ui.language.set('한국어');ui.change_language()
                        self.assertEqual(ui.button.cget('text'),'연결 중지')
                        self.assertEqual(ui.status.get(),'보드 응답 대기')
                        ui.language.set('English');ui.change_language()
                finally:ui.client=None;ui.close()
                root=tk.Tk();root.withdraw();ui=app.App(root)
                try:self.assertEqual(ui.language.get(),'English')
                finally:ui.close()

    def test_english_setup_and_quality_windows_have_no_korean_captions(self):
        root=tk.Tk();root.withdraw()
        try:
            setup=board_setup.SetupWindow(root,probe=False,language='en')
            setup.apply({'firmware':'test','usb_mode':'apple','usb_mode_saved':'standard',
                         'wifi_ssid':'Home','wifi_connected':True,'router_ip':'192.168.0.14'})
            setup.show();root.update_idletasks()
            self.assertEqual(setup.mode.get(),'Standard · Windows compatible')
            self.assertIn('192.168.0.14',setup.router.get())
            self.assertLessEqual(root.winfo_reqwidth(),760)
            self.assertLessEqual(root.winfo_reqheight(),800)
            def texts(widget):
                for option in ['text','textvariable','values']:
                    if option in widget.keys():
                        value=widget.cget(option)
                        if option=='textvariable':value=widget.getvar(value) if value else ''
                        self.assertFalse(re.search('[가-힣]',str(value)),str(value))
                for child in widget.winfo_children():texts(child)
            texts(root)
            show_quality(root,QualitySettings('aac'),False,lambda value:None)
            root.update_idletasks();texts(root)
        finally:root.destroy()


if __name__=='__main__':unittest.main()
