#include <math.h>
#include <string.h>
#include "speaker_volume.h"

void speaker_volume_init(speaker_volume_t *v) {
    memset(v, 0, sizeof *v);
}

static void phone_changed(speaker_volume_t *v) {
    v->pc_set = false;
    v->changes++;
}

bool speaker_volume_set(speaker_volume_t *v, unsigned channel, int16_t volume) {
    if (channel >= SPEAKER_VOLUME_CHANNELS) return false;
    v->phone_seen = true;
    if (v->volume[channel] != volume) phone_changed(v);
    v->volume[channel] = volume;
    return true;
}

bool speaker_volume_mute(speaker_volume_t *v, unsigned channel, bool mute) {
    if (channel >= SPEAKER_VOLUME_CHANNELS) return false;
    v->phone_seen = true;
    if (v->mute[channel] != mute) phone_changed(v);
    v->mute[channel] = mute;
    return true;
}

bool speaker_volume_pc(speaker_volume_t *v, int16_t level, uint32_t command) {
    if (v->pc_set && command == v->pc_command) return false;
    if (level <= SPEAKER_VOLUME_MIN) level = SPEAKER_LEVEL_SILENT;
    else if (level > 0) level = 0;
    if (!v->pc_set || v->pc_level != level) v->changes++;
    v->pc_set = true;
    v->pc_level = level;
    v->pc_command = command;
    return true;
}

int16_t speaker_volume_side(const speaker_volume_t *v, unsigned side) {
    unsigned channel = 1 + (side ? 1 : 0);
    if (v->mute[0] || v->mute[channel]) return SPEAKER_LEVEL_SILENT;
    if (v->volume[0] <= SPEAKER_VOLUME_MIN || v->volume[channel] <= SPEAKER_VOLUME_MIN) return SPEAKER_LEVEL_SILENT;
    int16_t low = v->volume[0] < v->volume[channel] ? v->volume[0] : v->volume[channel];
    return low > 0 ? 0 : low;
}

int16_t speaker_volume_level(const speaker_volume_t *v) {
    if (v->pc_set) return v->pc_level;
    int16_t left = speaker_volume_side(v, 0), right = speaker_volume_side(v, 1);
    return left > right ? left : right;
}

int32_t speaker_volume_gain(const speaker_volume_t *v, unsigned side) {
    int32_t db = speaker_volume_side(v, side);
    if (v->pc_set) {
        int16_t left = speaker_volume_side(v, 0), right = speaker_volume_side(v, 1);
        int16_t top = left > right ? left : right;
        if (v->pc_level == SPEAKER_LEVEL_SILENT) db = SPEAKER_LEVEL_SILENT;
        else if (top == SPEAKER_LEVEL_SILENT) db = v->pc_level;           // the phone is muted: the PC's level, both sides
        else if (db != SPEAKER_LEVEL_SILENT) db = v->pc_level + (db - top); // the phone's balance, at the PC's level
    }
    if (db <= SPEAKER_VOLUME_MIN) return 0;
    if (db >= 0) return SPEAKER_GAIN_UNITY;
    return (int32_t)lrintf(SPEAKER_GAIN_UNITY * powf(10.0f, (float)db / (256.0f * 20.0f)));
}
