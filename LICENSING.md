# 라이선스 확인 현황

프로젝트에서 직접 작성한 PC 앱 코드와 문서는 [MIT License](LICENSE)로 제공합니다. 저작권 표기는 `Copyright (c) 2026 ys05086`입니다. 외부 라이브러리와 고지 원문에는 각자의 라이선스가 계속 적용됩니다. 이 문서는 배포 조건 검토 메모이며, MIT 허락의 원문은 LICENSE에 있습니다. 수집한 외부 고지와 출처는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 및 `licenses/`에 있습니다.

개인 시험 사용, 타인에게 바이너리 제공, 소스 공개는 구분해야 합니다. 무료 배포도 의존 라이브러리의 배포 조건에서 자동 면제되지 않습니다. 오픈소스 사용료와 저작권 고지·소스 제공 의무, 코덱 특허 조건은 서로 다른 문제입니다.

## 확인한 구성 요소

| 구성 요소 | 확인된 라이선스 / 확인 범위 |
| --- | --- |
| ESP-IDF 5.5.1 | 주 라이선스 Apache-2.0. 하위 구성 요소에는 별도 조건이 있을 수 있음. |
| usb_device_uac 1.3.1 | Apache-2.0 |
| TinyUSB 0.19.0 계열 | MIT. 이 프로젝트의 수정·백포트와 원저작권 고지 보존 필요. |
| NumPy 2.2.6 | 주 라이선스 BSD-3-Clause. 설치 패키지 LICENSE에 번들 의존성 고지가 함께 있음. |
| sounddevice 0.5.6 | MIT. 함께 배포되는 PortAudio 등도 별도 확인 대상. |
| soxr 1.0.0 | 설치 메타데이터 LGPL-2.1-or-later. libsoxr/PFFFT 고지 포함. |
| FFmpeg 7.1.1 (최소 빌드, `ffmpeg/ffmpeg.exe`) | **LGPL 2.1 이상.** AAC 비교 기능 전용. GPL·nonfree 구성 없이 PCM·AAC·ADTS·파이프·리샘플러만 넣어 [tools/build_ffmpeg.sh](tools/build_ffmpeg.sh)로 빌드함. |

**FFmpeg:** 이전에는 PyAV 휠에 들어 있던 FFmpeg DLL을 썼고, 그 DLL이 GPL인 x264/x265를 직접 불러오고 있었습니다. 지금은 PyAV를 쓰지 않습니다. 워크플로가 고정한 FFmpeg 원본 소스(SHA-256 확인)를 위 스크립트로 빌드하고, 빌드 스크립트는 configure 결과가 `LGPL version 2.1 or later`가 아니면 실패합니다. 앱 묶음의 `licenses/inventory.json`을 만드는 단계도 `--enable-gpl`/`--enable-nonfree`가 있거나 GPL 라이브러리가 들어 있으면 실패합니다.

LGPL 조건을 위해 Windows ZIP의 `ffmpeg/` 폴더에 다음을 함께 넣습니다.

- `ffmpeg.exe`, `COPYING.LGPLv2.1`, `LICENSE.md`(FFmpeg 원본의 라이선스 원문)
- `source/ffmpeg-7.1.1.tar.xz`: 빌드에 쓴 수정하지 않은 원본 소스 그 자체
- `BUILD.txt`: 버전, 소스 해시, configure 옵션

앱은 `ffmpeg.exe`를 별도 프로그램으로 실행하므로, 사용자가 직접 빌드한 FFmpeg로 바꿔 넣을 수 있습니다.

CI는 Python 3.11을 쓰며, 패키징 단계에서 고지 원문과 바이너리 해시/버전 목록을 그 환경에서 수집해 ZIP의 `licenses/inventory.json`에 넣습니다. 네이티브 참고 원문의 버전 대응이 확정되지 않은 경우 `reference-sources.json`에 표시했습니다.

## 프로젝트 코드의 MIT 적용 범위

2026-10-08 소유자가 MIT 적용을 명시적으로 선택했습니다. 비상업 제한은 적용하지 않습니다. MIT 조건에 따라 상업 이용, 수정, 재배포가 가능하며 저작권·허락 고지를 유지해야 합니다.

이 저장소의 PC 앱과 `firmware/`에서 직접 작성한 코드와 문서에 적용합니다. 펌웨어는 `firmware/LICENSE`를 따로 둡니다. 외부 원문·라이브러리·패치에 포함된 upstream 코드는 원래 조건을 유지합니다. 함께 배포하는 FFmpeg는 LGPL 조건을 따릅니다.

## 이번에 준비한 고지

- 설치 패키지와 CPython의 라이선스 원문, 파일별 SHA-256과 버전 기록.
- PortAudio, Tcl/Tk의 라이선스 참고 원문 및 출처.
- FFmpeg 최소 빌드의 라이선스 원문, 원본 소스, 빌드 정보.
- ESP-IDF, UAC, TinyUSB의 주요 고지 원문과 프로젝트 수정 사항 설명.

MIT/BSD/Apache 등은 조건을 지키면 상업 이용을 허용하고, LGPL·GPL도 상업 판매 자체를 금지하지 않습니다. 외부 의존성이 있다는 이유로 타인의 상업 이용이 자동 금지되지는 않습니다.

## 공개 배포 전에 남은 작업

- soxr(libsoxr) 등 함께 배포되는 다른 LGPL 네이티브 구성 요소의 정확한 소스·빌드 정보와 교체 조건을 갖춥니다.
- Python/Tcl/Tk, PortAudio, CFFI의 외부 라이브러리와 ESP-IDF 하위 구성 요소까지 최종 산출물 기준으로 고지를 채웁니다. 이미 모은 원문만으로 전체 고지가 끝났다고 간주하지 않습니다.

AAC 등 코덱 특허/상업 배포 조건은 오픈소스 라이선스만으로 면제된다고 단정할 수 없습니다.

## 원문

- [ESP-IDF 5.5.1 LICENSE](https://github.com/espressif/esp-idf/blob/v5.5.1/LICENSE)
- [usb_device_uac 1.3.1 LICENSE](https://components.espressif.com/components/espressif/usb_device_uac/versions/1.3.1/license)
- [TinyUSB 0.19.0 LICENSE](https://github.com/hathach/tinyusb/blob/0.19.0/LICENSE)
- [FFmpeg 라이선스·배포 안내](https://ffmpeg.org/legal.html)
