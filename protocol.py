"""ESP32 Wi-Fi headset duplex-v1: 48 kHz mono PCM16LE, 480 frames per UDP packet."""
import struct
import threading
import time

FRAMES = 480
PCM_BYTES = 960
HEADER = struct.Struct('<4sIIHH')


def microphone(session, sequence, pcm, stop=False):
    if not session or (len(pcm) != (0 if stop else PCM_BYTES)):
        raise ValueError('Invalid microphone packet')
    return HEADER.pack(b'VSM1', session, sequence, 0 if stop else FRAMES, 1 if stop else 2) + pcm


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
