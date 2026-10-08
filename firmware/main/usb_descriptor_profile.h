#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef enum {
    VS_USB_STANDARD = 0,
    VS_USB_APPLE = 1,
    VS_USB_ADAPTIVE = 2
} vs_usb_mode_t;

// This bridge has one UAC2 function: speaker OUT 01, feedback IN 81, mic IN 82.
// Preserve every class/clock/terminal descriptor and the microphone endpoint.
// Return zero on descriptor drift; never enumerate a partly transformed device.
static inline size_t vs_usb_build_descriptor(const uint8_t *src, size_t len,
                                            uint8_t *dst, size_t capacity,
                                            vs_usb_mode_t mode)
{
    if (!src || !dst || len < 9 || capacity < len || mode > VS_USB_ADAPTIVE ||
        mode < VS_USB_STANDARD || src[0] != 9 || src[1] != 2 ||
        ((size_t)src[2] | (size_t)src[3] << 8) != len) return 0;
    size_t out = 0, interface_offset = 0;
    unsigned speaker = 0, mic = 0, feedback = 0;
    for (size_t i = 0; i < len;) {
        size_t n = src[i];
        if (n < 2 || n > len - i) return 0;
        if (src[i+1] == 4) {
            if (n != 9) return 0;
            interface_offset = out;
        }
        bool skip = false;
        if (src[i+1] == 5) {
            if (n != 7 || !interface_offset) return 0;
            if (src[i+2] == 0x81) {
                if (src[i+3] != 0x11 || dst[interface_offset+4] != 2) return 0;
                feedback++;
                if (mode == VS_USB_ADAPTIVE) {
                    dst[interface_offset+4] = 1;
                    skip = true;
                }
            } else if (src[i+2] == 0x01) {
                if (src[i+3] != 0x05) return 0;
                speaker++;
            } else if (src[i+2] == 0x82) {
                if (src[i+3] != 0x05) return 0;
                mic++;
            } else return 0;
        }
        if (!skip) {
            memcpy(dst + out, src + i, n);
            if (src[i+1] == 5) {
                if (src[i+2] == 0x81) {
                    dst[out+4] = mode == VS_USB_APPLE ? 3 : 4;
                    dst[out+5] = 0;
                } else if (src[i+2] == 0x01 && mode == VS_USB_ADAPTIVE) {
                    dst[out+3] = 0x09; // ISO / adaptive / data, no explicit feedback.
                }
            }
            out += n;
        }
        i += n;
    }
    if (speaker != 1 || mic != 1 || feedback != 1) return 0;
    dst[2] = (uint8_t)out;
    dst[3] = (uint8_t)(out >> 8);
    return out;
}
