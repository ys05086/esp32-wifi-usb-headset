"""Opt-in hardware smoke test: local packets only, no audio recordings."""
import socket
import struct
import threading
import time
from client import HeadsetClient


def audio_self_test(input_device, output_device, quality=None):
    # Use a loopback board stub so testing stream startup never sends the
    # user's microphone to a physical ESP32 or an active call.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(('127.0.0.1', 49152))
        server.settimeout(.1)
        done = threading.Event()
        def reply():
            received = 0
            while not done.is_set():
                try: data, address = server.recvfrom(2048)
                except socket.timeout: continue
                if data[:4] == b'VSM1' and len(data) == 976:
                    received += 1
                    server.sendto(struct.pack('<4sIIIII', b'VSA2', received, 0, 0, 0, 0), address)
                    session = struct.unpack_from('<I', data, 4)[0]
                    server.sendto(struct.pack('<4sIIHH', b'VSR1', session, received-1, 480, 0)+bytes(960), address)
        responder = threading.Thread(target=reply, daemon=True)
        responder.start()
        client = HeadsetClient('127.0.0.1', input_device, output_device, quality=quality)
        try:
            client.start()
            deadline = time.monotonic() + 3
            while client.active and time.monotonic() < deadline:
                codec_ready = client.quality.mode == 'pcm' or client.quality_report.get('decoded_frames',0)>=4800
                if client.board_received >= 20 and client.returns.received >= 20 and codec_ready: break
                time.sleep(.02)
            codec_ready = client.quality.mode == 'pcm' or client.quality_report.get('decoded_frames',0)>=4800
            report = {'ok': client.board_received >= 20 and client.returns.received >= 20 and codec_ready and not client.quality_error,
                      'status': client.status, 'input_rate': client.input_rate,
                      'output_rate': client.output_rate, 'acknowledged': client.board_received,
                      'callback_errors': client.audio_errors, 'return_received': client.returns.received,
                      'return_underruns': client.returns.underruns,'quality':client.quality.to_dict(),
                      'aac_processing':client.quality_report,'aac_queue_drops':client.quality_drops,
                      'send_queue_underruns':client.send_underruns}
        finally:
            client.stop()
            if client.thread: client.thread.join(timeout=3)
            done.set(); responder.join(timeout=1)
        return report
