#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct { uint32_t packets, failed, zero, bytes, retries; } vs_usb_endpoint_stats_t;
typedef struct {
    vs_usb_endpoint_stats_t ep[3]; // microphone, speaker, feedback
    uint32_t feedback_value, feedback_bytes;
    uint32_t mic_prefill_attempts, mic_prefill_recovered;
    bool mic_active, speaker_active;
} vs_usb_stats_t;
void vs_usb_diag_xfer(unsigned kind, unsigned result, unsigned bytes);
void vs_usb_diag_state(bool mic, bool speaker);
void vs_usb_diag_feedback(unsigned value, unsigned bytes);
void vs_usb_diag_retry(unsigned ep_addr);
void vs_usb_diag_mic_prefill(bool recovered);
vs_usb_stats_t vs_usb_diag_snapshot(void);
