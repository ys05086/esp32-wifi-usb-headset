#include "wifi_pcm.h"
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int tri(uint64_t n) { // 500 Hz triangle, peak 12000: 500 per sample everywhere
    int k = (int)(n % 96);
    return k < 48 ? -12000 + k * 500 : 12000 - (k - 48) * 500;
}
static void wave(uint8_t *p, unsigned seq, bool triangle) {
    memset(p,0,PCM_PACKET_BYTES);memcpy(p,"VSM1",4);p[4]=1;
    for(int i=0;i<4;i++) { p[8+i]=(uint8_t)(seq>>(i*8)); }
    p[12]=0xe0;p[13]=1;
    for(int i=0;i<480;i++){
        uint16_t v=triangle?(uint16_t)(int16_t)tri((uint64_t)seq*480+i):0x1234;
        p[16+i*2]=(uint8_t)v;p[17+i*2]=(uint8_t)(v>>8);
    }
}
static void packet(uint8_t *p, unsigned seq) { wave(p,seq,false); }

/// A sender whose clock runs `ppm` fast (negative: slow) against the USB host, its packets arriving up to
/// `jitter_ms` late, `burst` packets already queued at the start. The host reads 480 frames every 10 ms.
static void drift(double ppm, unsigned jitter_ms, unsigned burst, unsigned seconds) {
    static wifi_pcm_t s; memset(&s,0,sizeof s);
    uint8_t p[PCM_PACKET_BYTES],out[960];
    double period=10000.0/(1+ppm*1e-6), arrival=0, next=0; // host microseconds
    uint32_t rng=12345; bool pending=false, started=false;
    unsigned k=0, settled_at=0; int previous=0, worst=0;
    size_t low=PCM_RING_FRAMES, high=0;
    for(unsigned j=0;j<seconds*100;j++) {
        double t=j*10000.0;
        for(;;) {
            if(k>=burst && !pending) {
                rng=rng*1103515245u+12345u;
                double sent=(k-burst)*period+(double)((rng>>8)%(jitter_ms*1000+1));
                next=sent>arrival?sent:arrival; pending=true;
            }
            double due=k<burst?0:next;
            if(due>t) break;
            arrival=due; pending=false;
            wave(p,k,true); assert(wifi_pcm_push(&s,p,sizeof p,(int64_t)(arrival/1000))); k++;
        }
        wifi_pcm_read(&s,out,sizeof out,(int64_t)(t/1000));
        for(int i=0;i<480;i++) {
            int v=(int16_t)(out[2*i]|out[2*i+1]<<8);
            if(s.primed && (started || i)) { int d=abs(v-previous); if(d>worst) worst=d; }
            previous=v;
        }
        if(s.primed) started=true;
        if(!settled_at && started && s.window_reads==0 && s.window_min<=PCM_HIGH_FRAMES) settled_at=j;
        if(settled_at && j>settled_at+3000) { if(s.count<low) low=s.count; if(s.count>high) high=s.count; }
    }
    printf("drift %+6.0f ppm, jitter %2u ms, burst %2u: settled %5.1f s, level %3zu-%3zu ms, removed %u, added %u, "
           "cap trims %u, underruns %u, largest step %d\n", ppm, jitter_ms, burst, settled_at/100.0, low/48, high/48,
           s.squeezed, s.stretched, s.dropped, s.underruns, worst);
    assert(s.dropped==0 && s.underruns==0);  // no 80 ms cuts, no gaps
    assert(worst<=502);                      // triangle slope 500 * 481/480, plus rounding: no click anywhere
    assert(settled_at && low>=PCM_LOW_FRAMES-960 && high<=PCM_HIGH_FRAMES+480+jitter_ms*48+480);
}

int main(void) {
    wifi_pcm_t s={0};uint8_t p[PCM_PACKET_BYTES],out[960];
    packet(p,0);assert(!wifi_pcm_push(&s,p,sizeof p-1,0));
    for(unsigned i=0;i<7;i++){packet(p,i);assert(wifi_pcm_push(&s,p,sizeof p,i*10));}
    assert(!wifi_pcm_push(&s,p,sizeof p,61));
    wifi_pcm_read(&s,out,sizeof out,70);
    for(int i=0;i<480;i++)assert(out[i*2]==0x34&&out[i*2+1]==0x12);
    assert(s.count==PCM_PRIME_FRAMES-480&&s.flushed==0);
    packet(p,9);assert(wifi_pcm_push(&s,p,sizeof p,80));assert(s.gaps==2);
    wifi_pcm_read(&s,out,sizeof out,400);assert(!s.active&&s.count==0);
    for(unsigned i=0;i<sizeof out;i++)assert(out[i]==0);
    packet(p,0);assert(wifi_pcm_push(&s,p,sizeof p,401));
    p[4]=2;assert(!wifi_pcm_push(&s,p,sizeof p,402));
    p[4]=1;p[12]=p[13]=0;p[14]=1;assert(wifi_pcm_push(&s,p,16,403));assert(!s.active);
    for(unsigned i=0;i<1000;i++){packet(p,i);assert(wifi_pcm_push(&s,p,sizeof p,500+i*10));assert(s.count<=9600);}
    assert(s.dropped>0);
    packet(p,1000);p[14]=2;assert(wifi_pcm_push(&s,p,sizeof p,10500));
    packet(p,1001);p[14]=3;assert(!wifi_pcm_push(&s,p,sizeof p,10510));

    // level control off (in band): a plain copy, bit for bit
    memset(&s,0,sizeof s);
    for(unsigned i=0;i<7;i++){wave(p,i,true);assert(wifi_pcm_push(&s,p,sizeof p,i*10));}
    wifi_pcm_read(&s,out,sizeof out,70);
    assert(s.adjust==0);
    for(int i=0;i<480;i++)assert((int16_t)(out[2*i]|out[2*i+1]<<8)==tri((uint64_t)i));
    // one frame more or fewer: still the triangle, with no step larger than its slope
    int16_t raw[PCM_PACKET_FRAMES+2];
    for(size_t taken=479;taken<=481;taken++) {
        for(size_t i=0;i<=taken;i++)raw[i]=(int16_t)tri(i);
        wifi_pcm_render(raw,taken,out,480);
        for(int i=1;i<480;i++){int a=(int16_t)(out[2*i-2]|out[2*i-1]<<8),b=(int16_t)(out[2*i]|out[2*i+1]<<8);assert(abs(b-a)<=502);}
    }

    // The host stops reading for 3 s (stream closed and opened again) while audio keeps arriving: it starts
    // again from the newest 70 ms, before playing anything, rather than from a 200 ms backlog.
    memset(&s,0,sizeof s);
    unsigned seq=0;int64_t t=0;
    for(;t<1000;t+=10){wave(p,seq++,true);assert(wifi_pcm_push(&s,p,sizeof p,t));wifi_pcm_read(&s,out,sizeof out,t);}
    uint32_t cut=s.dropped;
    for(;t<4000;t+=10){wave(p,seq++,true);assert(wifi_pcm_push(&s,p,sizeof p,t));}
    assert(s.dropped>cut&&s.count>PCM_HIGH_FRAMES);  // nobody read: the cap kept it at 120-200 ms
    wave(p,seq++,true);assert(wifi_pcm_push(&s,p,sizeof p,t));
    wifi_pcm_read(&s,out,sizeof out,t);
    assert(s.flushed>0&&s.count==PCM_PRIME_FRAMES-480&&s.adjust==0);
    // the newest audio: the read ends 70 ms before the last sample received
    uint64_t last=(uint64_t)seq*480,first=last-PCM_PRIME_FRAMES;
    for(int i=0;i<480;i++)assert((int16_t)(out[2*i]|out[2*i+1]<<8)==tri(first+i));

    // 30 virtual minutes each. Measured on the board 2026-10-08: the PC sender ran +12..+84 ppm against the
    // phone, and empty USB packets took a further ~35 ppm; the old buffer cut 80 ms every 10-60 minutes.
    drift(0,0,0,1800);
    drift(150,10,0,1800);
    drift(-150,10,0,1800);
    drift(1500,20,0,1800);
    drift(-1500,20,0,1800);
    drift(150,10,16,1800);  // 160 ms queued before the first read, as several captures had: flushed at once
    return 0;
}
