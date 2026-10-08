# ESP32 펌웨어 설치 · Windows

대상 보드는 **ESP32-S3-N16R8 / 16 MB 플래시**, 현재 시험 보드는 **COM과 USB 포트가 따로 있는 모델**입니다. 일반 ESP32나 다른 플래시 구성에 그대로 설치하지 마세요. 이 펌웨어는 양방향 USB 헤드셋 실험 버전이며 간헐적인 끊김을 개선 중입니다.

## 준비와 펌웨어 받기

- **COM → PC**: 펌웨어 설치·로그용 USB 직렬 포트.
- **USB / OTG → 소리를 들을 기기**: 설치 후 오디오용 포트.
- 데이터 전송이 되는 USB 케이블을 사용합니다. 설치할 때는 통화를 끝내고 보드의 USB/OTG 쪽은 분리합니다.
- [Firmware Actions](https://github.com/ys05086/esp32-wifi-usb-headset/actions/workflows/firmware.yml)의 성공한 실행에서 `esp32-wifi-usb-headset-firmware` artifact를 내려받아 압축을 풉니다. Actions artifact를 받으려면 GitHub 로그인이 필요합니다. PC 앱 ZIP에는 펌웨어가 들어 있지 않습니다.
- 실행의 소스 커밋과 `source-commit.txt`를 확인합니다. 최신 빌드 성공만으로 음질 검증이 끝난 것은 아닙니다.

| 파일 | 용도 | 기록 주소 |
| --- | --- | --- |
| `esp32-wifi-usb-headset.bin` | 최초 설치용 병합 이미지 | `0x0` |
| `esp32-wifi-usb-headset-app.bin` | 같은 파티션 구성을 쓰는 기존 보드의 앱 업데이트 | `0x10000` |
| `flasher_args.json` | 해당 빌드의 플래시 설정과 파티션 주소 확인 | 기록하지 않음 |
| `SHA256SUMS.txt`, `source-commit.txt`, `dependencies.lock` | 파일 검증·버전 확인 | 기록하지 않음 |

펌웨어 폴더에서 PowerShell을 열고 다음 해시를 `SHA256SUMS.txt`와 비교합니다.

```powershell
Get-FileHash .\esp32-wifi-usb-headset.bin -Algorithm SHA256
Get-FileHash .\esp32-wifi-usb-headset-app.bin -Algorithm SHA256
```

## 설치 도구와 포트 확인

PC 앱 실행에는 Python이 필요 없지만, 아래 수동 설치 방법은 Python이 필요합니다. Python 3.10 이상을 준비하고 다음을 실행합니다. 설치 도구는 이 폴더의 가상환경에만 설치됩니다.

```powershell
py -3 -m venv .flash-tools
.\.flash-tools\Scripts\python.exe -m pip install esptool==5.1.0
```

`py`가 없고 `python`이 정상 작동한다면 첫 줄의 `py -3`을 `python`으로 바꿉니다. 장치 관리자 → **포트(COM 및 LPT)**에서 보드를 꽂을 때 나타나는 COM 번호를 확인합니다. 아래 `COM7`은 예시이며 자신의 번호로 바꿉니다. 직렬 모니터는 닫습니다.

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 flash-id
```

ESP32-S3와 16 MB 플래시가 확인되어야 합니다. COM이 나타나지 않으면 케이블과 보드의 COM 포트를 확인하고, 보드에 실제 탑재된 USB 직렬 칩의 제조사 드라이버를 설치합니다. 시험 보드는 CH343입니다.

## 기존 내용 백업

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 --baud 460800 read-flash 0x0 0x1000000 board-backup.bin
```

백업이 완료되고 파일 크기가 16,777,216바이트인지 확인합니다. 백업에는 Wi-Fi 설정 등이 들어갈 수 있으므로 개인 보관하고 배포 ZIP이나 GitHub에는 올리지 않습니다. 기존 백업이 있으면 다른 파일명을 사용합니다.

## 최초 설치

새 보드이거나 다른 펌웨어에서 넘어오는 경우입니다. 병합 이미지 기록은 기존 파티션과 설정 영역을 덮어쓸 수 있습니다.

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 --baud 460800 write-flash --flash-mode dio --flash-freq 40m --flash-size 16MB 0x0 .\esp32-wifi-usb-headset.bin
```

## 기존 보드 업데이트

이 프로젝트의 같은 파티션 구성을 사용하는 보드에만 적용합니다. 배포물의 `flasher_args.json`에서 앱 주소가 `0x10000`인지 확인합니다. 앱 영역만 기록하므로 NVS의 Wi-Fi·USB 모드 설정을 보존합니다. 파티션 구성 변경이 있는 배포물에는 이 방법을 그대로 사용하지 않습니다.

```powershell
.\.flash-tools\Scripts\python.exe -m esptool --chip esp32s3 --port COM7 --baud 460800 write-flash 0x10000 .\esp32-wifi-usb-headset-app.bin
```

기록과 해시 검증이 성공한 뒤 보드의 **USB와 COM 케이블을 모두 뺐다가** 다시 연결합니다. 앱 업데이트 파일을 `0x0`에 쓰거나 병합 이미지를 `0x10000`에 쓰지 않습니다. 일반 업데이트에 전체 플래시 삭제는 필요 없습니다.

연결 단계에서 실패하면 **BOOT를 누른 채 RESET을 짧게 누르고 BOOT를 놓아** 다운로드 모드에 진입한 뒤 재시도합니다. 다운로드 모드에서는 오디오 장치로 동작하지 않습니다. 기록 중 케이블을 빼지 마세요. 전송 오류가 반복되면 `--baud 115200`으로 낮춰 재시도합니다.

## Wi-Fi와 USB 헤드셋 연결

1. 전원을 켜고 `ESP32-Headset` Wi-Fi에 연결합니다. 비밀번호는 `esp32headset`입니다. 모든 보드에 같은 기본값이라, 설정은 근처에 모르는 사람이 없는 곳에서 합니다.
2. 브라우저에서 `http://192.168.4.1`을 열고 **2.4 GHz 공유기** 이름과 비밀번호를 저장합니다. 보드 AP의 ‘인터넷 없음’ 표시는 설정 단계에서는 정상입니다.
3. `router_ip`에 나타난 주소를 기록한 뒤 PC/휴대폰을 원래 네트워크로 돌립니다. PC는 동일 LAN의 유선 또는 5 GHz를 써도 됩니다. PC 앱에는 `192.168.4.1` 대신 기록한 공유기 주소를 입력합니다.
4. 설정 페이지의 **USB compatibility**를 선택하고 저장합니다. Standard/Apple/Adaptive는 호환성 프로필이며 OS 자동 감지가 아닙니다. 저장 후 USB와 COM 전원을 모두 끊었다 다시 켜야 적용됩니다.
5. **USB/OTG 포트**를 소리를 들을 기기에 연결합니다. 현재 iPhone 시험에서는 Adaptive로 양방향 통신을 확인했지만 간헐적인 마이크 끊김이 남아 있습니다. Standard는 시험한 iPhone에서 입력은 되지만 출력이 나오지 않았습니다. 기기별로 확인하세요.
6. PC 앱에서 마이크와 헤드폰, 보드 IP를 선택하고 연결합니다. 꽂은 기기에서 녹음으로 마이크 방향을, 소리 재생으로 컴퓨터에서 들리는지를 각각 확인합니다. 앱에 ‘연결됨’이 표시되는 것만으로 기기의 각 앱이 USB 오디오를 쓰는지까지 확인되지는 않습니다.

Lightning iPhone은 USB 호스트 연결을 지원하는 어댑터와 필요시 외부 전원이 필요합니다. 단순 Lightning–USB-C 충전 케이블로 연결되는 것으로 가정하지 마세요. 꽂을 기기에 맞는 USB 데이터/호스트 연결을 사용합니다.

공식 명령 안내: [Espressif esptool](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html). 직접 빌드할 때는 [펌웨어 소스와 빌드 안내](firmware/README.md)를 참고하세요.
