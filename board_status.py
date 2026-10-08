"""Read active USB mode independently of the real-time audio worker."""
import ipaddress
import json
import queue
import threading
import time
import urllib.request


def fetch_status(host):
    host = str(ipaddress.IPv4Address(host))
    # LAN status should never be routed through a system HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{host}/status', timeout=2) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError('보드 응답이 너무 큽니다')
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('protocol') != 'duplex-v1':
        raise ValueError('ESP32 헤드셋 상태 응답이 아닙니다')
    return data


class BoardStatus:
    def __init__(self, fetch=fetch_status):
        self.fetch = fetch
        self.host = None
        self.generation = 0
        self.pending = None
        self.next_check = 0
        self.responses = queue.Queue()
        self.data = None
        self.error = None
        self.checked_at = None

    def poll(self, host):
        host = host.strip()
        if host != self.host:
            self.host = host
            self.generation += 1
            self.data = self.error = self.checked_at = None
            self.next_check = 0
        while True:
            try:
                generation, data, error, checked_at = self.responses.get_nowait()
            except queue.Empty:
                break
            self.pending = None
            if generation == self.generation:
                self.data, self.error, self.checked_at = data, error, checked_at
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            self.error = '올바른 보드 IPv4 주소를 입력하세요'
            return
        if self.pending is None and time.monotonic() >= self.next_check:
            generation = self.generation
            self.pending = generation
            self.next_check = time.monotonic() + 3

            def worker():
                try:
                    data, error = self.fetch(host), None
                except Exception as exc:
                    data, error = None, str(exc)
                self.responses.put((generation, data, error, time.time()))

            threading.Thread(target=worker, name='ESP32-status', daemon=True).start()

    @property
    def label(self):
        if self.error:
            return 'USB 모드 · 확인 불가 (보드 주소·연결 확인)'
        if self.data is None:
            return 'USB 모드 · 확인 중…'
        mode = self.data.get('usb_mode')
        labels = {'standard': 'Standard', 'apple': 'Apple · 아이폰 호환',
                  'adaptive': 'Adaptive · 피드백 없음 (실험)'}
        return '현재 USB 모드 · ' + labels.get(mode, '알 수 없음 (펌웨어 확인)')

    def report(self):
        return {'host': self.host, 'checked_at_unix': self.checked_at,
                'status': self.data, 'error': self.error}
