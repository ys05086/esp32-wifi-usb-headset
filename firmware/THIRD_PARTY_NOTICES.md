# ESP32 USB headset — third-party notices

This firmware uses ESP-IDF 5.5.1 (principally Apache-2.0),
espressif/usb_device_uac 1.3.1 (Apache-2.0), and
espressif/tinyusb 0.19.0~3 (MIT). These components retain their original
copyright and license terms. Bundled license texts are in `licenses/`.
`dependencies.lock` records the resolved component versions.

The project modifies UAC and TinyUSB using `patch_uac.py` and
`patch_tinyusb.py`. Modifications include microphone FIFO sizing and refill
ordering, speaker buffer ownership, selectable USB descriptors, immediate
ISO IN FIFO priming, interrupt ordering and diagnostic instrumentation.
The patch scripts describe upstream backports; this notice does not
replace or remove original copyright notices.

Sources and modifications: the `firmware/` directory of
https://github.com/ys05086/esp32-wifi-usb-headset

Upstream sources:

- https://github.com/espressif/esp-idf/tree/v5.5.1
- https://components.espressif.com/components/espressif/usb_device_uac/versions/1.3.1
- https://components.espressif.com/components/espressif/tinyusb/versions/0.19.0~3

## Scope

The collection includes top-level license files from ESP-IDF and resolved
managed components. ESP-IDF contains components with separate terms and
file-level copyright notices. Matching those to linked firmware, and
assembling remaining notices, is still in progress. This is not a declaration
that the complete firmware is MIT-licensed or that distribution review is
complete. Original code and documentation in `firmware/` are licensed
under the MIT License in `LICENSE`. Third-party components, upstream code
embedded in patches, and their notices retain their own terms. The Windows client in the
repository root has its own LICENSE.
