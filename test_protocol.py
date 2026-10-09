import struct
import heapq
import unittest
from protocol import HEADER, LevelReader, ReturnBuffer, microphone


class ProtocolTests(unittest.TestCase):
    def packet(self, seq, session=7):
        return HEADER.pack(b'VSR1',session,seq,480,0)+b'\x34\x12'*480

    def test_wire_format(self):
        self.assertEqual(microphone(7,1,bytes(960))[:16],HEADER.pack(b'VSM1',7,1,480,2))
        self.assertEqual(len(microphone(7,2,b'',True)),16)

    def test_prime_loss_duplicate_and_timeout(self):
        b=ReturnBuffer(7,40)
        self.assertFalse(b.push(self.packet(0,8),1))
        for n in range(4):self.assertTrue(b.push(self.packet(n),1+n*.01))
        self.assertFalse(b.push(self.packet(3),1.04))
        self.assertEqual(b.read(1.04),b'\x34\x12'*480)
        self.assertTrue(b.push(self.packet(6),1.05));self.assertEqual(b.lost,0)
        for _ in range(5): b.read(1.06)
        self.assertEqual(b.lost,2)
        self.assertEqual(b.read(2),bytes(960))

    def test_wrap_and_bounded_queue(self):
        b=ReturnBuffer(7)
        self.assertTrue(b.push(self.packet(0xffffffff),1))
        self.assertTrue(b.push(self.packet(0),1.01))
        for i in range(1,100):self.assertTrue(b.push(self.packet(i),1.01+i*.01))
        self.assertLessEqual(len(b.blocks),20);self.assertGreater(b.discarded,0)

    def test_reordered_audio_is_not_replaced_by_silence(self):
        b=ReturnBuffer(7,40)
        for seq in [0,2,1,3]:self.assertTrue(b.push(self.packet(seq),1))
        for _ in range(4):self.assertEqual(b.read(1.04),b'\x34\x12'*480)
        self.assertEqual(b.lost,0);self.assertEqual(b.reordered,1)

    def test_one_late_block_recovers_without_full_reprime(self):
        b=ReturnBuffer(7,40)
        for seq in range(4):b.push(self.packet(seq),1)
        for _ in range(4):b.read(1.04)
        self.assertEqual(b.read(1.05),bytes(960))
        b.push(self.packet(4),1.055)
        self.assertEqual(b.read(1.06),b'\x34\x12'*480)
        self.assertEqual(b.underruns,1)

    def test_sustained_outage_reprime_and_expiry(self):
        b=ReturnBuffer(7,40)
        for seq in range(4):b.push(self.packet(seq),1)
        for _ in range(7):b.read(1.04)
        self.assertFalse(b.primed);self.assertEqual(b.underruns,1)
        self.assertEqual(b.read(2),bytes(960))
        for seq in range(100,104):b.push(self.packet(seq),2)
        self.assertEqual(b.read(2.01),b'\x34\x12'*480)

    def test_thirty_minutes_of_bursty_arrivals_stays_bounded(self):
        # Virtual time, NOT a 30-minute hardware/call stability claim.
        b=ReturnBuffer(7,80); arrivals=[]; highest_queue=0
        for tick in range(30*60*100):
            delay=6 if 200 <= tick%500 < 210 else 0
            heapq.heappush(arrivals,(tick+delay,tick))
            while arrivals and arrivals[0][0] <= tick:
                _,seq=heapq.heappop(arrivals)
                b.push(self.packet(seq),1+tick*.01)
            highest_queue=max(highest_queue,len(b.blocks))
            if tick>=8:self.assertEqual(b.read(1+tick*.01),b'\x34\x12'*480)
        self.assertEqual(b.underruns,0);self.assertEqual(b.lost,0)
        self.assertGreater(b.reordered,0);self.assertLessEqual(highest_queue,15)


class LevelReaderTests(unittest.TestCase):
    """The device sends at its own pace (the PC plays exactly 100 blocks a second); Wi-Fi adds jitter."""
    def run_device(self, ppm, seconds=600, jitter_ms=20, seed=3):
        import numpy as np
        rng = np.random.default_rng(seed)
        b = ReturnBuffer(7, 80); level = LevelReader(b)
        period = 0.01 / (1 + ppm * 1e-6); k = 0; arrivals = []
        tri = lambda n: np.where(n % 96 < 48, -12000 + (n % 96) * 500, 12000 - (n % 96 - 48) * 500)
        worst = previous = 0; started = False
        for tick in range(seconds * 100):
            now = 1 + tick * 0.01
            while k * period <= tick * 0.01:      # the device's blocks, each delayed up to jitter_ms
                heapq.heappush(arrivals, (k * period + rng.uniform(0, jitter_ms / 1000), k)); k += 1
            while arrivals and arrivals[0][0] <= tick * 0.01:
                _, seq = heapq.heappop(arrivals)
                pcm = tri(np.arange(seq * 480, seq * 480 + 480)).astype('<i2').tobytes()
                b.push(HEADER.pack(b'VSR1', 7, seq, 480, 0) + pcm, now)
            y = np.frombuffer(level.read(now), '<i2').astype(int)
            if b.primed:
                steps = np.abs(np.diff(np.concatenate(([previous], y)) if started else y)); started = True
                worst = max(worst, int(steps.max()))
                previous = int(y[-1])
        return b, level, worst

    def test_device_slow_or_fast_by_up_to_two_percent(self):
        for ppm in (0, -12000, 12000, -20000, 20000):
            with self.subTest(ppm=ppm):
                b, level, worst = self.run_device(ppm)
                self.assertLessEqual(b.underruns, 1)                  # at most the start-up one
                self.assertEqual(b.lost, 0); self.assertEqual(b.discarded, 0)
                self.assertLessEqual(worst, 500 + (500 * LevelReader.MAX_ADJUST + 479) // 480 + 2)
                self.assertAlmostEqual(level.rate_ppm, ppm, delta=abs(ppm) * 0.1 + 300)

    def test_no_drift_is_a_plain_copy(self):
        b = ReturnBuffer(7, 40); level = LevelReader(b)
        for seq in range(4): b.push(HEADER.pack(b'VSR1', 7, seq, 480, 0) + b'\x34\x12' * 480, 1.0)
        self.assertEqual(level.read(1.0), b'\x34\x12' * 480)
        self.assertEqual((level.adjust, level.removed, level.added), (0, 0, 0))


if __name__=='__main__':unittest.main()
