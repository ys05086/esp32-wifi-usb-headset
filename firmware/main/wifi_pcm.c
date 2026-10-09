#include "wifi_pcm.h"
#include <string.h>
static uint32_t le32(const uint8_t *p) { return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
// A discontinuity: the next second's level change says nothing about the sender's rate. The rate itself stays.
static void clear_audio(wifi_pcm_t *s) {
    s->head = s->count = 0; s->primed = false; s->window_reads = 0; s->adjust = 0; s->have_last = false;
}
static void put(wifi_pcm_t *s, int16_t v) {
    s->samples[(s->head + s->count) % PCM_RING_FRAMES] = v; s->count++;
}
bool wifi_pcm_push(wifi_pcm_t *s, const uint8_t *p, size_t n, int64_t now) {
    if (n < 16 || memcmp(p, "VSM1", 4)) return false;
    uint32_t session = le32(p+4), seq = le32(p+8);
    unsigned frames = p[12] | (unsigned)p[13]<<8, flags = p[14] | (unsigned)p[15]<<8;
    if (!session || flags > 2 || (flags != 1 && (frames != 480 || n != PCM_PACKET_BYTES)) ||
        (flags == 1 && (frames != 0 || n != 16))) return false;
    bool expired = !s->active || now - s->last_ms > 300;
    if (s->active && session != s->session && !expired) return false;
    if (flags == 1) {
        if (session != s->session) return false;
        clear_audio(s); s->active = false; return true;
    }
    if (expired || session != s->session) { clear_audio(s); s->rate = 0; s->session = session; s->next_sequence = seq; }
    int32_t gap = (int32_t)(seq - s->next_sequence);
    if (gap < 0) return false; // duplicates and reordered stale packets
    if (gap > 3) { clear_audio(s); s->gaps += (uint32_t)gap; }
    else if (gap) {
        if (s->count + (size_t)gap * 480 + 480 > PCM_RING_FRAMES) clear_audio(s);
        for (int i=0; i<gap*480; i++) put(s, 0);
        s->gaps += (uint32_t)gap;
    }
    if (s->count + 480 > PCM_CAP_FRAMES) { // the level control keeps far below this; bursts only
        size_t cut = s->count > PCM_KEEP_FRAMES ? s->count - PCM_KEEP_FRAMES : 0;
        s->head = (s->head + cut) % PCM_RING_FRAMES; s->count -= cut; s->dropped += (uint32_t)cut;
    }
    for (size_t i=0; i<480; i++) put(s, (int16_t)(p[16+2*i] | (unsigned)p[17+2*i]<<8));
    s->next_sequence = seq + 1; s->received++; s->last_ms = now; s->active = true;
    return true;
}
size_t wifi_pcm_take(wifi_pcm_t *s, int16_t *raw, size_t frames, int64_t now) {
    if (!frames) return 0;
    if (!s->active || now - s->last_ms > 300) { clear_audio(s); s->active = false; return 0; }
    // The USB host stopped reading (stream closed and opened again) while audio kept arriving: start like a
    // first prime, from the newest 70 ms, instead of playing the backlog and draining it 2 ms a second.
    if (s->primed && now - s->last_read_ms > 100) s->primed = false;
    s->last_read_ms = now;
    if (!s->primed) {
        if (s->count < PCM_PRIME_FRAMES) return 0;
        size_t cut = s->count - PCM_PRIME_FRAMES; // nothing is playing yet, so nothing audible is cut
        s->head = (s->head + cut) % PCM_RING_FRAMES; s->count -= cut; s->flushed += (uint32_t)cut;
        s->primed = true; s->window_reads = 0; s->adjust = 0; s->have_last = false;
    }
    size_t take = frames < 2 ? frames : (size_t)((int)frames + s->adjust * (int)frames / PCM_PACKET_FRAMES);
    if (s->count < take) { s->underruns++; clear_audio(s); return 0; }
    for (size_t i=0; i<take; i++) { raw[i] = s->samples[s->head]; s->head = (s->head+1) % PCM_RING_FRAMES; }
    s->count -= take;
    raw[take] = s->count ? s->samples[s->head] : raw[take-1];
    if (take > frames) s->squeezed += (uint32_t)(take - frames);
    else s->stretched += (uint32_t)(frames - take);
    if (!s->window_reads) { s->window_min = s->count; s->window_sum = 0; }
    if (s->count < s->window_min) s->window_min = s->count;
    s->window_sum += s->count;
    if (++s->window_reads == PCM_WINDOW_READS) {
        // surplus = how far the mean rose + what this second's step removed; smoothed, as jitter moves the mean
        int32_t mean = (int32_t)(s->window_sum / PCM_WINDOW_READS);
        if (s->have_last) s->rate += ((mean - s->last_mean) + s->adjust * PCM_WINDOW_READS - s->rate) / 4;
        s->last_mean = mean; s->have_last = true;
        int32_t want = s->rate + ((int32_t)s->window_min - (PCM_LOW_FRAMES + PCM_HIGH_FRAMES) / 2) / 4;
        int32_t step = (want + (want >= 0 ? PCM_WINDOW_READS / 2 : -PCM_WINDOW_READS / 2)) / PCM_WINDOW_READS;
        s->adjust = step > PCM_MAX_ADJUST ? PCM_MAX_ADJUST : step < -PCM_MAX_ADJUST ? -PCM_MAX_ADJUST : (int)step;
        s->window_reads = 0;
    }
    return take;
}
void wifi_pcm_render(const int16_t *raw, size_t taken, uint8_t *out, size_t frames) {
    if (!taken) { memset(out, 0, frames*2); return; }
    if (taken == frames) {
        for (size_t i=0; i<frames; i++) { out[2*i] = (uint8_t)raw[i]; out[2*i+1] = (uint8_t)((uint16_t)raw[i] >> 8); }
        return;
    }
    // output i sits at input position i * taken / frames = k + r / frames, exactly: even spacing that carries on
    // into the next block. Stepped without division, to keep the producer short (its slack is a few ms).
    uint32_t inverse = (1u << 24) / (uint32_t)frames; // r / frames in 15 bits is (r * inverse) >> 9
    size_t k = 0, r = 0;
    for (size_t i=0; i<frames; i++) {
        int32_t a = raw[k], w = (int32_t)(((uint32_t)r * inverse) >> 9), v = a + (((raw[k+1] - a) * w) >> 15);
        for (r += taken; r >= frames; r -= frames) k++;
        out[2*i] = (uint8_t)v; out[2*i+1] = (uint8_t)((uint16_t)v >> 8);
    }
}
void wifi_pcm_read(wifi_pcm_t *s, uint8_t *out, size_t bytes, int64_t now) {
    int16_t raw[PCM_RAW_FRAMES];
    for (size_t done = 0, total = bytes/2; done < total; ) {
        size_t frames = total - done < PCM_PACKET_FRAMES ? total - done : PCM_PACKET_FRAMES;
        wifi_pcm_render(raw, wifi_pcm_take(s, raw, frames, now), out + done*2, frames);
        done += frames;
    }
    if (bytes & 1) out[bytes-1] = 0;
}
