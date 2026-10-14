import json
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from audio_quality import QualitySettings
from client import HeadsetClient
from microphone_level import GainRamp, microphone_percent


class MicrophoneTests(unittest.TestCase):
    def test_saved_percent_is_bounded_and_invalid_values_use_unity(self):
        for invalid in [None, {}, 'bad', float('nan'), float('inf')]:
            self.assertEqual(microphone_percent(invalid), 100)
        self.assertEqual(microphone_percent(-20), 0)
        self.assertEqual(microphone_percent(500), 200)
        self.assertEqual(microphone_percent(150), 150)

    def test_ramp_is_ten_ms_across_callback_sizes_and_rates(self):
        for rate in [16000, 44100, 48000, 96000]:
            total=round(rate*.01)
            ramp=GainRamp()
            chunks=[total//3, total-total//3]
            actual=np.concatenate([ramp.apply(np.ones(n),2,rate) for n in chunks])
            np.testing.assert_allclose(actual,1+np.arange(1,total+1)/total)
            self.assertEqual(ramp.current,2)
            np.testing.assert_array_equal(ramp.apply(np.ones(17),2,rate),np.full(17,2))
            # Retargeting starts from the current level, without an instantaneous jump.
            falling=ramp.apply(np.ones(total//2),0,rate)
            rising=ramp.apply(np.ones(total),1.5,rate)
            self.assertLess(abs(rising[0]-falling[-1]),.02)

    def test_capture_scales_pcm_and_aac_input_without_changing_listening(self):
        source=np.full((480,2),12000,dtype=np.int16)
        for mode in ['pcm','aac']:
            for gain,expected in [(0,0),(.5,6000),(1,12000),(2,24000)]:
                with self.subTest(mode=mode,gain=gain):
                    c=HeadsetClient('127.0.0.1',None,None,quality=QualitySettings(mode))
                    c.input_gain=gain;c.microphone_ramp=GainRamp(gain)
                    c.capture(source,480,None,None)
                    np.testing.assert_array_equal(np.frombuffer(c.captured.get_nowait(),dtype='<i2'),np.full(480,expected))
                    self.assertEqual(c.output_gain,1)
                    c.mic_muted=True;c.capture(source,480,None,None)
                    self.assertEqual(c.captured.get_nowait(),bytes(960))

    def test_boost_saturates_without_integer_wrap_and_counts_overrange(self):
        c=HeadsetClient('127.0.0.1',None,None)
        c.input_gain=2;c.microphone_ramp=GainRamp(2)
        source=np.tile(np.array([30000,-30000,1000,-1000],dtype=np.int16),120)
        c.capture(source[:,None],480,None,None)
        expected=np.clip(source.astype(np.int32)*2,-32768,32767).astype('<i2')
        self.assertEqual(c.captured.get_nowait(),expected.tobytes())
        self.assertEqual(c.input_clipped_samples,240)

    def test_ui_applies_saves_restores_and_resets_microphone_volume(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'settings.json'
            config.write_text(json.dumps({'host':'127.0.0.1','other_setting':'preserved'}))
            with patch.object(app,'CONFIG',config),patch.object(app.App,'refresh'),patch.object(app.App,'poll'):
                root=tk.Tk();root.withdraw()
                ui=app.App(root)
                try:
                    self.assertEqual(ui.mic_volume.get(),100)
                    ui.client=SimpleNamespace()
                    ui.mic_volume.set(150);ui.microphone_volume_moved()
                    self.assertEqual(ui.client.input_gain,1.5)
                    self.assertEqual(ui.client.output_gain,.8)
                    ui.save_microphone_volume()
                    saved=json.loads(config.read_text())
                    self.assertEqual(saved['microphone_volume_percent'],150)
                    self.assertEqual(saved['other_setting'],'preserved')
                finally:
                    ui.client=None;ui.close()
                root=tk.Tk();root.withdraw();ui=app.App(root)
                try:
                    self.assertEqual(ui.mic_volume.get(),150)
                    ui.reset_microphone_volume()
                    # Closing before the debounce interval must still save the new value.
                finally:ui.close()
                self.assertEqual(json.loads(config.read_text())['microphone_volume_percent'],100)


if __name__=='__main__':unittest.main()
