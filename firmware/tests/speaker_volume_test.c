#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "speaker_volume.h"

static void near(int32_t got, int32_t want) {
    if (abs(got - want) > 2) { printf("got %d, want %d\n", got, want); abort(); }
}

static void phone_sets_all(speaker_volume_t *v, int16_t volume, bool mute) {   // as an iPhone does
    for (unsigned c = 0; c < SPEAKER_VOLUME_CHANNELS; c++) {
        assert(speaker_volume_set(v, c, volume));
        assert(speaker_volume_mute(v, c, mute));
    }
}

static void phone_volume(void) {
    speaker_volume_t v;
    speaker_volume_init(&v);
    // Untouched (a phone that scales the stream itself): unity on both sides.
    assert(speaker_volume_gain(&v, 0) == SPEAKER_GAIN_UNITY && speaker_volume_gain(&v, 1) == SPEAKER_GAIN_UNITY);
    assert(!v.phone_seen && speaker_volume_level(&v) == 0);

    // -6 dB on the master channel: half amplitude, both sides.
    assert(speaker_volume_set(&v, 0, -6 * 256));
    near(speaker_volume_gain(&v, 0), 32845);
    near(speaker_volume_gain(&v, 1), 32845);
    // The lower of master and channel applies: -20 dB on the left only. The level is the louder side.
    assert(speaker_volume_set(&v, 1, -20 * 256));
    near(speaker_volume_gain(&v, 0), 6554);
    near(speaker_volume_gain(&v, 1), 32845);
    assert(speaker_volume_level(&v) == -6 * 256 && v.phone_seen);
    assert(v.changes == 2);
    assert(speaker_volume_set(&v, 1, -20 * 256) && v.changes == 2);   // same value: no change counted
    // As an iPhone sets it: the same value on all three channels applies once, not twice.
    speaker_volume_t phone;
    speaker_volume_init(&phone);
    phone_sets_all(&phone, -5339, false);   // -20.86 dB
    near(speaker_volume_gain(&phone, 0), 5940);
    near(speaker_volume_gain(&phone, 1), 5940);

    // The bottom of the range is silence, on the master or a channel.
    assert(speaker_volume_set(&v, 1, 0) && speaker_volume_set(&v, 0, SPEAKER_VOLUME_MIN));
    assert(speaker_volume_gain(&v, 0) == 0 && speaker_volume_gain(&v, 1) == 0);
    assert(speaker_volume_level(&v) == SPEAKER_LEVEL_SILENT);
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
}

static void pc_level(void) {
    speaker_volume_t v;
    speaker_volume_init(&v);
    phone_sets_all(&v, -5339, false);
    uint32_t changes = v.changes;

    // The PC sets -10 dB: both sides, and the level reports it.
    assert(speaker_volume_pc(&v, -10 * 256, 7));
    assert(v.pc_set && v.pc_command == 7 && v.changes == changes + 1);
    near(speaker_volume_gain(&v, 0), 20724);
    near(speaker_volume_gain(&v, 1), 20724);
    assert(speaker_volume_level(&v) == -10 * 256);
    // A repeat of the same command is ignored; a new one with the same level is taken, not counted.
    assert(!speaker_volume_pc(&v, -30 * 256, 7) && speaker_volume_level(&v) == -10 * 256);
    assert(speaker_volume_pc(&v, -10 * 256, 8) && v.changes == changes + 1);

    // The phone re-sending its unchanged volume keeps the PC's level; changing it takes the level back.
    phone_sets_all(&v, -5339, false);
    assert(v.pc_set && speaker_volume_level(&v) == -10 * 256);
    phone_sets_all(&v, -4728, false);   // one step up: -18.47 dB
    assert(!v.pc_set && speaker_volume_level(&v) == -4728);
    near(speaker_volume_gain(&v, 0), 7818);

    // At its lowest an iPhone sends -50 dB and mute: silence, until the PC raises the level for both sides.
    phone_sets_all(&v, SPEAKER_VOLUME_MIN, true);
    assert(speaker_volume_gain(&v, 0) == 0 && speaker_volume_level(&v) == SPEAKER_LEVEL_SILENT);
    assert(speaker_volume_pc(&v, -20 * 256, 9));
    near(speaker_volume_gain(&v, 0), 6554);
    near(speaker_volume_gain(&v, 1), 6554);

    // The PC level keeps the phone's balance: left 6 dB under right stays 6 dB under.
    speaker_volume_t balance;
    speaker_volume_init(&balance);
    assert(speaker_volume_set(&balance, 1, -6 * 256));
    assert(speaker_volume_pc(&balance, -14 * 256, 1));
    near(speaker_volume_gain(&balance, 0), 6554);    // -20 dB
    near(speaker_volume_gain(&balance, 1), 13076);   // -14 dB
    // A side the phone silenced stays silent.
    assert(speaker_volume_mute(&balance, 1, true) && speaker_volume_pc(&balance, -14 * 256, 2));
    assert(speaker_volume_gain(&balance, 0) == 0);
    near(speaker_volume_gain(&balance, 1), 13076);

    // PC levels are clamped: above 0 dB to 0 dB, at or below the bottom of the range to silence.
    assert(speaker_volume_pc(&v, 6 * 256, 10) && speaker_volume_level(&v) == 0);
    assert(speaker_volume_gain(&v, 0) == SPEAKER_GAIN_UNITY);
    assert(speaker_volume_pc(&v, -60 * 256, 11) && speaker_volume_level(&v) == SPEAKER_LEVEL_SILENT);
    assert(speaker_volume_gain(&v, 0) == 0 && speaker_volume_gain(&v, 1) == 0);
    assert(speaker_volume_pc(&v, SPEAKER_LEVEL_SILENT, 12) && speaker_volume_gain(&v, 1) == 0);

    // Without the phone ever setting a volume (it scales the stream itself), the PC level applies as is.
    speaker_volume_t android;
    speaker_volume_init(&android);
    assert(speaker_volume_pc(&android, -6 * 256, 1) && !android.phone_seen);
    near(speaker_volume_gain(&android, 0), 32845);
    near(speaker_volume_gain(&android, 1), 32845);
}

static void ramp(void) {
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
}

int main(void) {
    phone_volume();
    pc_level();
    ramp();
    puts("speaker volume tests passed");
    return 0;
}
