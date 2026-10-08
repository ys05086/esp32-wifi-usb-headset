#include "usb_mic_refill.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

// Discrete full-speed USB model using TinyUSB 0.19's 47/48/49-frame
// flow-control decisions and ten-interval blackout. No hardware timing claim.
// As in the driver, the next 960-byte block is staged ahead: the gate moves it in at once, and the producer
// then needs `producer_delay` ms to stage another, every 100th block (once a second) `slow` ms instead.
// A slow block empties the FIFO when it takes longer than the ~10 ms between refills plus the FIFO's slack.
static int64_t simulate(int milliseconds, int packets, bool balanced, int producer_delay, int slow, int *empties)
{
    const int depth = 98 * packets, block = 960; // 49-frame maximum packet * packets, PCM16.
    int count = depth / 2, blackout = 0, ready_at = 0, blocks = 0;
    int64_t sent = 0;
    *empties = 0;
    for (int tick = 0; tick < milliseconds; tick++) {
        int frames;
        if (count < 94) { frames = 0; ++*empties; }
        else if (count < depth/2-2 && !blackout) { frames = 47; blackout = 10; }
        else if (count > depth/2+2 && !blackout) { frames = 49; blackout = 10; }
        else { frames = 48; if (blackout) blackout--; }
        if (frames * 2 > count) { frames = count / 2; ++*empties; } // a short packet: what the FIFO holds
        count -= frames * 2; sent += frames;
        bool refill = balanced ? vs_usb_mic_should_refill(count, depth, block) : count <= depth-block;
        if (refill && tick >= ready_at) { count += block; ready_at = tick + (++blocks % 100 ? producer_delay : slow); }
        assert(count >= 0 && count <= depth);
    }
    return sent - (int64_t)milliseconds*48;
}

int main(void)
{
    int empties;
    assert(!vs_usb_mic_should_refill(0, 10, 20));
    assert(!vs_usb_mic_should_refill(0, 10, 0));
    assert(vs_usb_mic_should_refill(598, 2156, 960));
    assert(!vs_usb_mic_should_refill(600, 2156, 960));
    int64_t legacy = simulate(60000, 22, false, 1, 1, &empties);
    assert(legacy > 5000); // Reproduce the existing consumption bias.
    for (int delay=1; delay<=3; delay++) {
        int64_t corrected = simulate(30*60*1000, 22, true, delay, delay, &empties);
        printf("producer delay %d ms: corrected drift %lld frames / virtual 30 min, %d empty\n", delay, (long long)corrected, empties);
        assert(empties == 0 && llabs(corrected) < 48); // <1 ms accumulated bias over virtual 30 min.
    }
    printf("legacy drift: %lld frames / virtual minute\n", (long long)legacy);
    // One slow block a second (traced producer wake delays reached 34 ms): 22 packets run dry past ~15 ms,
    // 62 packets past ~35 ms.
    for (int slow=2; slow<=34; slow++) {
        int64_t drift = simulate(10*60*1000, 62, true, 2, slow, &empties);
        if (slow % 8 == 2 || empties)
            printf("62 packets, one %d ms block a second: %d short packets, drift %lld frames / virtual 10 min\n",
                   slow, empties, (long long)drift);
        assert(empties == 0);
    }
    simulate(10*60*1000, 22, true, 2, 17, &empties);
    printf("22 packets, one 17 ms block a second: %d short packets / virtual 10 min\n", empties);
    assert(empties > 0);
    return 0;
}
