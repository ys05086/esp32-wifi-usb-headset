"""Known signals only: simultaneously validate USB mic and speaker over Wi-Fi.

Run on Windows with BOTH board ports attached. Never opens the physical mic.
python duplex_hardware.py BOARD_IP RESULT_DIRECTORY
Requires numpy, sounddevice, soundfile.
"""
import argparse, ctypes, json, secrets, socket, struct, time
from contextlib import ExitStack
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

p = argparse.ArgumentParser()
p.add_argument('host'); p.add_argument('output', type=Path)
p.add_argument('--shared', action='store_true')
p.add_argument('--combined', action='store_true')
p.add_argument('--raw-capture', action='store_true')
a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
devices = sd.query_devices(); apis = sd.query_hostapis()
ids = [i for i, d in enumerate(devices) if 'usb uac' in d['name'].lower()
       and apis[d['hostapi']]['name'] == 'Windows WASAPI']
inputs = [i for i in ids if devices[i]['max_input_channels']]
if a.raw_capture:
    inputs = [i for i,d in enumerate(devices) if 'usb uac' in d['name'].lower() and d['max_input_channels'] and apis[d['hostapi']]['name']=='Windows WDM-KS']
outputs = [i for i in ids if devices[i]['max_output_channels']]
assert len(inputs) == len(outputs) == 1, (inputs, outputs)
t = np.arange(48000 * 6) / 48000
def signal(hz):
    envelope = np.clip(np.minimum((t-1)/.02, (4-t)/.02), 0, 1)
    return np.rint(1600 * envelope * np.sin(2*np.pi*hz*t)).astype('<i2')
mic = signal(330)
speaker = np.column_stack([signal(660), signal(880)])
captured = []; returns = {}; errors = []; position = 0; acks = []
def capture(data, frames, timing, status):
    captured.append(data.copy().reshape(-1))
    if status: errors.append(str(status))
def play(data, frames, timing, status):
    global position
    data.fill(0); n = min(frames, max(0, len(speaker)-position))
    if n: data[:n] = speaker[position:position+n]; position += n
    if status: errors.append(str(status))
def both(indata, outdata, frames, timing, status):
    capture(indata, frames, timing, status); play(outdata, frames, timing, status)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect((a.host, 49152)); sock.setblocking(False)
session = secrets.randbelow(2**32-1)+1
ctypes.windll.winmm.timeBeginPeriod(1)
try:
    with ExitStack() as stack:
        options=dict(samplerate=48000, dtype='int16', blocksize=480, extra_settings=sd.WasapiSettings(exclusive=not a.shared))
        if a.combined:
            stack.enter_context(sd.Stream(device=(inputs[0],outputs[0]), channels=(1,2), callback=both, **options))
        else:
            input_options = dict(options)
            if a.raw_capture: input_options.pop('extra_settings')
            stack.enter_context(sd.InputStream(device=inputs[0], channels=1, callback=capture, **input_options))
            stack.enter_context(sd.OutputStream(device=outputs[0], channels=2, callback=play, **options))
        start = time.perf_counter()
        for seq in range(600):
            remaining = start + seq*.01 - time.perf_counter()
            if remaining > 0: time.sleep(remaining)
            sock.send(struct.pack('<4sIIHH', b'VSM1', session, seq, 480, 2) + mic[seq*480:(seq+1)*480].tobytes())
            while True:
                try: data = sock.recv(2048)
                except BlockingIOError: break
                if len(data) == 24 and data[:4] == b'VSA2': acks.append(struct.unpack('<4sIIIII', data)[1:])
                elif len(data) == 976 and data[:4] == b'VSR1':
                    _, sid, number, frames, flags = struct.unpack_from('<4sIIHH', data)
                    assert sid == session and frames == 480 and flags == 0
                    returns[number] = np.frombuffer(data[16:], dtype='<i2').copy()
        sock.send(struct.pack('<4sIIHH', b'VSM1', session, 600, 0, 1)); time.sleep(.4)
finally:
    sock.close(); ctypes.windll.winmm.timeEndPeriod(1)
y = np.concatenate(captured)
z = np.concatenate([returns.get(i, np.zeros(480, dtype=np.int16)) for i in range(max(returns, default=-1)+1)])
def levels(audio):
    v = audio[96000:144000].astype(float)
    return {str(hz): round(float(abs(np.sum(v*np.exp(-2j*np.pi*hz*np.arange(len(v))/48000)))*2/max(1,len(v))), 2)
            for hz in [330, 660, 880]}
result = {'mic_levels': levels(y), 'return_levels': levels(z), 'acks': len(acks),
          'last_ack': acks[-1] if acks else None, 'return_packets': len(returns),
          'return_missing': max(returns, default=-1)+1-len(returns), 'audio_errors': errors,
          'mic_tail_peak': int(np.max(np.abs(y[-4800:].astype(int)))),
          'mic_max_step': int(np.max(np.abs(np.diff(y[96000:144000].astype(int))))),
          'return_max_step': int(np.max(np.abs(np.diff(z[96000:144000].astype(int))))) if len(z)>144000 else None}
result['pass'] = bool(acks) and len(returns)>400 and not errors and result['mic_tail_peak']==0 \
    and result['mic_levels']['330']>1000 and result['mic_levels']['660']<10 and result['mic_levels']['880']<10 \
    and result['return_levels']['330']<10 and result['return_levels']['660']>400 and result['return_levels']['880']>400 \
    and result['mic_max_step']<400 and result['return_max_step'] is not None and result['return_max_step']<400
sf.write(a.output/'usb-microphone.wav', y, 48000, subtype='PCM_16')
sf.write(a.output/'wifi-return.wav', z, 48000, subtype='PCM_16')
(a.output/'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['pass'] else 1)
