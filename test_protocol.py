import struct
import heapq
import unittest
from protocol import (HEADER, LEVEL_COMMAND, LEVEL_STATE, SILENT, LevelReader, ListeningLevel, ReturnBuffer,
                      level_command, microphone, slider_db, slider_position)


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


class ListeningLevelTests(unittest.TestCase):
    def state(self, raw, flags=2, changes=5, command=0):
        return LEVEL_STATE.pack(b'VSV1', raw, flags, changes, command)

    def test_command_packet(self):
        self.assertEqual(level_command(7, -20.86, 9), LEVEL_COMMAND.pack(b'VSL1', 7, -5340, 0, 9))
        self.assertEqual(len(level_command(7, None, 9)), 16)
        self.assertEqual(LEVEL_COMMAND.unpack(level_command(7, None, 9))[2], SILENT)
        self.assertEqual(LEVEL_COMMAND.unpack(level_command(7, 6, 9))[2], 0)          # never above 0 dB
        self.assertEqual(LEVEL_COMMAND.unpack(level_command(7, -200, 9))[2], -32767)  # very quiet, not silent

    def test_slider_maps_two_positions_a_db(self):
        self.assertIsNone(slider_db(0))
        self.assertEqual((slider_db(100), slider_db(80), slider_db(1)), (0, -10, -49.5))
        self.assertEqual((slider_position(None), slider_position(0), slider_position(-20.86)), (0, 100, 58.28))
        self.assertEqual(slider_position(-60), 0)
        for position in (1, 14.5, 58, 100):
            self.assertAlmostEqual(slider_position(slider_db(position)), position)

    def test_report_links_and_follows_the_board(self):
        level = ListeningLevel()
        self.assertFalse(level.linked)
        self.assertFalse(level.state(b'VSA2' + bytes(20)))
        self.assertFalse(level.state(self.state(0)[:15]))
        self.assertTrue(level.state(self.state(-5339)))
        self.assertTrue(level.linked and level.phone_sets and not level.by_pc)
        self.assertAlmostEqual(level.db, -20.855, places=3)
        self.assertTrue(level.state(self.state(SILENT, flags=3, changes=6)))
        self.assertIsNone(level.db); self.assertTrue(level.by_pc); self.assertEqual(level.changes, 6)

    def test_command_resent_until_echoed_then_given_up(self):
        level = ListeningLevel()
        level.set(-10, now=1.0)
        command, db = level.due(1.0)
        self.assertEqual(db, -10)
        self.assertIsNone(level.due(1.05))                      # not before RESEND
        self.assertEqual(level.due(1.11), (command, -10))      # resent
        level.state(self.state(-2560, flags=3, command=command - 1 & 0xffffffff))
        self.assertTrue(level.pending)                          # an older echo does not confirm it
        level.state(self.state(-2560, flags=3, command=command))
        self.assertFalse(level.pending); self.assertIsNone(level.due(2.0))
        level.set(-12, now=3.0)
        self.assertEqual(level.due(3.0)[0], command + 1 & 0xffffffff)
        self.assertIsNone(level.due(3.0 + ListeningLevel.GIVE_UP + .01))
        self.assertFalse(level.pending)

    def test_ids_differ_between_connections(self):
        # The board ignores a repeat of the last id it took, so a new connection must not start from it.
        self.assertNotEqual(ListeningLevel().command, ListeningLevel().command)


if __name__=='__main__':unittest.main()
