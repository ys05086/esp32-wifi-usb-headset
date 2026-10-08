# Third-party notices / 외부 소프트웨어 고지

ESP32 Call Bridge includes software developed by other authors. Their
copyrights and license terms remain with those authors. Original project
code and documentation are licensed under the MIT License in `LICENSE`.
That grant does not relicense third-party code, libraries, license texts,
or upstream portions embedded in patches. Their terms remain applicable.

이 배포물은 FFmpeg, PyAV, NumPy, sounddevice/PortAudio, soxr, CFFI,
pycparser, Python 및 Tcl/Tk를 사용합니다. 빌드에 따라 Pillow와 PyYAML 등도
포함됩니다. 고지 원문은 동봉된 `licenses/` 폴더에 있습니다.

## 원문과 버전

- `licenses/python-packages/`: 실제 빌드 환경의 패키지에서 복사한 저작권·라이선스 원문.
  NumPy의 LICENSE에는 OpenBLAS 등 번들 구성 요소 고지도 포함됩니다.
  soxr에는 libsoxr, PFFFT 및 LGPL 원문이 포함됩니다.
- `licenses/python-runtime/`: 해당 빌드에 사용한 CPython의 LICENSE 원문.
- `licenses/native-reference/`: PortAudio, Tcl/Tk, FFmpeg 등의 추가 원문과 수집 출처.
  버전 연결이 미확정인 참고 원문은 출처 목록에서 구분합니다.
- `licenses/inventory.json`: 패키지 버전, 고지 파일 SHA-256, 배포된 DLL/PYD 목록과 해시,
  FFmpeg DLL이 보고한 라이선스 및 빌드 설정. 개발자 PC의 개인 경로나 녹음은 포함하지 않습니다.
- `licenses/firmware-reference/`: 별도 ESP32 펌웨어의 주요 구성 요소 고지.
  Windows ZIP에 해당 펌웨어 바이너리가 포함된다는 뜻은 아닙니다.

FFmpeg project: https://ffmpeg.org/ — license and source-distribution information:
https://ffmpeg.org/legal.html . The DLL license functions in the inspected local
build report LGPL version 3 or later. However, its avcodec DLL imports bundled
x264 and x265 DLLs. **This self-report is not evidence that the complete bundle
is LGPL-only or MIT-only.**

## 현재 고지 묶음의 범위와 남은 사항

이 고지 묶음은 수집을 완료한 원문을 제공하는 첫 단계이며, 전체 배포 조건 충족을
선언하지 않습니다. 현재 로컬 FFmpeg의 x264/x265 의존성은 PE import table에서도
확인했습니다. 단순히 DLL을 삭제하면 로딩이 깨질 수 있으며, AAC 기능을 끄는 것만으로
배포물에서 제거되지 않습니다. MIT 기반 배포를 단순화하려면 불필요한 GPL 코덱을
포함하지 않는 FFmpeg/PyAV 구성을 별도로 준비하고 검사해야 합니다.

배포 바이너리에 정확히 대응하는 FFmpeg/soxr 및 기타 해당 구성 요소의 소스와
빌드/재링크 자료 제공은 아직 준비되지 않았습니다. 일반적인 upstream 링크는
그 자료 제공을 대신하지 않습니다. FFmpeg의 추가 네이티브 의존성, 포함된 ASIO
변형 PortAudio, Microsoft 런타임과 펌웨어 하위 구성 요소의 고지도 추가 확인 대상입니다.

외부 라이브러리의 수정·교체 및 그 디버깅에 관해서는 해당 라이선스가 허용하는 권리를
제한하지 않습니다. 이 문서는 제3자 코덱 특허권이나 상표권의 허락을 부여하지 않습니다.

## 펌웨어 수정 사항

ESP-IDF 5.5.1, usb_device_uac 1.3.1, TinyUSB 0.19.0~3을 사용합니다.
UAC/TinyUSB 원본을 프로젝트의 `patch_uac.py`와 `patch_tinyusb.py`로 수정합니다.
변경에는 마이크 FIFO 크기/공급 순서, 스피커 큐 소유권, USB 프로필 선택,
IN FIFO 즉시 채우기, 인터럽트 처리 순서와 진단 계측이 포함됩니다.
원저작권과 라이선스는 그대로 유지됩니다.

펌웨어 소스와 수정 스크립트:
이 저장소의 [firmware/](firmware/)
