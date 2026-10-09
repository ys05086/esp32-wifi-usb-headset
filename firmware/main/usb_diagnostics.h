#pragma once
#include <stdbool.h>
#include <stdint.h>

// 47 frames of mono PCM16: TinyUSB's smallest regular microphone packet at 48 kHz. A successful packet
// with fewer bytes (but not none) counts as short.
#define VS_MIC_MIN_PACKET_BYTES 94
// The last USB anomalies with the board's uptime, to line them up with a recording made through the board
// (the status page reports uptime_ms alongside).
#define VS_USB_EVENTS 32
enum { VS_USB_EVENT_EMPTY = 1, VS_USB_EVENT_SHORT, VS_USB_EVENT_FAILED, VS_USB_EVENT_RETRY };
typedef struct { uint32_t at_ms; uint16_t bytes; uint8_t kind, endpoint; } vs_usb_event_t;

typedef struct { uint32_t packets, failed, zero, partial, bytes, retries; } vs_usb_endpoint_stats_t;
typedef struct {
    vs_usb_endpoint_stats_t ep[3]; // microphone, speaker, feedback
    uint32_t feedback_value, feedback_bytes;
    uint32_t mic_prefill_attempts, mic_prefill_recovered;
    // Speaker data as the USB ISR hands it to the speaker task (normally one 1 ms chunk per packet):
    // chunks, all-zero chunks, all-zero chunks right after sound, chunks lost to a full handoff queue,
    // and stream restarts (a 10 ms gap between packets clears the FIFO and waits for 5 ms of data).
    uint32_t spk_chunks, spk_zero_chunks, spk_zero_after_sound, spk_queue_full, spk_restarts;
    // the most chunks waiting when the speaker task took one, and how often more than 8 were (the old depth)
    uint32_t spk_backlog_max, spk_backlog_over8;
    // microphone packets by size, 47 / 48 / 49 frames / other: the host may read the board's clock from these
    uint32_t mic_frames[4];
    uint32_t event_count;          // every event so far; the ring keeps the last VS_USB_EVENTS
    vs_usb_event_t events[VS_USB_EVENTS];
    bool mic_active, speaker_active;
} vs_usb_stats_t;
void vs_usb_diag_xfer(unsigned kind, unsigned result, unsigned bytes);
void vs_usb_diag_state(bool mic, bool speaker);
void vs_usb_diag_feedback(unsigned value, unsigned bytes);
void vs_usb_diag_retry(unsigned ep_addr);
void vs_usb_diag_mic_prefill(bool recovered);
void vs_usb_diag_speaker_chunk(const uint8_t *data, unsigned size, bool queued);   // USB ISR
void vs_usb_diag_speaker_restart(void);                                              // USB ISR
void vs_usb_diag_speaker_backlog(unsigned waiting);                                  // speaker task
vs_usb_stats_t vs_usb_diag_snapshot(void);
