#include "probe_tone.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

int main(void)
{
    probe_init();
    assert(probe_sample(-1) == 0);
    assert(probe_sample(PROBE_DURATION_US) == 0);
    assert(probe_sample(60000000) == 0);
    int max = 0;
    for (int64_t t = 0; t < PROBE_DURATION_US; t += 20) {
        int s = abs(probe_sample(t));
        if (t % 1000000 >= 200000) assert(s == 0);
        if (s > max) max = s;
    }
    assert(max > 1600 && max <= 1638);
    assert(probe_sample(0) == 0);
    assert(probe_sample(200000) == 0);
    // Validate lookup phase and amplitude against ideal tones through table wraps.
    for (int second = 0; second < 4; ++second) {
        for (int us = 10000; us < 190000; us += 125) {
            int expected = (int)lrint(1638.0 * sin(6.283185307179586 * (second % 2 ? 880 : 660) * us / 1000000.0));
            assert(abs(probe_sample(second * 1000000LL + us) - expected) <= 1);
        }
    }
    // Identical sample output despite callback scheduling jitter, with absolute expiry.
    probe_stream_t regular = {.start_us = -1}, jittered = {.start_us = -1};
    uint8_t a[960], b[960];
    for (int block = 0; block < 20; ++block) {
        int64_t time = 1000000 + block * 10000;
        int jitter = block == 0 ? 0 : (block % 3 - 1) * 350;
        probe_render(&regular, 1000000, time, a, sizeof a);
        probe_render(&jittered, 1000000, time + jitter, b, sizeof b);
        assert(memcmp(a, b, sizeof a) == 0);
    }
    memset(a, 1, sizeof a);
    probe_render(&regular, 1000000, 5000000, a, sizeof a);
    for (size_t i = 0; i < sizeof a; ++i) assert(a[i] == 0);
    // Paused USB capture resumes at current time, not at an old beep.
    probe_render(&jittered, 1000000, 1750000, a, sizeof a);
    for (size_t i = 0; i < sizeof a; ++i) assert(a[i] == 0);
    return 0;
}
