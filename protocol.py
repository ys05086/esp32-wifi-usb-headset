"""ESP32 Wi-Fi headset duplex-v1: 48 kHz mono PCM16LE, 480 frames per UDP packet."""
import struct
import threading
import time

import numpy as np

FRAMES = 480
PCM_BYTES = 960
HEADER = struct.Struct('<4sIIHH')


def microphone(session, sequence, pcm, stop=False):
    if not session or (len(pcm) != (0 if stop else PCM_BYTES)):
        raise ValueError('Invalid microphone packet')
    return HEADER.pack(b'VSM1', session, sequence, 0 if stop else FRAMES, 1 if stop else 2) + pcm


class LevelReader:
    """Plays a ReturnBuffer at the pace the device actually sends, as the board does for its microphone.

    A USB host that sends 1% fewer packets (an iPhone did: 982 a second) empties a fixed buffer once a second,
    10 ms of silence each time. Once a second this measures the device's surplus from the buffer's mean level,
    then reads that many frames more or fewer than it plays (plus a quarter of the way from the second's lowest
    level to 3/4 of the chosen buffer), at most MAX_ADJUST per 480 (2.5%), by linear interpolation. With no
    drift it is a plain copy. Only the audio callback calls read().
    """
    MAX_ADJUST = 12
    WINDOW = 100      # reads per decision, ~1 s

    def __init__(self, returns):
        self.returns = returns
        self.target = returns.target_blocks * FRAMES * 3 // 4
        self.pending = np.zeros(0, np.int16)
        self.adjust, self.rate = 0, 0.0
        self.removed = self.added = 0
        self._restart()

    def _restart(self):
        self.reads, self.window_min, self.window_sum, self.last_mean, self.adjust = 0, None, 0, None, 0

    @property
    def rate_ppm(self):
        return self.rate * 1e6 / 48000

    def read(self, now=None):
        if not self.returns.primed:            # filling or refilling: silence, and no rate from this stretch
            self.pending = np.zeros(0, np.int16)
            self._restart()
            return self.returns.read(now)
        take = FRAMES + self.adjust
        while len(self.pending) < take + 1:  # the next block's first frame for the last interpolation
            self.pending = np.concatenate((self.pending, np.frombuffer(self.returns.read(now), '<i2')))
        if take == FRAMES:
            out = self.pending[:FRAMES].copy()
        else:
            where = np.arange(FRAMES) * (take / FRAMES)
            out = np.round(np.interp(where, np.arange(take + 1), self.pending[:take + 1])).astype(np.int16)
            if take > FRAMES: self.removed += take - FRAMES
            else: self.added += FRAMES - take
        self.pending = self.pending[take:]
        level = self.returns.queued_frames + len(self.pending)
        self.window_min = level if self.window_min is None else min(self.window_min, level)
        self.window_sum += level
        self.reads += 1
        if self.reads == self.WINDOW:
            mean = self.window_sum / self.WINDOW
            if self.last_mean is not None:
                self.rate += ((mean - self.last_mean) + self.adjust * self.WINDOW - self.rate) / 4
            self.last_mean = mean
            want = self.rate + (self.window_min - self.target) / 4
            self.adjust = int(max(-self.MAX_ADJUST, min(self.MAX_ADJUST, round(want / self.WINDOW))))
            self.reads, self.window_min, self.window_sum = 0, None, 0
        return out.astype('<i2').tobytes()


class ReturnBuffer:
    def __init__(self, session, buffer_ms=80):
        self.session = session
        self.lock = threading.Lock()
        self.blocks = {}
        self.target_blocks = max(4, min(12, int(buffer_ms) // 10))
        self.next_sequence = None
        self.last_received = 0
        self.primed = False
        self.received = self.lost = self.underruns = self.discarded = 0
        self.reordered = self.late = 0
        self.max_gap_ms = 0.0
        self.highest_sequence = None
        self.starved_reads = 0

    @property
    def queued_ms(self):
        with self.lock: return len(self.blocks) * 10

    @property
    def queued_frames(self):
        with self.lock: return len(self.blocks) * FRAMES

    def push(self, data, now=None):
        now = time.monotonic() if now is None else now
        if len(data) != 976:
            return False
        magic, session, seq, frames, flags = HEADER.unpack_from(data)
        if (magic, session, frames, flags) != (b'VSR1', self.session, FRAMES, 0):
            return False
        with self.lock:
            if now - self.last_received > .3:
                self.blocks.clear(); self.primed = False; self.next_sequence = None
                self.highest_sequence = None; self.starved_reads = 0
            if self.next_sequence is None: self.next_sequence = seq
            gap = (seq - self.next_sequence) & 0xffffffff
            if gap >= 0x80000000:
                self.late += 1; return False
            if seq in self.blocks: return False
            # A sequence window bounds both latency and storage. Restart at
            # current speech after a large jump; never replay a long backlog.
            if gap >= 20:
                self.discarded += len(self.blocks)
                self.blocks.clear(); self.next_sequence = seq; self.primed = False
                self.starved_reads = 0
            if self.highest_sequence is not None and ((seq-self.highest_sequence) & 0xffffffff) >= 0x80000000:
                self.reordered += 1
            else: self.highest_sequence = seq
            if self.last_received:
                self.max_gap_ms = max(self.max_gap_ms, (now-self.last_received)*1000)
            self.blocks[seq] = data[16:]
            self.last_received = now; self.received += 1
        return True

    def read(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if now - self.last_received > .3:
                self.blocks.clear(); self.primed = False; self.next_sequence = None
                self.starved_reads = 0
            if not self.primed:
                if len(self.blocks) < self.target_blocks:
                    return bytes(PCM_BYTES)
                self.primed = True
            pcm = self.blocks.pop(self.next_sequence, None)
            if pcm is not None:
                self.next_sequence = (self.next_sequence + 1) & 0xffffffff
                self.starved_reads = 0
                return pcm
            if self.blocks:
                # Only declare loss at its playback deadline. A later packet
                # arriving first no longer destroys the opportunity to reorder.
                self.lost += 1
                self.next_sequence = (self.next_sequence + 1) & 0xffffffff
            if not self.starved_reads: self.underruns += 1
            self.starved_reads += 1
            # A single late block need not cause another full buffer wait.
            # Sustained starvation re-primes instead of endlessly playing gaps.
            if self.starved_reads >= 3: self.primed = False
            return bytes(PCM_BYTES)
