import unittest
from unittest.mock import patch
import numpy as np
import sounddevice as sd
from audio_format import PCMConverter, endpoint_format


class FormatTests(unittest.TestCase):
    def test_native_rate_fallback(self):
        def check(**options):
            if options['samplerate'] != 96000:
                raise sd.PortAudioError('Invalid sample rate', -9997)
        info = dict(max_input_channels=1, default_samplerate=96000, name='Capture')
        with patch.object(sd, 'query_devices', return_value=info), patch.object(sd, 'check_input_settings', side_effect=check):
            self.assertEqual(endpoint_format(3, 'input'), (96000, 1))

    def test_arbitrary_blocks_keep_exact_pcm_at_48k(self):
        converter = PCMConverter(48000, 48000)
        source = np.arange(1920, dtype=np.int16)
        for chunk in np.array_split(source, 7): converter.push(chunk)
        result = np.concatenate([converter.pop(480) for _ in range(4)])
        np.testing.assert_array_equal(result, source)
        self.assertIsNone(converter.pop(1))

    def test_conversion_is_independent_of_callback_boundaries(self):
        for source_rate, target_rate in [(96000, 48000), (44100, 48000), (48000, 44100), (48000, 96000)]:
            with self.subTest(rates=(source_rate, target_rate)):
                wave = (10000 * np.sin(2 * np.pi * 1000 * np.arange(source_rate) / source_rate)).astype(np.float32)
                whole, chunks = PCMConverter(source_rate, target_rate), PCMConverter(source_rate, target_rate)
                whole.push(wave)
                for chunk in np.array_split(wave, 137): chunks.push(chunk)
                self.assertGreater(len(chunks.pending), target_rate * .95)
                self.assertLessEqual(len(chunks.pending), target_rate)
                np.testing.assert_allclose(chunks.pending, whole.pending, atol=.02)

    def test_downsampling_filters_out_of_band_noise(self):
        converter = PCMConverter(96000, 48000)
        t = np.arange(96000) / 96000
        converter.push(10000 * (np.sin(2*np.pi*1000*t) + np.sin(2*np.pi*30000*t)))
        signal = converter.pending[3000:43000]
        t = np.arange(len(signal)) / 48000
        amplitude = lambda frequency: abs(np.mean(signal * np.exp(-2j*np.pi*frequency*t))) * 2
        self.assertGreater(amplitude(1000), 9900)
        self.assertLess(amplitude(18000), 5)


if __name__ == '__main__': unittest.main()
