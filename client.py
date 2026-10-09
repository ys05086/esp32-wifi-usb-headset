"""PC audio endpoints <-> Wi-Fi ESP32 USB headset for phone calls."""
import ipaddress
import queue
import secrets
import select
import socket
import struct
import threading
import time
import sys
import numpy as np
import sounddevice as sd
from protocol import ReturnBuffer, microphone
from audio_format import endpoint_format, PCMConverter
from audio_quality import QualitySettings, AACProcessor


class HeadsetClient:
    def __init__(self, host, input_device, output_device, buffer_ms=80, quality=None):
        ipaddress.IPv4Address(host)
        self.host, self.input_device, self.output_device = host, input_device, output_device
        self.session = secrets.randbelow(2**32 - 1) + 1
        self.returns = ReturnBuffer(self.session, buffer_ms)
        self.captured = queue.Queue(maxsize=20)
        self.quality = quality or QualitySettings()
        self.outbound = queue.Queue(maxsize=20) if self.quality.mode == 'aac' else self.captured
        self.quality_thread = self.processor = None
        self.quality_error = None
        self.quality_drops = self.send_underruns = 0
        self.quality_report = {}
        self.stop_event = threading.Event()
        self.thread = None
        self.input_gain = self.output_gain = 1.0
        self.mic_muted = self.return_muted = False
        self.status = '연결 준비 중'
        self.sent = self.input_drops = self.audio_errors = 0
        self.capture_errors = self.playback_errors = 0
        self.board_received = self.board_underruns = self.board_return_drops = 0
        self.input_rate = self.output_rate = 48000
        self.capture_converter = PCMConverter(48000, 48000)
        self.playback_converter = PCMConverter(48000, 48000)

    def start(self):
        self.thread = threading.Thread(target=self.run, name='ESP32-headset', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def capture(self, data, frames, timing, status):
        if status: self.audio_errors += 1; self.capture_errors += 1
        mono = data.astype(np.int32).mean(axis=1) * self.input_gain
        self.capture_converter.push(mono)
        while True:
            block = self.capture_converter.pop(480)
            if block is None: break
            pcm = bytes(960) if self.mic_muted else block.tobytes()
            try: self.captured.put_nowait(pcm)
            except queue.Full:
                try: self.captured.get_nowait()
                except queue.Empty: pass
                try: self.captured.put_nowait(pcm)
                except queue.Full: pass
                self.input_drops += 1

    def playback(self, data, frames, timing, status):
        if status: self.audio_errors += 1; self.playback_errors += 1
        data.fill(0)
        mono = self.playback_converter.pop(frames)
        while mono is None:
            pcm = self.returns.read()
            self.playback_converter.push(np.frombuffer(pcm, dtype='<i2'))
            mono = self.playback_converter.pop(frames)
        if not self.return_muted:
            mono = mono.astype(np.float32) * self.output_gain
            data[:] = np.clip(mono, -32768, 32767).astype(np.int16)[:, None]

    def encode_audio(self):
        try:
            while not self.stop_event.is_set():
                try: pcm = self.captured.get(timeout=.05)
                except queue.Empty: continue
                for block in self.processor.push(pcm):
                    if self.stop_event.is_set(): break
                    try: self.outbound.put_nowait(block)
                    except queue.Full:
                        try: self.outbound.get_nowait()
                        except queue.Empty: pass
                        try: self.outbound.put_nowait(block)
                        except queue.Full: pass
                        self.quality_drops += 1
                self.quality_report = self.processor.report()
        except Exception as error:
            self.quality_error = f'AAC 처리 실패: {error}'
            self.stop_event.set()

    def run(self):
        timer = None; sock = None; seq = 0; com_initialized = False
        try:
            if sys.platform == 'win32':
                import ctypes
                # WASAPI activation is per-thread: initializing PortAudio in
                # the GUI thread does not initialize this audio worker's COM.
                result = ctypes.windll.ole32.CoInitializeEx(None, 0)
                if result not in (0, 1):
                    raise RuntimeError(f'Windows 오디오 초기화 실패: 0x{result & 0xffffffff:08X}')
                com_initialized = True
                timer = ctypes.windll.winmm; timer.timeBeginPeriod(1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect((self.host, 49152)); sock.setblocking(False)
            self.input_rate, input_channels = endpoint_format(self.input_device, 'input')
            self.output_rate, output_channels = endpoint_format(self.output_device, 'output')
            self.capture_converter = PCMConverter(self.input_rate, 48000)
            self.playback_converter = PCMConverter(48000, self.output_rate)
            if self.quality.mode == 'aac':
                self.processor = AACProcessor(self.quality)
                self.quality_thread = threading.Thread(target=self.encode_audio, name='AAC-quality', daemon=True)
                self.quality_thread.start()
            with sd.InputStream(device=self.input_device, samplerate=self.input_rate, channels=input_channels,
                                dtype='int16', blocksize=round(self.input_rate / 100), callback=self.capture), \
                 sd.OutputStream(device=self.output_device, samplerate=self.output_rate, channels=output_channels,
                                 dtype='int16', blocksize=round(self.output_rate / 100), callback=self.playback):
                started = next_send = time.monotonic(); last_ack = 0
                instant_capture = self.input_rate == 48000 and self.quality.mode == 'pcm'
                capture_ready = instant_capture
                prime_blocks = self.quality.prime_blocks if self.quality.mode == 'aac' else 4
                self.status = '보드 응답 대기'
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    if now >= next_send:
                        # A delayed thread skips old capture blocks instead of replaying a burst.
                        if now - next_send > .03:
                            keep = prime_blocks if self.quality.mode == 'aac' else 2
                            while self.outbound.qsize() > keep:
                                try: self.outbound.get_nowait(); self.input_drops += 1
                                except queue.Empty: break
                            next_send = now
                        # Prime across the resampler's variable output batches.
                        if not capture_ready and self.outbound.qsize() >= prime_blocks:
                            capture_ready = True
                        try: pcm = self.outbound.get_nowait() if capture_ready else bytes(960)
                        except queue.Empty:
                            pcm = bytes(960); self.send_underruns += 1; capture_ready = instant_capture
                        # Mute must take effect even with AAC frames already queued.
                        if self.mic_muted: pcm = bytes(960)
                        try: sock.send(microphone(self.session, seq, pcm)); self.sent += 1
                        except BlockingIOError: self.input_drops += 1
                        seq = (seq + 1) & 0xffffffff; next_send += .01
                    readable, _, _ = select.select([sock], [], [], max(0, min(.01, next_send-time.monotonic())))
                    if readable:
                        for _ in range(32):
                            try: data = sock.recv(2048)
                            except BlockingIOError: break
                            if len(data) == 24 and data[:4] == b'VSA2':
                                _, self.board_received, self.board_underruns, _, _, self.board_return_drops = struct.unpack('<4sIIIII', data)
                                last_ack = time.monotonic(); self.status = '양방향 연결됨 · 기기 소리는 선택한 출력으로 재생'
                            else: self.returns.push(data)
                    if now - max(started, last_ack) > 8:
                        raise RuntimeError('보드 응답 없음: IP·같은 네트워크·양방향 펌웨어를 확인하세요.')
                    if last_ack and now-last_ack>2: self.status = '보드 응답이 지연되고 있어요.'
                if self.quality_error: raise RuntimeError(self.quality_error)
                self.status = '연결 종료 · USB 마이크는 무음'
        except Exception as error:
            self.status = str(error)
        finally:
            self.stop_event.set()
            if self.quality_thread: self.quality_thread.join(timeout=2)
            if self.processor: self.processor.close()  # ends the FFmpeg child processes
            if sock:
                try: sock.send(microphone(self.session, seq, b'', stop=True))
                except OSError: pass
                sock.close()
            if timer: timer.timeEndPeriod(1)
            if com_initialized: ctypes.windll.ole32.CoUninitialize()
