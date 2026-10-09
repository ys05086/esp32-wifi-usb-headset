#pragma once

#include <stdbool.h>
#include <stdint.h>

// The phone's volume for the board's USB speaker. The speaker feature unit offers mute and a volume of
// -50..0 dB in 1 dB steps on the master channel (0) and on left (1) and right (2), in 1/256 dB. An iPhone
// sends the stream at full scale and sets this volume instead, so the board applies it to the sound it sends
// to the PC. The bottom of the range is silence: at its lowest phone volume, nothing should be heard.
#define SPEAKER_VOLUME_CHANNELS 3
#define SPEAKER_VOLUME_MIN (-50 * 256)
#define SPEAKER_GAIN_UNITY 65536   // Q16
#define SPEAKER_GAIN_STEP 273      // per frame: a full swing takes 5 ms, so a change does not click

typedef struct {
    int16_t volume[SPEAKER_VOLUME_CHANNELS];   // 1/256 dB
    bool mute[SPEAKER_VOLUME_CHANNELS];
    uint32_t changes;
} speaker_volume_t;

void speaker_volume_init(speaker_volume_t *v);
// False for a channel the speaker does not have.
bool speaker_volume_set(speaker_volume_t *v, unsigned channel, int16_t volume);
bool speaker_volume_mute(speaker_volume_t *v, unsigned channel, bool mute);
// Q16 gain for left (side 0) or right (side 1): master and channel volume add in dB.
int32_t speaker_volume_gain(const speaker_volume_t *v, unsigned side);

static inline int32_t speaker_gain_ramp(int32_t gain, int32_t target) {
    if (gain < target) return target - gain > SPEAKER_GAIN_STEP ? gain + SPEAKER_GAIN_STEP : target;
    return gain - target > SPEAKER_GAIN_STEP ? gain - SPEAKER_GAIN_STEP : target;
}
