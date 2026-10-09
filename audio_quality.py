"""Continuous AAC-LC encode/decode for outbound quality comparison.

The ESP32 wire format stays 48 kHz mono PCM16. The codec is a minimal LGPL build of FFmpeg (only PCM, AAC,
ADTS, pipes and the resampler), bundled as ffmpeg/ffmpeg.exe next to the app and built by the workflow from
the pinned source (THIRD_PARTY_NOTICES.md). It runs as two child processes, PCM -> AAC (ADTS) and
AAC -> PCM; this object feeds the first from the codec worker and threads collect the rest. Nothing here
runs in the PortAudio callback, and no audio is written to files.
"""
from collections import deque
from dataclasses import dataclass, asdict
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

SAMPLE_RATES = (16000, 24000, 32000, 44100, 48000)
BITRATES = (16, 24, 32, 48, 64, 96, 128, 160, 192)
FRAME_SAMPLES = 1024          # AAC-LC frame
ENCODER_DELAY = 1024          # FFmpeg's AAC encoder primes one frame; ADTS cannot carry that, so it is cut


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
        # one AAC frame at the chosen rate, plus the two FFmpeg processes and pipes between them
        return math.ceil(FRAME_SAMPLES / self.sample_rate * 100) + 6 if self.mode == 'aac' else 0


def ffmpeg_path():
    """The bundled ffmpeg (ffmpeg/ffmpeg.exe next to the app or this file), else ESP32_BRIDGE_FFMPEG, else PATH."""
    here = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    for candidate in (here / 'ffmpeg' / 'ffmpeg.exe', here / 'ffmpeg' / 'ffmpeg'):
        if candidate.is_file():
            return str(candidate)
    found = os.environ.get('ESP32_BRIDGE_FFMPEG') or shutil.which('ffmpeg')
    if found:
        return found
    raise RuntimeError('AAC에 쓸 ffmpeg를 찾지 못했어요 (앱 폴더의 ffmpeg/ffmpeg.exe).')


class AACProcessor:
    def __init__(self, settings):
        self.settings = settings
        ffmpeg = ffmpeg_path()
        quiet = ['-hide_banner', '-nostats', '-loglevel', 'error']
        # Both inputs skip stream probing: by default FFmpeg reads up to 5 s before it starts.
        encode = [ffmpeg, *quiet, '-probesize', '32', '-analyzeduration', '0', '-f', 's16le', '-ar', '48000', '-ac', '1', '-i', 'pipe:0',
                  '-af', f'aresample={settings.sample_rate}', '-c:a', 'aac', '-b:a', f'{settings.bitrate_kbps}k',
                  '-f', 'adts', '-flush_packets', '1', 'pipe:1']
        decode = [ffmpeg, *quiet, '-probesize', '32', '-analyzeduration', '0', '-f', 'aac', '-i', 'pipe:0',
                  '-af', f'atrim=start_sample={ENCODER_DELAY},aresample=48000', '-ac', '1',
                  '-f', 's16le', '-flush_packets', '1', 'pipe:1']
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        self.encoder = subprocess.Popen(encode, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        bufsize=0, creationflags=flags)
        self.decoder = subprocess.Popen(decode, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        bufsize=0, creationflags=flags)
        self.lock = threading.Lock()
        self.input_frames = self.decoded_frames = self.encoded_bytes = self.encoded_frames = 0
        self.pending = bytearray()
        self.emitted_frames = 0
        self.first_output_ms = None
        self.closed = False
        self.error = None
        self.errors = {name: deque(maxlen=20) for name in ('encoder', 'decoder')}
        self.threads = [threading.Thread(target=target, name=f'AAC-{target.__name__}', daemon=True)
                        for target in (self._relay, self._collect)]
        self.threads += [threading.Thread(target=self._drain, args=(name, proc), daemon=True)
                         for name, proc in (('encoder', self.encoder), ('decoder', self.decoder))]
        for thread in self.threads:
            thread.start()

    def _relay(self):
        """encoder ADTS -> decoder, counting AAC frames and payload bytes for the bitrate report."""
        buffer = bytearray()
        try:
            while True:
                chunk = self.encoder.stdout.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                while len(buffer) >= 7 and buffer[0] == 0xFF and buffer[1] & 0xF0 == 0xF0:
                    length = (buffer[3] & 0x03) << 11 | buffer[4] << 3 | buffer[5] >> 5
                    if len(buffer) < length:
                        break
                    header = 7 if buffer[1] & 0x01 else 9
                    with self.lock:
                        self.encoded_frames += (buffer[6] & 0x03) + 1
                        self.encoded_bytes += length - header
                    del buffer[:length]
                self.decoder.stdin.write(chunk)
        except (OSError, ValueError) as error:
            if not self.closed:
                self.error = self.error or f'AAC 전달 실패: {error}'
        finally:
            try:
                self.decoder.stdin.close()
            except OSError:
                pass

    def _collect(self):
        try:
            while True:
                chunk = self.decoder.stdout.read(4096)
                if not chunk:
                    break
                with self.lock:
                    if self.first_output_ms is None:
                        self.first_output_ms = self.input_frames / 48
                    self.pending.extend(chunk)
                    self.decoded_frames += len(chunk) // 2
        except (OSError, ValueError) as error:
            if not self.closed:
                self.error = self.error or f'AAC 복원 실패: {error}'

    def _drain(self, name, proc):
        for line in iter(proc.stderr.readline, b''):
            self.errors[name].append(line.decode('utf-8', 'replace').strip())

    def _check(self):
        if self.error:
            raise RuntimeError(self.error)
        for name, proc in (('encoder', self.encoder), ('decoder', self.decoder)):
            code = proc.poll()
            if code is not None and not self.closed:
                detail = ' / '.join(self.errors[name]) or f'종료 코드 {code}'
                raise RuntimeError(f'AAC {name} 프로세스가 멈췄어요: {detail}')

    def _blocks(self):
        with self.lock:
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
        self._check()
        try:
            self.encoder.stdin.write(pcm)
        except OSError as error:
            self._check()
            raise RuntimeError(f'AAC 인코더에 쓰지 못했어요: {error}') from error
        with self.lock:
            self.input_frames += 480
        return self._blocks()

    def finish(self, timeout=10):
        """Finite synthetic/offline tests only: flush both processes and return the rest, cut to the input length.
        A live stop calls close() and discards pending audio."""
        if self.closed:
            return []
        self.encoder.stdin.close()
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))
        for proc in (self.encoder, self.decoder):
            proc.wait(max(0.1, deadline - time.monotonic()))
        if self.error:
            raise RuntimeError(self.error)
        self.closed = True
        with self.lock:
            # the encoder pads its last 1024-sample frame; omit that test-only tail
            del self.pending[max(0, self.input_frames - self.emitted_frames) * 2:]
        return self._blocks()

    def close(self):
        """Stop both processes at once (live stop); pending audio is dropped."""
        self.closed = True
        for proc in (self.encoder, self.decoder):
            for stream in (proc.stdin, proc.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
            if proc.poll() is None:
                proc.kill()
        for proc in (self.encoder, self.decoder):
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                pass

    def __del__(self):
        if not getattr(self, 'closed', True):
            self.close()

    def report(self):
        with self.lock:
            return dict(settings=self.settings.to_dict(), frame_samples=FRAME_SAMPLES,
                        input_frames=self.input_frames, decoded_frames=self.decoded_frames,
                        first_output_input_ms=self.first_output_ms,
                        pending_ms=max(0, self.input_frames-self.decoded_frames)/48,
                        encoded_average_kbps=(self.encoded_bytes*8*self.settings.sample_rate /
                                              (self.encoded_frames*FRAME_SAMPLES)/1000 if self.encoded_frames else 0))


def quality_self_test():
    """Exercise the bundled AAC codec without opening devices or network."""
    settings = QualitySettings('aac', 24000, 64)
    codec = AACProcessor(settings)
    pcm = (np.sin(2*np.pi*440*np.arange(48000)/48000)*8000).astype('<i2')
    blocks = []
    for chunk in np.split(pcm, 100):
        blocks.extend(codec.push(chunk.tobytes()))
    blocks.extend(codec.finish())
    audio = np.frombuffer(b''.join(blocks), dtype='<i2')
    return dict(ok=len(audio)>=47520 and float(np.std(audio))>1000,
                output_frames=len(audio), ffmpeg=ffmpeg_path(), **codec.report())
