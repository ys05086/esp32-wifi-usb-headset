#include "usb_mic_trace.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <limits.h>

bool vs_mic_trace_enabled(void) { return VS_MIC_TRACE_DETAILED != 0; }

#if VS_MIC_TRACE_DETAILED

static portMUX_TYPE trace_lock = portMUX_INITIALIZER_UNLOCKED;
static vs_mic_trace_t trace;
static bool mic_active, speaker_active;
static uint64_t opened_us, request_us, begin_us, last_plan_us;
static bool requested, running;

static uint32_t elapsed(uint64_t now, uint64_t then) {
    uint64_t delta = now >= then ? now - then : 0;
    return delta > UINT32_MAX ? UINT32_MAX : (uint32_t)delta;
}
static void event(unsigned kind, uint64_t now) {
    // Caller holds trace_lock. No allocation, logging or sockets on audio paths.
    uint32_t seq = ++trace.event_count;
    vs_mic_event_t *e = &trace.events[(seq-1) % VS_MIC_TRACE_CAPACITY];
    *e = (vs_mic_event_t){.at_us=now,.sequence=seq,.kind=kind,.stream=trace.stream,
        .stream_age_us=mic_active?elapsed(now,opened_us):0,
        .fifo_bytes=trace.fifo_bytes,.requested_bytes=trace.requested_bytes,
        .staged_bytes=trace.staged_bytes,.source_frames=trace.source_frames,
        .phase=trace.phase,.request_age_us=requested?elapsed(now,request_us):0,
        .wake_us=trace.wake_us,.render_us=trace.render_us,.mic_active=mic_active,.speaker_active=speaker_active};
}
void vs_mic_trace_stream(bool mic, bool speaker) {
    uint64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&trace_lock);
    if (mic && !mic_active) {trace.stream++;opened_us=now;last_plan_us=0;}
    if (!mic) {requested=false;running=false;trace.phase=0;last_plan_us=0;}
    mic_active=mic;speaker_active=speaker;
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_source(unsigned frames) {
    portENTER_CRITICAL(&trace_lock);
    trace.source_frames=frames;
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_plan(unsigned fifo_bytes, unsigned requested_bytes) {
    uint64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&trace_lock);
    trace.fifo_bytes=fifo_bytes;trace.requested_bytes=requested_bytes;trace.plans++;
    if (last_plan_us && mic_active) {
        uint32_t gap=elapsed(now,last_plan_us);
        if (gap>trace.max_plan_gap_us) trace.max_plan_gap_us=gap;
    }
    last_plan_us=now;
    if (!requested_bytes) {trace.planned_empty++;event(1,now);}
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_empty_completion(void) {
    uint64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&trace_lock);
    trace.completed_empty++;event(2,now);
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_request(void) {
    uint64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&trace_lock);
    request_us=now;requested=true;trace.phase=1;
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_begin(void) {
    uint64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&trace_lock);
    trace.wake_us=requested?elapsed(now,request_us):0;
    if (trace.wake_us>trace.max_wake_us) trace.max_wake_us=trace.wake_us;
    begin_us=now;running=true;trace.phase=2;
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_ready(unsigned bytes) {
    uint64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&trace_lock);
    trace.render_us=running?elapsed(now,begin_us):0;
    if (trace.render_us>trace.max_render_us) trace.max_render_us=trace.render_us;
    trace.staged_bytes=bytes;trace.phase=3;trace.publications++;
    if (trace.wake_us>5000 || trace.render_us>5000) {trace.slow_producer++;event(3,now);}
    running=false;requested=false;
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_consumed(void) {
    portENTER_CRITICAL(&trace_lock);
    trace.staged_bytes=0;trace.phase=0;
    portEXIT_CRITICAL(&trace_lock);
}
void vs_mic_trace_snapshot(vs_mic_trace_t *out) {
    portENTER_CRITICAL(&trace_lock);
    *out=trace;
    portEXIT_CRITICAL(&trace_lock);
}
#else
// Default audio build: no timestamp reads, shared trace locks or event writes.
void vs_mic_trace_stream(bool mic, bool speaker) {(void)mic;(void)speaker;}
void vs_mic_trace_source(unsigned frames) {(void)frames;}
void vs_mic_trace_plan(unsigned fifo_bytes, unsigned requested_bytes) {(void)fifo_bytes;(void)requested_bytes;}
void vs_mic_trace_empty_completion(void) {}
void vs_mic_trace_request(void) {}
void vs_mic_trace_begin(void) {}
void vs_mic_trace_ready(unsigned bytes) {(void)bytes;}
void vs_mic_trace_consumed(void) {}
void vs_mic_trace_snapshot(vs_mic_trace_t *out) {*out=(vs_mic_trace_t){0};}
#endif
