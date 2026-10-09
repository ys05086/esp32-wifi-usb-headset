#include <math.h>
#include <string.h>
#include "speaker_volume.h"

void speaker_volume_init(speaker_volume_t *v) {
    memset(v, 0, sizeof *v);
}

bool speaker_volume_set(speaker_volume_t *v, unsigned channel, int16_t volume) {
    if (channel >= SPEAKER_VOLUME_CHANNELS) return false;
    if (v->volume[channel] != volume) v->changes++;
    v->volume[channel] = volume;
    return true;
}

bool speaker_volume_mute(speaker_volume_t *v, unsigned channel, bool mute) {
    if (channel >= SPEAKER_VOLUME_CHANNELS) return false;
    if (v->mute[channel] != mute) v->changes++;
    v->mute[channel] = mute;
    return true;
}

int32_t speaker_volume_gain(const speaker_volume_t *v, unsigned side) {
    unsigned channel = 1 + (side ? 1 : 0);
    if (v->mute[0] || v->mute[channel]) return 0;
    if (v->volume[0] <= SPEAKER_VOLUME_MIN || v->volume[channel] <= SPEAKER_VOLUME_MIN) return 0;
    int32_t total = v->volume[0] < v->volume[channel] ? v->volume[0] : v->volume[channel];
    if (total >= 0) return SPEAKER_GAIN_UNITY;
    return (int32_t)lrintf(SPEAKER_GAIN_UNITY * powf(10.0f, (float)total / (256.0f * 20.0f)));
}
