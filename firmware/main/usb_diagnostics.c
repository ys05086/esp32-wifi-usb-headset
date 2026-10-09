#include "usb_diagnostics.h"
#include "usb_mic_trace.h"
#include "freertos/FreeRTOS.h"
#include "esp_timer.h"

static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static vs_usb_stats_t stats;

// Under lock.
static void event(unsigned kind, unsigned endpoint, unsigned bytes) {
    vs_usb_event_t *e = &stats.events[stats.event_count++ % VS_USB_EVENTS];
    *e = (vs_usb_event_t){.at_ms = (uint32_t)(esp_timer_get_time() / 1000), .bytes = (uint16_t)bytes,
                          .kind = (uint8_t)kind, .endpoint = (uint8_t)endpoint};
}

void vs_usb_diag_mic_prefill(bool recovered) {
    // Only the impending-empty path: no new lock on ordinary USB packets.
    portENTER_CRITICAL(&lock);
    stats.mic_prefill_attempts++;
    if (recovered) stats.mic_prefill_recovered++;
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_speaker_chunk(const uint8_t *data, unsigned size, bool queued) {
    static bool sound;   // the previous chunk had sound; only the USB ISR runs this
    bool zero = true;
    for (unsigned i = 0; i < size; i++) if (data[i]) { zero = false; break; }
    portENTER_CRITICAL(&lock);
    stats.spk_chunks++;
    if (zero) { stats.spk_zero_chunks++; if (sound) stats.spk_zero_after_sound++; }
    if (!queued) stats.spk_queue_full++;
    portEXIT_CRITICAL(&lock);
    sound = !zero;
}

void vs_usb_diag_speaker_restart(void) {
    portENTER_CRITICAL(&lock);
    stats.spk_restarts++;
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_speaker_backlog(unsigned waiting) {
    portENTER_CRITICAL(&lock);
    if (waiting > stats.spk_backlog_max) stats.spk_backlog_max = waiting;
    if (waiting > 8) stats.spk_backlog_over8++;
    portEXIT_CRITICAL(&lock);
}

// Board endpoints: OUT 1 speaker; IN 2 microphone, IN 1 feedback.
static int iso_index(unsigned epnum, unsigned dir) {
    if (!dir) return epnum == 1 ? 0 : -1;
    return epnum == 2 ? 1 : epnum == 1 ? 2 : -1;
}

static int64_t isr_entered, isr_left, out_rx_us;

void vs_usb_diag_isr_enter(void) {
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&lock);
    if (isr_left && (stats.mic_active || stats.speaker_active)) {
        uint32_t gap = (uint32_t)(now - isr_left);
        if (gap > stats.isr_gap_max_us) stats.isr_gap_max_us = gap;
        if (gap > 1100) stats.isr_gaps_over1100++;
    }
    isr_entered = now;
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_isr_exit(void) {
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&lock);
    uint32_t ran = (uint32_t)(now - isr_entered);
    if (ran > stats.isr_max_us) stats.isr_max_us = ran;
    if (ran > 150) stats.isr_over150++;
    isr_left = now;
    portEXIT_CRITICAL(&lock);
}

static unsigned out_last_rx = 0x100;   // 4 LSBs of the frame of the last OUT packet; 0x100: none yet
static bool out_late;                  // the re-arm after that packet ran in a later frame

void vs_usb_diag_out_rx(unsigned frame4) {
    portENTER_CRITICAL(&lock);
    if (out_last_rx != 0x100) {
        unsigned gap = (frame4 - out_last_rx) & 15u;
        if (gap >= 2 && gap < 12) {      // a longer pause is the host stopping, not a lost packet
            stats.out_missed += gap - 1;
            if (out_late) stats.out_missed_after_late += gap - 1;
        }
    }
    out_last_rx = frame4 & 15u;
    out_late = false;
    out_rx_us = esp_timer_get_time();
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_iso_arm(unsigned epnum, unsigned dir, unsigned frame) {
    static unsigned last[3] = {0x10000, 0x10000, 0x10000};
    int i = iso_index(epnum, dir);
    if (i < 0) return;
    portENTER_CRITICAL(&lock);
    if (last[i] != 0x10000) {
        unsigned gap = (frame - last[i]) & 0x3FFFu;
        if (gap >= 2 && gap < 50) { stats.arm_gaps[i] += gap - 1; stats.arm_gap_events[i]++; }
    }
    last[i] = frame & 0x3FFFu;
    if (i == 0 && out_last_rx != 0x100 && ((frame - out_last_rx) & 15u) >= 1) { stats.out_late_arms++; out_late = true; }
    if (i == 0 && out_rx_us) {
        uint32_t delay = (uint32_t)(esp_timer_get_time() - out_rx_us);
        if (delay > stats.rearm_max_us) stats.rearm_max_us = delay;
        stats.rearm_hist[delay < 250 ? 0 : delay < 500 ? 1 : delay < 750 ? 2 : delay < 1000 ? 3 : 4]++;
        out_rx_us = 0;
    }
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_retry(unsigned ep_addr) {
    // Board descriptors: 0x82 microphone, 0x81 speaker feedback.
    if (ep_addr != 0x82 && ep_addr != 0x81) return;
    unsigned kind = ep_addr == 0x82 ? 0 : 2;
    portENTER_CRITICAL(&lock);
    stats.ep[kind].retries++;
    event(VS_USB_EVENT_RETRY, kind, 0);
    portEXIT_CRITICAL(&lock);
}

void vs_usb_diag_xfer(unsigned kind, unsigned result, unsigned bytes) {
    if (kind >= 3) return;
    portENTER_CRITICAL(&lock);
    vs_usb_endpoint_stats_t *ep = &stats.ep[kind];
    ep->packets++;
    if (result != 0) { ep->failed++; event(VS_USB_EVENT_FAILED, kind, bytes); } // TinyUSB XFER_RESULT_SUCCESS == 0
    else {
        ep->bytes += bytes;
        if (bytes == 0) { ep->zero++; if (kind == 0) event(VS_USB_EVENT_EMPTY, 0, 0); }
        else if (kind == 0 && bytes < VS_MIC_MIN_PACKET_BYTES) { ep->partial++; event(VS_USB_EVENT_SHORT, 0, bytes); }
        if (kind == 0 && bytes) {
            unsigned frames = bytes / 2;   // mono PCM16
            stats.mic_frames[frames >= 47 && frames <= 49 ? frames - 47 : 3]++;
        }
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
    stats.isr_max_us = stats.isr_gap_max_us = stats.rearm_max_us = 0;   // maxima per status read
    portEXIT_CRITICAL(&lock);
    return result;
}
