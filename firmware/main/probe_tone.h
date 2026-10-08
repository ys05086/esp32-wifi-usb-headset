#pragma once
#include <stdint.h>
#include <stddef.h>

#define PROBE_RATE 48000
#define PROBE_DURATION_US 4000000LL

// Call once before starting USB. No trigonometry runs in the audio callback.
void probe_init(void);

// Stateless lookup; elapsed time outside the finite probe returns silence.
int16_t probe_sample(int64_t elapsed_us);

typedef struct {
    int64_t start_us;
    int64_t last_callback_us;
    int64_t sample_cursor;
} probe_stream_t;

void probe_render(probe_stream_t *state, int64_t start_us, int64_t now_us, uint8_t *pcm, size_t bytes);
