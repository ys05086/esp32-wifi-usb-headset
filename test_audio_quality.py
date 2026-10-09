import json
import queue
import threading
import time
import unittest
from collections import deque
from unittest.mock import patch
import numpy as np
from audio_quality import AACProcessor, QualitySettings, SAMPLE_RATES, bitrates_for
from client import HeadsetClient


def encode(source, rate=48000, bitrate=128):
    codec=AACProcessor(QualitySettings('aac',rate,bitrate))
    blocks=[]
    for i in range(0,len(source),480):blocks.extend(codec.push(source[i:i+480].astype('<i2').tobytes()))
    blocks.extend(codec.finish())
    return np.frombuffer(b''.join(blocks),dtype='<i2'),codec


class QualityTests(unittest.TestCase):
    def test_settings_roundtrip_and_invalid_saved_data(self):
        s=QualitySettings('aac',24000,96)
        self.assertEqual(QualitySettings.restore(json.loads(json.dumps(s.to_dict()))),s)
        for bad in [None,[],{'sample_rate':12345},{'mode':'aac','sample_rate':16000,'bitrate_kbps':192}]:
            self.assertEqual(QualitySettings.restore(bad),QualitySettings())
        with self.assertRaises(ValueError):QualitySettings('aac',16000,192)

    def test_every_exposed_format_encodes_without_silent_bitrate_clamp(self):
        t=np.arange(48000)/48000
        source=(7000*np.sin(2*np.pi*1000*t)).astype('<i2')
        for rate in SAMPLE_RATES:
            for bitrate in bitrates_for(rate):
                with self.subTest(rate=rate,bitrate=bitrate):
                    output,codec=encode(source,rate,bitrate)
                    # FFmpeg gets the requested rate; its AAC encoder may spend less on a plain tone.
                    self.assertIn(f'{bitrate}k',codec.encoder.args)
                    self.assertLess(codec.report()['encoded_average_kbps'],bitrate*1.3)
                    self.assertEqual(len(output),len(source))
                    self.assertGreater(np.std(output[5000:-5000]),3000)
                    self.assertLess(np.max(np.abs(output.astype(float))),13000)
                    # Low AAC bitrates intentionally alter the waveform/phase.
                    self.assertGreater(np.corrcoef(source[5000:-5000],output[5000:-5000])[0,1],.90)
                    self.assertIsNotNone(codec.first_output_ms)
                    self.assertEqual(codec.finish(),[])

    def test_bitrate_setting_takes_effect(self):
        # On noise the average follows the setting up the scale (the encoder caps near 6 bits per sample).
        source=np.random.default_rng(0).normal(0,4000,48000)
        for rate in SAMPLE_RATES:
            with self.subTest(rate=rate):
                averages=[encode(source,rate,b)[1].report()['encoded_average_kbps'] for b in bitrates_for(rate)]
                for lower,higher in zip(averages,averages[1:]):self.assertGreater(higher,lower*.95)
                for bitrate,average in zip(bitrates_for(rate),averages):
                    if bitrate<=64:self.assertGreater(average,bitrate*.85)

    def test_sample_rate_removes_above_nyquist_content(self):
        t=np.arange(96000)/48000
        source=5000*(np.sin(2*np.pi*1000*t)+np.sin(2*np.pi*12000*t))
        narrow,_=encode(source,16000,64)
        wide,_=encode(source,48000,128)
        def amplitude(x,hz):
            y=x[12000:84000];t=np.arange(len(y))/48000
            return abs(np.mean(y*np.exp(-2j*np.pi*hz*t)))*2
        self.assertGreater(amplitude(narrow,1000),4000)
        self.assertLess(amplitude(narrow,12000),50)
        self.assertGreater(amplitude(wide,12000),2000)

    def test_bitrate_changes_encoded_size_and_decoded_audio(self):
        rng=np.random.default_rng(17)
        source=rng.normal(0,4000,96000)
        low,lc=encode(source,48000,16);high,hc=encode(source,48000,128)
        self.assertGreater(hc.encoded_bytes,lc.encoded_bytes*3)
        self.assertGreater(np.sqrt(np.mean((low.astype(float)-high.astype(float))**2)),100)

    def test_default_path_is_exact_pcm_without_codec(self):
        with patch('client.AACProcessor',side_effect=AssertionError('PCM opened codec')):
            client=HeadsetClient('127.0.0.1',None,None)
            source=np.arange(-240,240,dtype=np.int16).reshape(-1,1)
            client.capture(source,480,None,None)
            self.assertIs(client.outbound,client.captured)
            self.assertEqual(client.outbound.get_nowait(),source.astype('<i2').tobytes())

    def test_worker_bounded_queue_stop_and_report(self):
        client=HeadsetClient('127.0.0.1',None,None,quality=QualitySettings('aac',16000,64))
        client.processor=AACProcessor(client.quality)
        thread=threading.Thread(target=client.encode_audio)
        thread.start()
        try:
            for _ in range(100):client.captured.put(bytes(960),timeout=2)
            deadline=time.monotonic()+5
            while (client.quality_report.get('input_frames',0)<48000 or not client.quality_drops) and time.monotonic()<deadline:
                if client.captured.empty():client.captured.put(bytes(960))  # keep the worker reporting
                time.sleep(.01)
            self.assertGreaterEqual(client.quality_report['input_frames'],48000)
            self.assertGreater(client.quality_drops,0)
            self.assertLessEqual(client.outbound.qsize(),20)
            self.assertIsNone(client.quality_error)
        finally:
            client.stop();thread.join(2);client.processor.close()
        self.assertFalse(thread.is_alive())

    def test_codec_error_stops_instead_of_sending_unprocessed_audio(self):
        client=HeadsetClient('127.0.0.1',None,None,quality=QualitySettings('aac'))
        client.captured.put(b'bad block')
        client.processor=AACProcessor(client.quality)
        client.encode_audio()
        client.processor.close()
        self.assertTrue(client.stop_event.is_set())
        self.assertIn('AAC',client.quality_error)
        self.assertTrue(client.outbound.empty())

    def test_real_time_codec_output_does_not_starve_paced_sender(self):
        # The codec runs in two child processes, so this paces 10 ms blocks in real time (4 s per rate).
        tone=(4000*np.sin(2*np.pi*440*np.arange(480)/48000)).astype('<i2').tobytes()
        for rate in SAMPLE_RATES:
            with self.subTest(rate=rate):
                settings=QualitySettings('aac',rate,64)
                codec=AACProcessor(settings)
                try:
                    pending=deque();ready=False;started=None;sent=0;max_queue=0
                    begin=time.monotonic()
                    for tick in range(400):
                        time.sleep(max(0,begin+tick*.01-time.monotonic()))
                        pending.extend(codec.push(tone))
                        max_queue=max(max_queue,len(pending))
                        if not ready and len(pending)>=settings.prime_blocks:ready=True;started=tick
                        if ready:
                            self.assertTrue(pending, f'codec starvation at {tick*10} ms')
                            self.assertEqual(len(pending.popleft()),960);sent+=1
                    self.assertIsNotNone(started)
                    self.assertLessEqual(started*10,600)
                    self.assertLessEqual(max_queue,20)
                    self.assertEqual(sent,400-started)
                finally:
                    codec.close()

    def test_close_ends_both_codec_processes(self):
        codec=AACProcessor(QualitySettings('aac',24000,64))
        for _ in range(20):codec.push(bytes(960))
        codec.close()
        self.assertIsNotNone(codec.encoder.poll())
        self.assertIsNotNone(codec.decoder.poll())
        with self.assertRaises(RuntimeError):codec.push(bytes(960))


if __name__=='__main__':unittest.main()
