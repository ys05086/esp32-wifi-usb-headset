# ESP32 Wi-Fi USB Headset

**English** | [한국어](README.ko.md)

**A Wi-Fi ↔ USB audio bridge.** An ESP32-S3 board plugs into any device that supports USB audio as a USB headset, and lets you **hear that device on your computer over Wi-Fi**. In the other direction, your computer's microphone becomes that device's microphone.

It works with anything that recognizes a USB headset, such as a phone, a tablet or another PC. Listen to what the device plays (video, games, music, calls) on the headphones of the computer you are already using, without a cable, and talk to the device through your computer's microphone. Move the board between devices, or keep one board per device, to listen to several devices from one computer in turn.

```text
PC microphone → ESP32 Audio Bridge → Wi-Fi → ESP32 → USB microphone → device
PC headphones ← ESP32 Audio Bridge ← Wi-Fi ← ESP32 ← USB speaker    ← device
```

- [`firmware/`](firmware/): ESP32-S3 firmware. A USB Audio Class 2 headset plus Wi-Fi UDP audio.
- Repository root: the Windows app **ESP32 Audio Bridge**, which connects your computer's microphone and headphones to the board.
- [PROTOCOL.md](PROTOCOL.md): the UDP format the board speaks. Any other program can send and receive it too.

> **⚠️ This is an experimental project.** Wi-Fi and USB packet problems can still make the sound drop out, crackle or degrade now and then. How often depends on the device and the network. Do not rely on it yet for important calls, streams or recordings.

The Windows app, the board's setup page and the install guide are currently in Korean; the labels below are given in Korean with a translation.

## What you need

- An **ESP32-S3-N16R8** board (16 MB flash). It was tested on a board with separate **COM** (flashing and logs) and **USB/OTG** (audio) ports.
- Two USB data cables: COM ↔ computer for flashing, USB ↔ the device you want to hear.
- A Windows computer and a 2.4 GHz Wi-Fi router. The computer can be on the same router by cable or 5 GHz.

## How to use

1. **Flash the firmware:** follow the [firmware install guide](FIRMWARE_INSTALL.md) (Korean) to write the files from a **Firmware** Actions run through the board's COM port. Only needed once.
2. **Set up the board's Wi-Fi:** power the board and join the Wi-Fi network **`ESP32-Headset`** (password **`esp32headset`**) from a phone or computer. Open **http://192.168.4.1**, save your router's name and password, and note the **`router_ip`** the page shows. Then switch back to your usual network. The board keeps the setting, so this is a one-time step.
3. **Get the PC app:** download the `ESP32-Audio-Bridge-Windows` ZIP from an **ESP32 Audio Bridge Windows** Actions run, unzip it and run `ESP32AudioBridge.exe`. Keep the `_internal` folder next to it; Python is not needed.
4. **Plug into the device:** connect the board's **USB** port to the device you want to hear. A USB audio device named **`ESP32 Wi-Fi Headset`** appears on it. Phones usually switch to it on their own; on a Windows PC, pick `스피커(usb uac)` / `마이크(usb uac)` (speaker / microphone) in the sound settings.
5. **Connect from the computer:** in the PC app, enter the `router_ip` under **ESP32 주소** (ESP32 address). Pick your microphone (or an audio interface or virtual cable) under **보낼 소리** (sound to send) and your headphones under **기기 소리** (device sound), then press **연결 시작** (connect).
6. **Listen:** the device's sound now plays on your computer's headphones, and your computer's microphone reaches the device's microphone. To switch devices, move the board or connect to another board's address.

If sound works in only one direction or not at all, change **USB compatibility** on the board's setup page (its router address or 192.168.4.1), save, then unplug **both** the board's USB and COM cables and plug them back in. What worked in testing (your devices may differ):

| Device the board is plugged into | Setting that worked |
|---|---|
| Windows PC | Standard |
| iPhone | Adaptive (with Standard, only the microphone direction worked) |
| Galaxy | Apple |

**Good to know**

- Listen on **headphones**. With speakers, the device's sound reaches your computer's microphone and goes back to the device. Never route the device's sound back into the microphone or a virtual cable.
- The delay is the board buffer (about 60–100 ms) plus the USB buffer (about 30 ms), the PC listening buffer (40/80/120 ms) and the Wi-Fi.
- One board takes one program at a time. Stop the connection before switching programs.
- Audio travels as unencrypted UDP between trusted devices on one router. The setup Wi-Fi password is the same default on every board, so do the first setup where no stranger is nearby.
- If you hear dropouts, press **진단 저장** (save diagnostics) in the PC app (see below).

The code and documentation written for this repository are under the [MIT License](LICENSE) (the firmware: [firmware/LICENSE](firmware/LICENSE)). Third-party software and its notices keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), `licenses/` and [LICENSING.md](LICENSING.md). The review of the full binary distribution terms is still in progress.

## ESP32 Audio Bridge in detail

The **보낼 소리** (sound to send) list shows WASAPI devices first, and also offers virtual cables that only appear through another driver API. The WASAPI/MME/DirectSound/WDM-KS suffix is the access method. To keep the settings of an older version, copy its `settings.json` into the new folder.

The listening buffer is 80 ms by default; choose 40, 80 or 120 ms before connecting. A larger buffer absorbs more late packets at the cost of delay. Late packets are put back in order up to their play deadline, and playback resumes right after a single underrun. A longer gap refills the buffer, and data older than 300 ms is dropped. The app does not yet correct the clock difference of the computer's playback device (the firmware does correct it for the microphone direction).

If you hear dropouts, press **진단 저장** (save diagnostics). It saves, without any audio, a JSON file with device names, sample rates, packet arrival times, reordering, underruns, device errors and the board's counters. "보드 버퍼 부족" (board buffer underrun) concerns the sending path, "듣기 버퍼 부족" (listening buffer underrun) the receiving path. Zeros do not prove that the board's USB audio itself is clean.

Below the address the app shows the board's **current USB mode**, read about every 3 seconds; a saved setting only shows after the board restarts. The query runs on its own thread, apart from the audio. If the board does not answer, the mode shows as unknown, and the diagnostics JSON keeps the last query time and the board's USB transfer counters.
Standard is the Windows-compatible profile and Apple the Apple-compatible one; neither is limited to that operating system. Adaptive is an experimental profile without speaker feedback. Keep whatever already works. USB compatibility concerns the device on the USB side, not the computer on the Wi-Fi side.

The address and device names are saved in `settings.json` next to the executable. Start the app after the audio devices are connected.
The two-way firmware is required; the older microphone-only firmware does not answer this app.
Audio is 48 kHz PCM16, mono in each network direction.
The app checks each audio device's supported formats. Devices without 48 kHz (some capture cards) open at their default rate (e.g. 96 kHz) and go through a streaming resampler, which adds filter delay and an input buffer. The status line shows the actual rates.

## Sending quality · AAC comparison

Under **보내는 음질…** (sending quality), with the connection stopped, choose a setting, save and reconnect. The setting is saved in `settings.json`. The default is plain **원음 PCM** (original PCM); **AAC 압축·복원** (AAC encode and decode) affects only the audio you send.

- Sample rates: 16 / 24 / 32 / 44.1 / 48 kHz.
- AAC-LC target bitrates: 16 / 24 / 32 / 48 / 64 / 96 / 128 / 160 / 192 kbps (up to 96 kbps at 16 kHz, 128 kbps at 24 kHz). The actual average bitrate depends on the input and is recorded in the diagnostics.
- Path: input device → 48 kHz PCM → AAC encode and decode at the chosen rate → 48 kHz PCM → ESP32, on its own codec thread with a bounded queue. The microphone callback never runs AAC or an external program.
- The board's USB and Wi-Fi format stays 48 kHz mono PCM16. This does not reduce the network traffic or change the board's clock, nor does it control the encoder of the app recording on the device, which may compress again.
- Preparing and decoding AAC frames adds tens to hundreds of milliseconds; lower sample rates take longer to fill the same 1,024-sample frame. The AAC/send wait shown in the status is an estimate from the queue and throughput, not the total delay. Settings are locked while connected; muting applies at once, also to AAC output already prepared.

The AAC runtime ships in the app folder, so no separate FFmpeg or Python install is needed. No audio file is saved automatically. `--quality-self-test REPORT.json` checks the bundled encoder and decoder on a synthetic signal without opening a microphone or the network.

22 automated tests pass, covering real AAC encode and decode for all 40 offered settings, output length, bitrate and band limits, unchanged PCM, worker shutdown and errors, and a virtual two-minute send at each of the 5 sample rates. Real PC scheduling, the sound after the ESP32, and long sessions still need checking on hardware. AAC does not fix dropouts caused by buffer underruns.

## Development

```powershell
python -m pip install -r requirements.txt
python -m unittest test_protocol.py
python app.py
python -m pip install pyinstaller==6.22.3
python -m PyInstaller --noconfirm --windowed --onedir --name ESP32AudioBridge app.py
```

`app.py --self-test REPORT.json` creates a hidden window, saves the list of audio devices and exits, without recording or playing.
`app.py --audio-self-test REPORT.json` briefly opens the saved devices on the real worker threads and checks sending against a local UDP test server. The output is silent; nothing is saved or sent to a board. On Windows the worker threads initialize COM before WASAPI and release it after the stream closes.

## What is tested

Unit tests cover packet validation, session separation, sequence loss and reordering, and buffer expiry, plus a regression test that delays packets by up to 60 ms periodically over 30 virtual minutes. These do not stand in for real Wi-Fi and USB hardware or long sessions.
The ESP32 firmware and its hardware test scripts are in [firmware/](firmware/).

This repository holds both the Windows app and the ESP32 firmware. The app ZIP comes from the **ESP32 Audio Bridge Windows** Actions workflow.
