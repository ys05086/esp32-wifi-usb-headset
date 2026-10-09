#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define PCM_PACKET_FRAMES 480
#define PCM_PACKET_BYTES (16 + PCM_PACKET_FRAMES * 2)
#define PCM_RING_FRAMES 14400
// Level control. Nothing else lowers the network buffer: a sender faster than the USB host raises it until the
// 200 ms latency cap removes 80 ms at once. The host can also be ~1% slow (an iPhone polled 988 times a second
// instead of 1000). About once a second the buffer's mean level gives the sender's surplus in frames per second;
// the next reads take that many frames more (or fewer) than they play, plus a quarter of the distance from that
// second's lowest level to 70 ms, at most PCM_MAX_ADJUST per 480 (2.5%, 43 cents), spread over each block by
// linear interpolation. Near zero drift and near 70 ms it is a plain copy.
#define PCM_PRIME_FRAMES 3360   // 70 ms before playing, and again after an underrun
#define PCM_LOW_FRAMES 2880     // keep each second's lowest level between 60 ...
#define PCM_HIGH_FRAMES 3840    // ... and 80 ms
#define PCM_WINDOW_READS 100    // reads per decision: ~1 s of 10 ms blocks
#define PCM_CAP_FRAMES 9600     // emergency latency cap, 200 ms; keeps the newest 120 ms
#define PCM_KEEP_FRAMES 5760
#define PCM_MAX_ADJUST 12       // frames per 480-frame read: 2.5%, room above a 2% drift
#define PCM_RAW_FRAMES (PCM_PACKET_FRAMES + PCM_MAX_ADJUST + 1)   // a take, plus the next block's first frame
typedef struct {
    int16_t samples[PCM_RING_FRAMES];
    uint32_t session, next_sequence, received, gaps, underruns, dropped;
    uint32_t squeezed, stretched;   // frames removed / added by the level control
    uint32_t flushed;               // frames skipped when playback (re)started, before anything was played
    size_t head, count;
    size_t window_min;
    uint64_t window_sum;            // of the level after each read, for the mean
    unsigned window_reads;
    int adjust;                     // frames taken per 480 read beyond those played, -PCM_MAX_ADJUST..+PCM_MAX_ADJUST
    int32_t rate, last_mean;        // sender surplus (frames per second, smoothed); last second's mean level
    bool have_last;
    int64_t last_ms, last_read_ms;
    bool active, primed;
} wifi_pcm_t;
bool wifi_pcm_push(wifi_pcm_t *s, const uint8_t *p, size_t bytes, int64_t now_ms);
/// The samples for one block of `frames` (at most PCM_PACKET_FRAMES) into raw, which holds PCM_RAW_FRAMES:
/// returns how many frames it took (0: play silence), with raw[taken] the next block's first frame.
/// Short; meant for under the caller's lock.
size_t wifi_pcm_take(wifi_pcm_t *s, int16_t *raw, size_t frames, int64_t now_ms);
/// raw[0..taken] spread evenly over `frames` PCM16 LE frames; a plain copy when taken == frames.
void wifi_pcm_render(const int16_t *raw, size_t taken, uint8_t *out, size_t frames);
/// take + render in PCM_PACKET_FRAMES blocks, without a lock
void wifi_pcm_read(wifi_pcm_t *s, uint8_t *out, size_t bytes, int64_t now_ms);
