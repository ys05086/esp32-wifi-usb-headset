"""Negotiate endpoint formats; keep network PCM fixed at 48 kHz."""
import numpy as np
import sounddevice as sd
import soxr


def endpoint_format(device, direction):
    info = sd.query_devices(device)
    maximum = int(info[f'max_{direction}_channels'])
    check = sd.check_input_settings if direction == 'input' else sd.check_output_settings
    rates = dict.fromkeys([48000, int(info['default_samplerate']), 44100, 96000, 32000, 16000])
    channels = dict.fromkeys([min(2, maximum), 1, maximum])
    for rate in rates:
        for count in channels:
            if count < 1 or count > maximum:
                continue
            try:
                check(device=device, samplerate=rate, channels=count, dtype='int16')
                return rate, count
            except sd.PortAudioError:
                pass
    label = '입력' if direction == 'input' else '출력'
    raise ValueError(f'{label} 장치의 지원 오디오 형식을 찾지 못했어요: {info["name"]}. 다른 드라이버 항목을 선택해 주세요.')


class PCMConverter:
    """Stateful mono conversion with a FIFO for arbitrary callback sizes."""
    def __init__(self, source_rate, target_rate):
        self.resampler = None if source_rate == target_rate else soxr.ResampleStream(
            source_rate, target_rate, 1, dtype='float32', quality='HQ')
        self.pending = np.empty(0, dtype=np.float32)

    def push(self, samples):
        samples = np.asarray(samples, dtype=np.float32)
        if self.resampler is not None:
            samples = self.resampler.resample_chunk(samples)
        self.pending = np.concatenate((self.pending, samples))

    def pop(self, frames):
        if len(self.pending) < frames:
            return None
        result = np.clip(self.pending[:frames], -32768, 32767).astype('<i2')
        self.pending = self.pending[frames:]
        return result
