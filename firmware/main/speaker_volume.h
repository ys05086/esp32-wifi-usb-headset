#pragma once

#include <stdbool.h>
#include <stdint.h>

// The listening volume: what the phone asks the board's USB speaker for, and what the PC app sets. The
// speaker feature unit offers mute and a volume of -50..0 dB in 1 dB steps on the master channel (0) and on
// left (1) and right (2), in 1/256 dB. An iPhone sends the stream at full scale and sets this volume instead,
// so the board applies it to the sound it sends to the PC. An iPhone sets the same value on all three channels
// (fractional dB, about 2-4 dB a step; at its lowest volume -50 dB and mute), so master and channel do not
// add, which would double it: the lower of the two applies. The bottom of the range is silence.
//
// The PC app can set the level too, and the side that changed it last wins: a PC level holds until the phone
// changes its volume. The PC level keeps the phone's balance between left and right. The phone's own volume
// display does not follow the PC.
#define SPEAKER_VOLUME_CHANNELS 3
#define SPEAKER_VOLUME_MIN (-50 * 256)
#define SPEAKER_LEVEL_SILENT INT16_MIN
#define SPEAKER_GAIN_UNITY 65536   // Q16
#define SPEAKER_GAIN_STEP 273      // per frame: a full swing takes 5 ms, so a change does not click

typedef struct {
    int16_t volume[SPEAKER_VOLUME_CHANNELS];   // 1/256 dB, as the phone set it
    bool mute[SPEAKER_VOLUME_CHANNELS];
    bool phone_seen;      // the phone has set a volume or mute (an Android phone may scale the stream itself)
    bool pc_set;          // the PC set the level after the phone's last change
    int16_t pc_level;     // 1/256 dB, or SPEAKER_LEVEL_SILENT
    uint32_t pc_command;  // id of the PC's last level command, echoed back to it
    uint32_t changes;     // level changes from either side
} speaker_volume_t;

void speaker_volume_init(speaker_volume_t *v);
// The phone: false for a channel the speaker does not have. A changed value takes the level back from the PC.
bool speaker_volume_set(speaker_volume_t *v, unsigned channel, int16_t volume);
bool speaker_volume_mute(speaker_volume_t *v, unsigned channel, bool mute);
// The PC sets the level (1/256 dB, or SPEAKER_LEVEL_SILENT). False for a repeat of its last command.
bool speaker_volume_pc(speaker_volume_t *v, int16_t level, uint32_t command);
// The phone's volume for left (side 0) or right (side 1): the lower of master and channel, or silent.
int16_t speaker_volume_side(const speaker_volume_t *v, unsigned side);
// The shared level: the PC's while it holds, else the phone's louder side.
int16_t speaker_volume_level(const speaker_volume_t *v);
// Q16 gain for left (side 0) or right (side 1).
int32_t speaker_volume_gain(const speaker_volume_t *v, unsigned side);

static inline int32_t speaker_gain_ramp(int32_t gain, int32_t target) {
    if (gain < target) return target - gain > SPEAKER_GAIN_STEP ? gain + SPEAKER_GAIN_STEP : target;
    return gain - target > SPEAKER_GAIN_STEP ? gain - SPEAKER_GAIN_STEP : target;
}
