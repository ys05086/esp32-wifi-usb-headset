import threading
import time
import unittest
from board_status import BoardStatus


class BoardStatusTests(unittest.TestCase):
    def settle(self, board, host):
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            board.poll(host)
            if board.checked_at is not None:
                return
            time.sleep(.005)
        self.fail('Status worker did not return')

    def test_reads_active_mode_and_clears_on_failure(self):
        responses=iter([{'usb_mode':'apple'}, OSError('offline')])
        def fetch(host):
            response=next(responses)
            if isinstance(response, Exception): raise response
            return response
        board=BoardStatus(fetch)
        self.settle(board,'192.168.0.14')
        self.assertIn('Apple',board.label)
        board.next_check=0
        board.checked_at=None
        self.settle(board,'192.168.0.14')
        self.assertIsNone(board.data)
        self.assertIn('확인 불가',board.label)

    def test_old_host_reply_cannot_label_new_host(self):
        release=threading.Event()
        def fetch(host):
            if host.endswith('.14'):
                release.wait(1)
                return {'usb_mode':'apple'}
            return {'usb_mode':'standard'}
        board=BoardStatus(fetch)
        board.poll('192.168.0.14')
        board.poll('192.168.0.15')
        self.assertIsNone(board.data)
        release.set()
        self.settle(board,'192.168.0.15')
        self.assertIn('Standard',board.label)
        self.assertEqual(board.report()['host'],'192.168.0.15')

    def test_invalid_host_makes_no_request(self):
        board=BoardStatus(lambda host:self.fail('Unexpected HTTP request'))
        board.poll('bad/address')
        self.assertIsNotNone(board.error)
        self.assertIsNone(board.pending)


if __name__ == '__main__': unittest.main()
