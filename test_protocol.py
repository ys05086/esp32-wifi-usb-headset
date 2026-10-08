import struct
import heapq
import unittest
from protocol import HEADER, ReturnBuffer, microphone


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


if __name__=='__main__':unittest.main()
