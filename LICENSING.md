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
| PyAV 16.1.0 | BSD-3-Clause. FFmpeg 라이선스와 별개. |
| 현재 로컬 PyAV의 FFmpeg DLL | avcodec/avformat/avutil/avfilter/swresample/swscale의 런타임 license 함수가 `LGPL version 3 or later`를 반환함. 아래 주의 참조. |

2026-10-08의 로컬 Windows CPython 3.10 환경과 로컬 빌드 배포물을 확인했습니다. **avcodec DLL의 PE import table에서 번들 x264/x265 DLL을 실제로 참조하는 것을 확인했습니다.** 따라서 FFmpeg가 반환한 LGPL 문자열만으로 전체 배포물의 조건을 판단하면 안 됩니다. 현재 ZIP을 MIT-only 또는 LGPL-only로 표시하지 않습니다. AAC 기능을 꺼도 포함된 라이브러리의 배포 조건은 없어지지 않습니다.

CI는 Python 3.11을 쓰므로 새 패키징 단계에서 고지 원문과 DLL 해시/버전 목록을 그 환경에서 다시 수집합니다. 저장소 `licenses/inventory.json`은 현재 로컬 빌드의 기록이며 모든 미래 빌드에 대한 선언이 아닙니다. 네이티브 참고 원문의 버전 대응이 확정되지 않은 경우 `reference-sources.json`에 표시했습니다.

## 프로젝트 코드의 MIT 적용 범위

2026-10-08 소유자가 MIT 적용을 명시적으로 선택했습니다. 비상업 제한은 적용하지 않습니다. MIT 조건에 따라 상업 이용, 수정, 재배포가 가능하며 저작권·허락 고지를 유지해야 합니다.

이 저장소의 PC 앱과 `firmware/`에서 직접 작성한 코드와 문서에 적용합니다. 펌웨어는 `firmware/LICENSE`를 따로 둡니다. 외부 원문·라이브러리·패치에 포함된 upstream 코드는 원래 조건을 유지합니다.

우리 코드의 MIT 적용은 현재 FFmpeg 번들 전체를 MIT로 바꾸거나 GPL/LGPL 배포 의무를 없애지 않습니다. x264/x265 의존성 정리, 정확한 소스·빌드 자료 및 남은 고지 준비는 계속 필요합니다.

## 이번에 준비한 고지

- 설치 패키지 8개 및 CPython의 라이선스 원문, 파일별 SHA-256과 버전 기록.
- PortAudio, Tcl/Tk, FFmpeg의 라이선스 참고 원문 및 출처.
- ESP-IDF, UAC, TinyUSB의 주요 고지 원문과 프로젝트 수정 사항 설명.
- 다음 Windows 패키징 시 고지 파일 및 바이너리 목록을 동봉하는 절차.

MIT/BSD/Apache 등은 조건을 지키면 상업 이용을 허용하고, GPL도 상업 판매 자체를 금지하지 않습니다. 외부 의존성이 있다는 이유로 타인의 상업 이용이 자동 금지되지는 않습니다.

## 공개 배포 전에 남은 작업

- 고지를 모은 구성 요소 이외의 FFmpeg 네이티브 의존성과 ESP-IDF 하위 구성 요소까지 정확한 버전/저작권 고지를 채웁니다. 이미 모은 원문만으로 전체 고지가 끝났다고 간주하지 않습니다.
- FFmpeg/soxr 등 해당 LGPL 구성 요소의 정확한 바이너리에 대응하는 소스·빌드 정보 제공과 교체/재링크 조건을 충족하는 배포 방식을 준비합니다. 이름과 버전만 같은 임의 소스 링크로 충분하다고 가정하지 않습니다.
- Python/Tcl/Tk, PortAudio, CFFI, FFmpeg의 외부 라이브러리와 ESP-IDF 하위 구성 요소까지 최종 산출물 기준으로 확인합니다.

현재 설치 문서 추가는 공개 배포 준비가 모두 완료됐다는 의미가 아닙니다. AAC 등 코덱 특허/상업 배포 조건은 오픈소스 라이선스만으로 면제된다고 단정할 수 없습니다.

## 원문

- [ESP-IDF 5.5.1 LICENSE](https://github.com/espressif/esp-idf/blob/v5.5.1/LICENSE)
- [usb_device_uac 1.3.1 LICENSE](https://components.espressif.com/components/espressif/usb_device_uac/versions/1.3.1/license)
- [TinyUSB 0.19.0 LICENSE](https://github.com/hathach/tinyusb/blob/0.19.0/LICENSE)
- [FFmpeg 라이선스·배포 안내](https://ffmpeg.org/legal.html)
- [x264의 GPL / 상용 라이선스 안내](https://images.videolan.org/developers/x264.html)
- [x265 라이선스 안내](https://www.x265.org/)
