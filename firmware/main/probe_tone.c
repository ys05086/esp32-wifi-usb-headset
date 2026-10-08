#include "probe_tone.h"
#include <math.h>
#include <stdbool.h>
#include <string.h>

static int16_t sine660[800], sine880[600];

void probe_init(void)
{
    // Each table contains exactly eleven cycles, with no phase seam on wrap.
    for (int i = 0; i < 800; ++i)
        sine660[i] = (int16_t)lrintf(1638.0f * sinf(6.283185307179586f * 11 * i / 800));
    for (int i = 0; i < 600; ++i)
        sine880[i] = (int16_t)lrintf(1638.0f * sinf(6.283185307179586f * 11 * i / 600));
}

static int16_t sample_at_frame(int64_t frame)
{
    if (frame < 0 || frame >= 4 * PROBE_RATE) return 0;
    int within = (int)(frame % PROBE_RATE);
    if (within >= 9600) return 0;
    int sample = (frame / PROBE_RATE) % 2 ? sine880[within % 600] : sine660[within % 800];
    // Integer 10-ms fades; lookup and gain only in the real-time path.
    if (within < 480) sample = sample * within / 480;
    else if (within > 9120) sample = sample * (9600 - within) / 480;
    return (int16_t)sample;
}

int16_t probe_sample(int64_t elapsed_us)
{
    if (elapsed_us < 0 || elapsed_us >= PROBE_DURATION_US) return 0;
    return sample_at_frame(elapsed_us * PROBE_RATE / 1000000);
}

void probe_render(probe_stream_t *state, int64_t start_us, int64_t now_us, uint8_t *pcm, size_t bytes)
{
    memset(pcm, 0, bytes);
    int64_t elapsed = now_us - start_us;
    if (start_us < 0 || elapsed < 0 || elapsed >= PROBE_DURATION_US) return;
    // Task wake-up jitter must not modulate the tone: advance by transmitted samples.
    // A new test or a paused host reanchors to wall time; the deadline remains absolute.
    if (state->start_us != start_us || now_us - state->last_callback_us > 50000) {
        bool fresh = state->start_us != start_us;
        state->start_us = start_us;
        state->sample_cursor = fresh ? 0 : elapsed * PROBE_RATE / 1000000;
    }
    state->last_callback_us = now_us;
    for (size_t i = 0; i < bytes / 2; ++i) {
        int16_t sample = sample_at_frame(state->sample_cursor + (int64_t)i);
        pcm[2 * i] = (uint8_t)sample;
        pcm[2 * i + 1] = (uint8_t)((uint16_t)sample >> 8);
    }
    state->sample_cursor += (int64_t)(bytes / 2);
}
