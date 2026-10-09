#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "speaker_volume.h"

static void near(int32_t got, int32_t want) {
    if (abs(got - want) > 2) { printf("got %d, want %d\n", got, want); abort(); }
}

int main(void) {
    speaker_volume_t v;
    speaker_volume_init(&v);
    // Untouched (a phone that scales the stream itself): unity on both sides.
    assert(speaker_volume_gain(&v, 0) == SPEAKER_GAIN_UNITY && speaker_volume_gain(&v, 1) == SPEAKER_GAIN_UNITY);

    // -6 dB on the master channel: half amplitude, both sides.
    assert(speaker_volume_set(&v, 0, -6 * 256));
    near(speaker_volume_gain(&v, 0), 32845);
    near(speaker_volume_gain(&v, 1), 32845);
    // Master and channel volume add in dB: -6 - 14 = -20 dB on the left only.
    assert(speaker_volume_set(&v, 1, -14 * 256));
    near(speaker_volume_gain(&v, 0), 6554);
    near(speaker_volume_gain(&v, 1), 32845);
    assert(v.changes == 2);
    assert(speaker_volume_set(&v, 1, -14 * 256) && v.changes == 2);   // same value: no change counted

    // The bottom of the range is silence, on the master or a channel.
    assert(speaker_volume_set(&v, 1, 0) && speaker_volume_set(&v, 0, SPEAKER_VOLUME_MIN));
    assert(speaker_volume_gain(&v, 0) == 0 && speaker_volume_gain(&v, 1) == 0);
    assert(speaker_volume_set(&v, 0, -49 * 256));
    near(speaker_volume_gain(&v, 0), 233);
    assert(speaker_volume_set(&v, 0, 0) && speaker_volume_set(&v, 2, SPEAKER_VOLUME_MIN));
    assert(speaker_volume_gain(&v, 0) == SPEAKER_GAIN_UNITY && speaker_volume_gain(&v, 1) == 0);
    assert(speaker_volume_set(&v, 2, 0));

    // Mute on the master silences both sides; on a channel, that side only.
    assert(speaker_volume_mute(&v, 0, true));
    assert(speaker_volume_gain(&v, 0) == 0 && speaker_volume_gain(&v, 1) == 0);
    assert(speaker_volume_mute(&v, 0, false) && speaker_volume_mute(&v, 2, true));
    assert(speaker_volume_gain(&v, 0) == SPEAKER_GAIN_UNITY && speaker_volume_gain(&v, 1) == 0);

    // A positive request (outside the advertised range) never boosts; unknown channels are refused.
    assert(speaker_volume_mute(&v, 2, false) && speaker_volume_set(&v, 0, 6 * 256));
    assert(speaker_volume_gain(&v, 0) == SPEAKER_GAIN_UNITY);
    assert(!speaker_volume_set(&v, 3, 0) && !speaker_volume_mute(&v, 255, true));

    // The ramp reaches its target in steps of at most SPEAKER_GAIN_STEP: 0 to unity in 5 ms at 48 kHz.
    int32_t gain = 0;
    int frames = 0;
    while (gain != SPEAKER_GAIN_UNITY) {
        int32_t next = speaker_gain_ramp(gain, SPEAKER_GAIN_UNITY);
        assert(next > gain && next - gain <= SPEAKER_GAIN_STEP);
        gain = next;
        frames++;
    }
    assert(frames == 241);
    while (gain) gain = speaker_gain_ramp(gain, 0);
    assert(speaker_gain_ramp(100, 100) == 100);
    puts("speaker volume tests passed");
    return 0;
}
