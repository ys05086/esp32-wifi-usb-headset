# ESP32 firmware installation · Windows

**English** | [한국어](FIRMWARE_INSTALL.ko.md)

> **Experimental project:** intermittent Wi-Fi or USB problems can cause dropouts, crackling or degraded audio. Results depend on the device and network. Do not rely on this version for important calls, streams or recordings.

This firmware targets the **ESP32-S3-N16R8 with 16 MB flash**. The tested board has separate **COM** and **USB** ports. Do not install these images on a regular ESP32 or a board with a different flash configuration. This is the two-way USB headset firmware; intermittent audio issues are still being investigated.

## Easiest method: Board Setup

The PC app ZIP includes `ESP32BoardSetup.exe`, which installs firmware and configures Wi-Fi in one window. Connect the board's **COM** port to the PC, open **Board setup…** from Audio Bridge and press **Install firmware**. Choose **English** in Audio Bridge before opening Board Setup if needed.

![Board Setup in English, with example settings](docs/images/board-setup-en.png)

The installer uses the ZIP's `firmware/` folder. It writes the bootloader, partition table and application separately, preserves the settings (NVS) region unless **Reset settings too** is selected, and verifies each written region with MD5. After installation, save your router Wi-Fi settings in the same window and check the board's own Wi-Fi name and password.

The remaining sections describe manual flashing with esptool, useful if you cannot use the Windows setup program or it cannot enter download mode automatically.

## Prepare the board and download firmware

- **COM → PC:** USB-serial connection for installation and logs.
- **USB / OTG → audio device:** USB audio connection after installation.
- Use USB data cables. Disconnect the USB/OTG audio cable from the other device while flashing manually.
- Download and extract the `esp32-wifi-usb-headset-firmware` artifact from a successful [ESP32 Audio Bridge Windows workflow run](https://github.com/ys05086/esp32-wifi-usb-headset/actions/workflows/windows.yml). These are the same files as the PC app ZIP's `firmware/` folder. GitHub requires signing in to download Actions artifacts.
- Check the run's source commit against `source-commit.txt`. A successful build alone does not establish audio quality.

| File | Purpose | Flash address |
|---|---|---|
| `esp32-wifi-usb-headset.bin` | Merged image for first installation | `0x0` |
| `esp32-wifi-usb-headset-app.bin` | Application update for an existing board with the same partition layout | `0x10000` |
| `flasher_args.json` | Flash settings and partition addresses for this build | Do not flash |
| `SHA256SUMS.txt`, `source-commit.txt`, `dependencies.lock` | Integrity and version information | Do not flash |

Open PowerShell in the firmware folder and compare these hashes with `SHA256SUMS.txt`:

```powershell
Get-FileHash .\esp32-wifi-usb-headset.bin -Algorithm SHA256
Get-FileHash .\esp32-wifi-usb-headset-app.bin -Algorithm SHA256
```

## Install esptool and identify the port

The packaged PC apps do not need Python. Manual flashing below requires Python 3.10 or later. These commands install esptool into a virtual environment in the current folder:

```powershell
py -3 -m venv .flash-tools
.\.flash-tools\Scripts\python.exe -m pip install esptool==5.1.0
```

If `py` is unavailable but `python` works, replace `py -3` with `python` in the first command. In Device Manager → **Ports (COM & LPT)**, find the COM port that appears when you connect the board. Replace the example `COM7` below with your port. Close any serial monitor using it.

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 flash-id
```

Confirm the chip is ESP32-S3 and flash capacity is 16 MB. If no COM port appears, check the data cable and the board's COM connector, then install the driver supplied by the manufacturer of the board's actual USB-serial chip. The tested board uses CH343.

## Back up the existing flash

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 --baud 460800 read-flash 0x0 0x1000000 board-backup.bin
```

Confirm the backup completes and is 16,777,216 bytes. It may contain Wi-Fi credentials; keep it private and exclude it from distribution ZIPs and GitHub. Use another filename if a backup already exists.

## First installation

Use this for a new board or when replacing different firmware. Writing the merged image can overwrite existing partitions and settings.

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 --baud 460800 write-flash --flash-mode dio --flash-freq 40m --flash-size 16MB 0x0 .\esp32-wifi-usb-headset.bin
```

## Update an existing board

Use this only for a board already running this project with the same partition layout. Confirm the app address is `0x10000` in the release's `flasher_args.json`. Writing only the app preserves Wi-Fi and USB mode settings in NVS. Do not use this procedure unchanged if the new firmware changes the partition layout.

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 --baud 460800 write-flash 0x10000 .\esp32-wifi-usb-headset-app.bin
```

After writing and hash verification succeed, unplug **both USB and COM cables**, then reconnect. Do not write the application-only image at `0x0` or the merged image at `0x10000`. A normal update does not require erasing the whole flash.

If connection fails, hold **BOOT**, briefly press and release **RESET**, then release BOOT to enter download mode and retry. The board is not an audio device while in download mode. Keep the cable connected during writing. If transfer errors recur, retry with `--baud 115200`.

## Connect Wi-Fi and USB audio

1. Keep COM connected to the PC and save your **2.4 GHz router's** name and password in Board Setup. Its address appears after connecting. Without the Windows program, use a serial monitor at 115200 bps: send `@set {"wifi_ssid":"YourRouter","wifi_password":"YourPassword"}`, then `@get` to read `router_ip`.
2. The board's own Wi-Fi is named `ESP32-Headset-XXXX` and gets a random password on first boot. Read it in Board Setup or the `ap_password` field from `@get`. Devices on that Wi-Fi can also change router and USB mode settings at `http://192.168.4.1`. The router-side page is status-only.
3. Enter the board address in Audio Bridge. The PC may use Ethernet or 5 GHz Wi-Fi on the same LAN.
4. Select and save **USB mode** in Board Setup. Standard, Apple and Adaptive are compatibility profiles, not automatic OS detection. Disconnect both USB and COM power, then reconnect to apply the saved mode.
5. Connect **USB/OTG** to the device whose audio you want to use. Adaptive has worked in both directions on the tested iPhone, with intermittent microphone dropouts still observed. Standard provided microphone input but no playback on that iPhone. Test your own device.
6. In Audio Bridge, select the input, headphones and board address, then press **Connect**. Record on the USB device to test the microphone direction, and play sound on it to test the return direction. A connected status alone does not prove every app on the device is using USB audio.

Lightning iPhones need an adapter supporting USB host operation, and may need external power. Do not assume a simple Lightning–USB-C charging cable provides this connection. Use a data/host connection suitable for the device.

See the official [Espressif esptool command reference](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html). For building from source, see the [firmware development guide](firmware/README.md), currently in Korean.
