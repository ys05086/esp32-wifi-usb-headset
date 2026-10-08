#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifndef VS_MIC_TRACE_DETAILED
#define VS_MIC_TRACE_DETAILED 0
#endif
bool vs_mic_trace_enabled(void);

#define VS_MIC_TRACE_CAPACITY 16
// Event kinds: 1 scheduled empty, 2 completed empty, 3 slow producer.
// Producer phases: 0 unknown/stopped, 1 notified, 2 running, 3 staged ready.
typedef struct {
    uint64_t at_us;
    uint32_t sequence, kind, stream, stream_age_us;
    uint32_t fifo_bytes, requested_bytes, staged_bytes, source_frames;
    uint32_t phase, request_age_us, wake_us, render_us, mic_active, speaker_active;
} vs_mic_event_t;
typedef struct {
    uint32_t stream, planned_empty, completed_empty, slow_producer;
    uint32_t plans, publications, max_plan_gap_us, max_wake_us, max_render_us;
    uint32_t fifo_bytes, requested_bytes, staged_bytes, source_frames, phase;
    uint32_t wake_us, render_us, event_count;
    vs_mic_event_t events[VS_MIC_TRACE_CAPACITY];
} vs_mic_trace_t;
void vs_mic_trace_stream(bool mic, bool speaker);
void vs_mic_trace_source(unsigned frames);
void vs_mic_trace_plan(unsigned fifo_bytes, unsigned requested_bytes);
void vs_mic_trace_empty_completion(void);
void vs_mic_trace_request(void);
void vs_mic_trace_begin(void);
void vs_mic_trace_ready(unsigned bytes);
void vs_mic_trace_consumed(void);
void vs_mic_trace_snapshot(vs_mic_trace_t *out);
