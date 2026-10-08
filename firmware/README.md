# ESP32-S3 펌웨어 · Wi-Fi ↔ USB 오디오 브리지

ESP32-S3-N16R8이 Wi-Fi로 받은 PCM을 **USB 마이크**로 내보내고, **USB 스피커**로 받은 기기 소리를 Wi-Fi로 돌려준다.
보드 USB는 USB 헤드셋을 인식하는 **휴대폰/태블릿/PC 등**에 꽂고, 그 기기의 소리를 같은 네트워크의 컴퓨터에서 듣는다.
보내는 쪽은 이 저장소의 Windows 앱 ESP32 Call Bridge이거나, [PROTOCOL.md](../PROTOCOL.md) 형식으로 보내는 어떤 프로그램이든 된다.
한 번에 한 클라이언트가 연결된다.

## 바로 연결하기

1. 보드 전원을 켜고 Wi-Fi **ESP32-Headset**, 비밀번호 **esp32headset**으로 연결한다.
2. 브라우저에서 **http://192.168.4.1**을 열고 사용하는 2.4GHz 공유기의 SSID와 비밀번호를 저장한다.
3. 페이지의 `router_ip`가 `0.0.0.0`에서 실제 주소로 바뀌면 기록한다. 보내는 기기도 해당 공유기로 다시 연결한다.
4. 보내는 프로그램에 그 IP를 넣고 연결한다.
5. 보드 **USB** 포트를 소리를 들을 기기에 연결한다. PC 시험에서는 **마이크(usb uac)** / **스피커(usb uac)**를 선택한다.
   보드의 수신 카운터는 보드까지의 도착만 증명하며, 통화 상대의 수신까지 증명하지 않는다.

공유기 설정 없이 보드 AP에 직접 연결한 채 `192.168.4.1`로 보내는 것도 가능하다.
이 AP는 인터넷을 제공하지 않으므로 인터넷 통화에는 같은 공유기 사용을 권장한다.
Wi-Fi 설정은 보드 NVS에 저장된다. 설정 페이지는 로컬 네트워크용이며 인터넷에 포트를 열지 않는다.
설정 AP의 비밀번호는 모든 보드에 같은 기본값이다. 근처의 누구나 설정 페이지에 들어올 수 있으므로 공유기 설정을 마친 뒤 보드를 신뢰할 수 있는 장소에서 쓴다.

설정 페이지의 **USB compatibility**는 USB로 꽂은 기기의 호환성 설정이다. Wi-Fi 클라이언트의 OS와는 무관하다.
기본 Standard는 4바이트 16.16 피드백(Windows 호환), Apple은 3바이트 10.14 피드백(Apple 호환)이다. 운영체제 전용 모드가 아니며, Apple 설정으로 Galaxy가 작동한 사례도 있다. 이미 작동하는 설정을 유지한다.
저장 후 USB와 COM을 모두 분리해 전원을 끄고 다시 연결한다. `/status`의 `usb_mode`가 현재 적용값이다.

## 전송 형식과 버퍼

형식은 [PROTOCOL.md](../PROTOCOL.md)에 있다. UDP 49152, 패킷당 10ms / 480프레임 / 48kHz mono PCM16LE.
300ms 동안 패킷이 없으면 무음으로 돌아가고 버퍼를 비운다. 중복/오래된 순서는 거부한다.

- 70ms를 모은 뒤 재생하고, 이후 매초 그 1초 동안의 최저 수위를 60~80ms 안으로 맞춘다.
  벗어나면 다음 1초 동안 10ms 블록마다 1프레임을 더(또는 덜) 가져와 480프레임으로 보간한다(0.2%, 약 3센트).
  보내는 컴퓨터와 꽂은 기기의 시계 차이, 빈 USB 패킷 때문에 버퍼가 조금씩 차오르는 것을 이것이 흡수한다.
- 200ms 상한(최근 120ms만 남김)은 순간적인 몰림에 대비한 비상용이다.
- 꽂은 기기가 USB 마이크를 닫았다 다시 열면(100ms 넘게 읽지 않음) 그동안 쌓인 소리를 버리고 최근 70ms부터 재생한다.
  아직 아무것도 재생하지 않은 시점이라 들리는 잘림이 아니다.
- `/status`: `input_level_removed_frames`·`input_level_added_frames`는 보정으로 빼고 더한 프레임 수, `input_level_step`은 현재 보정 방향(+1 줄임, -1 늘림), `input_start_flushed_frames`는 다시 열 때 버린 프레임 수, `input_trimmed_frames`는 비상 상한으로 버린 프레임 수다.

반환(기기 소리): USB 스테레오 입력을 모노 평균으로 바꿔 480프레임씩 보낸다. 현재 소유자의 IP/포트로만 보내며, 입력이 300ms 끊기거나 세션/소유자가 바뀌면 이전 소리를 버린다.
보내는 기기에서는 이어폰으로 들어서, 반환 소리가 다시 마이크로 들어가지 않게 한다.

## 동작

- USB Audio Class 2, 48,000 Hz, signed PCM16 LE. 마이크 모노 + 스피커 스테레오.
- 이름: `ESP32 Wi-Fi Headset`. 전원을 켜거나 USB를 연결한 직후에는 무음.
- BOOT(GPIO0)를 **부팅 후** 한 번 누르면 660/880 Hz 확인음 네 번을 4초 안에 전송.
- 확인음 최대 진폭은 약 -26 dBFS. USB 스트림이 멈춰도 벽시계 기준으로 종료한다.
- 사인파는 USB 시작 전에 미리 계산하며, 실시간 콜백은 정수 테이블 조회만 한다.
  COM 로그의 `max render`로 10ms 블록 처리 예산을 넘는지 확인할 수 있다.
- COM 포트 115200 baud에서 `t`도 같은 확인음, `s`는 확인음을 멈추고 Wi-Fi 입력으로 돌아간다.
- USB 스피커 입력은 Wi-Fi 반환 전용이며 USB 마이크에 섞지 않는다. USB 마이크에는 평소 Wi-Fi PCM, BOOT를 누른 4초 동안 확인음이 나온다.
- RGB LED를 제어하지 않는다. PSRAM은 사용하지 않는다.

## 연결과 검사

1. 보드의 **COM** 포트: PC에서 백업·펌웨어 업로드·로그에 사용한다.
2. 보드의 **USB / OTG** 포트: USB 마이크로 인식시키려는 기기에 연결한다.
3. Windows에서 먼저 입출력 목록을 확인한다. 제품 문자열은 `ESP32 Wi-Fi Headset`이지만
   Windows 오디오 입력 이름은 인터페이스 문자열을 사용해 **`마이크(usb uac)`**로 표시된다.
4. 휴대폰 시험 때는 PC 케이블을 분리하고 USB/OTG 포트를 휴대폰에 연결한다.
5. 녹음 앱의 녹음을 시작한 후 BOOT를 짧게 눌러 확인음이 녹음되는지 확인한다.
6. 통화에서 상대에게 확인음이 전달되는지 확인한다. 통화 앱의 잡음 제거가 확인음을 없애면 비교 시험 동안 해당 처리를 끈다.
7. 꽂은 기기에서 USB 입출력을 사용하고, 컴퓨터에서는 이어폰으로 듣는다. 반환 소리가 마이크로 다시 유입되지 않는지 확인한다.
8. PC 실물 양방향 검사는 `python tests/duplex_hardware.py BOARD_IP RESULT_DIRECTORY`로 한다. 보드 USB 입출력만 열어 서로 다른 시험음으로 전달과 분리를 확인한다.

`USB`, `COM` 표시는 보드 제조사마다 다를 수 있다. 시험한 보드의 COM은 CH343이다.
GPIO0 외의 핀에는 주변 장치를 연결하지 않는다. BOOT를 누른 채 리셋하면 다운로드 모드로 들어간다.

## 빌드

이 `firmware/` 디렉터리에서 직접 작성한 코드와 문서는 [MIT License](LICENSE)로 제공한다. 외부 컴포넌트 및 패치에 포함된 upstream 원문은 원래 라이선스를 유지한다.
외부 구성 요소의 고지와 수정 사항은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있다. Actions 배포물에는 ESP-IDF와 해결된 관리 컴포넌트의 최상위 라이선스 원문도 `licenses/`에 포함된다. 하위 구성 요소 전체의 배포 조건 검토가 끝났다는 뜻은 아니다.

ESP-IDF **v5.5.1**, `espressif/usb_device_uac` **1.3.1**.

구성 단계에서 `patch_uac.py`가 고정 버전의 마이크 FIFO를 보정한다.
미병합 [upstream PR #764](https://github.com/espressif/esp-iot-solution/pull/764)의 버퍼 확장과 시작 시 무음 채우기를 검토해 반영했다. 원본 해시가 다르면 빌드를 중단한다.
FIFO는 62패킷(약 6KB)이다. 보충 요청 뒤 FIFO가 비기까지 약 25ms 여유가 있어, 공급 작업이 늦어도 빈 USB 패킷이 나가지 않게 한다.
시작할 때 FIFO의 절반(약 31ms)을 무음으로 채운다.

```sh
cd firmware
idf.py set-target esp32s3
idf.py build
idf.py merge-bin
```

`.github/workflows/firmware.yml`은 `firmware/` 변경 또는 수동 실행에서 호스트 시험과 펌웨어 빌드를 돌린다.
결과물 `esp32-wifi-usb-headset.bin`은 최초 설치용 주소 `0x0` 병합 이미지, `esp32-wifi-usb-headset-app.bin`은 기존 보드 업데이트용으로 `0x10000`에 기록해 NVS의 공유기 설정을 보존한다. `flasher_args.json`의 오프셋을 확인한다.
artifact의 `source-commit.txt`와 `SHA256SUMS.txt`를 함께 보관한다. 설치 절차는 [FIRMWARE_INSTALL.md](../FIRMWARE_INSTALL.md)에 있다.

업로드 전에 보드의 칩/16MB 플래시를 확인하고, 기존 플래시 전체를 로컬에 백업한다.
백업은 기존 네트워크 설정 등을 포함할 수 있으므로 저장소와 배포 ZIP에 포함하지 않는다.
이 프로토타입은 Espressif 예제 USB VID/PID를 사용하는 개발용이며 제품용 식별자로 취급하지 않는다.

```sh
python -m esptool --chip esp32s3 --port COM7 flash-id
python -m esptool --chip esp32s3 --port COM7 --baud 921600 read-flash 0 0x1000000 original-16mb.bin
python -m esptool --chip esp32s3 --port COM7 --baud 460800 write-flash 0x10000 esp32-wifi-usb-headset-app.bin
```

`COM7`은 예시다. TinyUSB 피드백 콜백과 USB endpoint descriptor 크기를 함께 선택하며, 컴파일 기본값을 모든 호스트에 강제하지 않는다.

## 근거

- [Espressif USB Audio Class](https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_device/usb_device_uac.html)
- [고정한 UAC 컴포넌트](https://components.espressif.com/components/espressif/usb_device_uac/versions/1.3.1/readme)
- [S3 USB 연결](https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html)


## Adaptive 실험 모드

보드 웹페이지의 **USB compatibility → Adaptive (experimental, no feedback)**를 저장한 뒤 USB와 COM 전원을 모두 끊었다 다시 연결한다. `/status`의 `usb_mode: adaptive`, `usb_feedback_enabled: false`, `usb_out_sync: adaptive`로 적용 여부를 확인한다. 저장만으로 현재 USB 구성을 바꾸지는 않는다. 기존 Standard와 Apple 설정은 유지되며 같은 화면에서 되돌릴 수 있다.

이 프로필은 UAC2 스피커 OUT을 adaptive로 설정하고 피드백 IN 0x81을 제거한다. 구성 길이, 스피커 인터페이스의 엔드포인트 개수, TinyUSB 내부 함수 길이를 함께 변경한다. 마이크 IN 0x82, 샘플 수 조절, Clock/Terminal 트리는 기존과 같다. 스피커는 수신 콜백/큐를 통해 **실제 수신한 프레임 수만큼** Wi-Fi로 전달하므로 별도 48kHz 타이머나 로컬 DAC 클럭으로 소비하지 않는다. 고정 길이 480프레임 반환 패킷 조립은 그대로다. PC 재생 장치의 클럭 차이까지 해결하는 기능은 아니다.

핀 고정한 TinyUSB의 `examples/device/uac2_headset/src/usb_descriptors.h`의 adaptive OUT/비동기 IN 구성을 참고했다. 라이브러리 업그레이드나 UAC1 전환은 포함하지 않는다. 실제 iPhone 인식·출력·장시간 마이크 연속성은 아직 검증 전이다. 2분 이상 동일한 소스를 송신하며 양방향 오디오, 마이크 재시도, 버퍼 잘림, 피드백 전송 0건을 함께 확인한다. 실패하면 Apple로 복구한다.

`tests/adaptive_descriptor_test.py`는 실제 컴포넌트 디스크립터/콜백을 호스트 C 컴파일러로 실행해 세 프로필의 길이와 엔드포인트, 마이크·Clock 보존, 손상 데이터 거부를 검증한다. 정상 열거 및 음질의 하드웨어 검증을 대체하지 않는다.


## 마이크 공급 순서 보정 (USB 상태 버전 4)

USB FIFO가 최소 패킷(현재 94바이트)보다 작으면, 패킷 크기를 결정하기 전에 준비된 음성 블록을 보충하는 콜백을 먼저 호출한다. 일반 구간의 전송 후 보충 기준, FIFO 크기, 47/48/49프레임 조절과 네트워크 버퍼 제한은 유지한다. 생산이 늦어 아직 블록이 없다면 이 보정만으로 복구할 수 없다. 짧은 마이크 PCM 공급 작업의 우선순위는 9, USB 관리 작업은 8, 스피커 작업은 6이다. 실제 기기의 실행 지연 개선은 별도 확인이 필요하다.

`/status.usb.mic_prefill_attempts`는 빈 패킷이 예상되어 사전 보충을 시도한 횟수, `mic_prefill_recovered`는 최소 패킷 이상으로 회복한 횟수다. 일반 패킷에는 이 카운터용 잠금을 추가하지 않는다. 기존 `mic.zero`, 재시도/실패, 네트워크 버퍼 잘림은 계속 집계한다.

## 선택적 상세 진단

기본 빌드는 상세 추적을 끄며 `/status.usb.mic_trace.enabled=false`로 표시한다. 이때 상세 진단용 시계 읽기·공유 잠금·사건 기록을 하지 않고, 꺼진 측정을 0건의 정상 결과로 표시하지 않는다. `idf.py -DVS_MIC_TRACE_DETAILED=ON build`로 별도 진단 빌드를 만들 수 있다. 활성화하면 아래 필드가 포함된다.

`/status.usb.mic_trace`는 원음 없이 숫자 상태와 최근 16개 사건을 저장한다. 메모리 할당·JSON 생성은 HTTP 작업에서만 하며 USB/음성 작업에는 고정 크기 카운터·링 버퍼만 사용한다. 계측 자체의 시간 비용은 있으므로 상세 추적이 켜진 빌드와 꺼진 빌드의 음질·실행 시간을 동일한 조건으로 간주하지 않는다.

- `kind=1`: 전송 예약 전에 선택한 PCM 길이가 0. `fifo_bytes`는 패킷 크기 계산 직전 FIFO 잔량이다.
- `kind=2`: 성공한 USB 완료가 0바이트. 이때 `fifo_bytes/requested_bytes`는 직전 예약의 값이며, 완료 순간 FIFO를 다시 읽은 값은 아니다. `requested_bytes>0`이면 예약 시점의 빈 데이터와 구분한다.
- `kind=3`: 공급 작업의 깨우기 지연 또는 블록 준비 시간이 5ms를 넘었다. 이것만으로 음성 손실을 뜻하지 않는다.
- `staged_bytes`: 다음 USB FIFO 채우기를 위해 이미 준비된 블록. `source_frames`는 가장 최근 Wi-Fi 수신/읽기 시점의 네트워크 버퍼 잔량이다. 다른 작업의 값이므로 완전히 동시적인 버퍼 스냅샷으로 간주하지 않는다.
- `phase`: 0 대기/미상, 1 공급 요청됨, 2 블록 준비 중, 3 블록 준비됨. `request_age_us`는 아직 처리 중인 요청의 경과 시간, `wake_us/render_us`는 최근 공급 작업의 깨우기/블록 준비 시간이다.
- `at_us`: 보드 부팅 기준 64비트 마이크로초, `stream/stream_age_us`: 마이크 열림 횟수/경과 시간. `mic_active/speaker_active`로 시작·정지 주변 사건을 구분한다. 이것은 PC/폰 녹음 파일의 타임스탬프가 아니다.
- `event_count/overwritten_events`: 전체 사건 수와 링에서 밀려난 수. HTTP 응답은 남아 있는 사건을 오래된 순서로 출력한다. `planned_empty/completed_empty`는 별도 누적 수치다.

저장 후 읽어도 사건이 남지만 보드를 재부팅하면 사라진다. 시험 중 2초마다 상태를 저장하면 링 용량을 넘어선 사건도 보존하기 쉽다. 오디오 패킷 데이터나 Wi-Fi 암호는 이 진단에 포함하지 않는다.
