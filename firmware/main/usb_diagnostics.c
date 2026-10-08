#include "usb_diagnostics.h"
#include "usb_mic_trace.h"
#include "freertos/FreeRTOS.h"

static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static vs_usb_stats_t stats;

void vs_usb_diag_mic_prefill(bool recovered) {
    // Only the impending-empty path: no new lock on ordinary USB packets.
    portENTER_CRITICAL(&lock);
    stats.mic_prefill_attempts++;
    if (recovered) stats.mic_prefill_recovered++;
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_retry(unsigned ep_addr) {
    // Board descriptors: 0x82 microphone, 0x81 speaker feedback.
    if (ep_addr != 0x82 && ep_addr != 0x81) return;
    unsigned kind = ep_addr == 0x82 ? 0 : 2;
    portENTER_CRITICAL(&lock);
    stats.ep[kind].retries++;
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_xfer(unsigned kind, unsigned result, unsigned bytes) {
    if (kind >= 3) return;
    portENTER_CRITICAL(&lock);
    vs_usb_endpoint_stats_t *ep = &stats.ep[kind];
    ep->packets++;
    if (result != 0) ep->failed++; // TinyUSB XFER_RESULT_SUCCESS == 0
    else {
        ep->bytes += bytes;
        if (bytes == 0) ep->zero++;
    }
    portEXIT_CRITICAL(&lock);
    if (kind==0 && result==0 && bytes==0) vs_mic_trace_empty_completion();
}

void vs_usb_diag_state(bool mic, bool speaker) {
    portENTER_CRITICAL(&lock);
    stats.mic_active = mic;
    stats.speaker_active = speaker;
    portEXIT_CRITICAL(&lock);
    vs_mic_trace_stream(mic, speaker);
}

void vs_usb_diag_feedback(unsigned value, unsigned bytes) {
    portENTER_CRITICAL(&lock);
    stats.feedback_value = value;
    stats.feedback_bytes = bytes;
    portEXIT_CRITICAL(&lock);
}

vs_usb_stats_t vs_usb_diag_snapshot(void) {
    portENTER_CRITICAL(&lock);
    vs_usb_stats_t result = stats;
    portEXIT_CRITICAL(&lock);
    return result;
}
