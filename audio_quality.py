"""Continuous AAC-LC encode/decode for outbound quality comparison.

The ESP32 wire format stays 48 kHz mono PCM16. No subprocesses or audio files.
This object belongs to the codec worker, never the PortAudio callback.
"""
from dataclasses import dataclass, asdict
from fractions import Fraction
import math
import numpy as np

SAMPLE_RATES = (16000, 24000, 32000, 44100, 48000)
BITRATES = (16, 24, 32, 48, 64, 96, 128, 160, 192)


def bitrates_for(rate):
    # AAC-LC mono's per-frame bit budget. Reject instead of silently clamping.
    return tuple(b for b in BITRATES if b * 1000 <= rate * 6)


@dataclass(frozen=True)
class QualitySettings:
    mode: str = 'pcm'
    sample_rate: int = 48000
    bitrate_kbps: int = 128

    def __post_init__(self):
        if self.mode not in ('pcm', 'aac') or self.sample_rate not in SAMPLE_RATES:
            raise ValueError('지원하지 않는 음질 설정이에요.')
        if self.bitrate_kbps not in bitrates_for(self.sample_rate):
            raise ValueError('이 샘플레이트에서 지원하지 않는 AAC 비트레이트예요.')

    @classmethod
    def restore(cls, value):
        try:
            return cls(**value) if isinstance(value, dict) else cls()
        except (TypeError, ValueError):
            return cls()

    def to_dict(self):
        return asdict(self)

    @property
    def label(self):
        return '원음 PCM · AAC 끔' if self.mode == 'pcm' else f'AAC · {self.sample_rate / 1000:g} kHz · {self.bitrate_kbps} kbps'

    @property
    def prime_blocks(self):
        return math.ceil(1024 / self.sample_rate * 100) + 2 if self.mode == 'aac' else 0


class AACProcessor:
    def __init__(self, settings):
        import av
        self.av = av
        self.settings = settings
        self.encoder = av.CodecContext.create('aac', 'w')
        self.encoder.sample_rate = settings.sample_rate
        self.encoder.layout = 'mono'
        self.encoder.format = 'fltp'
        self.encoder.bit_rate = settings.bitrate_kbps * 1000
        self.encoder.time_base = Fraction(1, settings.sample_rate)
        self.encoder.open()
        if self.encoder.bit_rate != settings.bitrate_kbps * 1000:
            raise RuntimeError('AAC 인코더가 선택한 비트레이트를 적용하지 못했어요.')
        self.decoder = av.CodecContext.create('aac', 'r')
        self.decoder.extradata = self.encoder.extradata
        self.decoder.open()
        self.down = av.AudioResampler(format='fltp', layout='mono', rate=settings.sample_rate)
        self.up = av.AudioResampler(format='s16', layout='mono', rate=48000)
        self.input_frames = self.decoded_frames = self.encoded_bytes = self.encoded_samples = 0
        self.pending = bytearray()
        self.emitted_frames = 0
        self.first_output_ms = None
        self.closed = False

    def _packets(self, packets):
        for packet in packets:
            self.encoded_bytes += packet.size
            self.encoded_samples += packet.duration or self.encoder.frame_size
            for frame in self.decoder.decode(packet):
                # AAC encoder priming has negative PTS. Do not play it as extra silence.
                if frame.pts is not None and frame.pts < 0:
                    skip = min(frame.samples, -frame.pts)
                    if skip == frame.samples:
                        continue
                    data = frame.to_ndarray()[:, skip:].copy()
                    frame = self.av.AudioFrame.from_ndarray(data, format=frame.format.name, layout='mono')
                    frame.sample_rate = self.settings.sample_rate
                    frame.pts = 0
                    frame.time_base = Fraction(1, self.settings.sample_rate)
                for output in self.up.resample(frame):
                    self._output(output)

    def _output(self, frame):
        self.decoded_frames += frame.samples
        if self.first_output_ms is None:
            self.first_output_ms = self.input_frames / 48
        self.pending.extend(frame.to_ndarray().astype('<i2', copy=False).tobytes())

    def _blocks(self):
        size = len(self.pending) // 960 * 960
        blocks = [bytes(self.pending[i:i+960]) for i in range(0, size, 960)]
        del self.pending[:size]
        self.emitted_frames += size // 2
        return blocks

    def push(self, pcm):
        if self.closed:
            raise RuntimeError('AAC processor already closed')
        if len(pcm) != 960:
            raise ValueError('Expected one 10 ms 48 kHz PCM16 mono block')
        data = np.frombuffer(pcm, dtype='<i2').reshape(1, -1)
        frame = self.av.AudioFrame.from_ndarray(data, format='s16', layout='mono')
        frame.sample_rate = 48000
        frame.pts = self.input_frames
        frame.time_base = Fraction(1, 48000)
        self.input_frames += 480
        for output in self.down.resample(frame):
            self._packets(self.encoder.encode(output))
        return self._blocks()

    def finish(self):
        """Finite synthetic/offline tests only; live stop discards pending audio."""
        if self.closed:
            return []
        if self.input_frames:
            for output in self.down.resample(None):
                self._packets(self.encoder.encode(output))
            self._packets(self.encoder.encode(None))
            for output in self.up.resample(None):
                self._output(output)
        self.closed = True
        # The encoder may pad its last 1024-sample frame; omit that test-only tail.
        del self.pending[max(0, self.input_frames-self.emitted_frames)*2:]
        return self._blocks()

    def report(self):
        return dict(settings=self.settings.to_dict(), frame_samples=self.encoder.frame_size,
                    input_frames=self.input_frames, decoded_frames=self.decoded_frames,
                    first_output_input_ms=self.first_output_ms,
                    pending_ms=max(0, self.input_frames-self.decoded_frames)/48,
                    encoded_average_kbps=(self.encoded_bytes*8*self.settings.sample_rate /
                                          self.encoded_samples/1000 if self.encoded_samples else 0))


def quality_self_test():
    """Exercise packaged AAC libraries without opening devices or network."""
    settings = QualitySettings('aac', 24000, 64)
    codec = AACProcessor(settings)
    pcm = (np.sin(2*np.pi*440*np.arange(48000)/48000)*8000).astype('<i2')
    blocks = []
    for chunk in np.split(pcm, 100):
        blocks.extend(codec.push(chunk.tobytes()))
    blocks.extend(codec.finish())
    audio = np.frombuffer(b''.join(blocks), dtype='<i2')
    return dict(ok=len(audio)>=47520 and float(np.std(audio))>1000,
                output_frames=len(audio), **codec.report())
