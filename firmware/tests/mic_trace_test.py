"""Run the real trace implementation with a deterministic clock, without hardware."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEST = r'''
#include <assert.h>
#include <stdio.h>
#include "usb_mic_trace.h"
static int64_t clock_us=100;
int64_t esp_timer_get_time(void) {return clock_us;}
int main(void) {
  assert(vs_mic_trace_enabled());
  vs_mic_trace_t s;
  vs_mic_trace_stream(true,true);
  vs_mic_trace_source(4800);
  vs_mic_trace_request();
  clock_us+=20;vs_mic_trace_begin();
  clock_us+=30;vs_mic_trace_ready(960);
  vs_mic_trace_plan(1000,96);
  vs_mic_trace_snapshot(&s);
  assert(s.event_count==0 && s.max_wake_us==20 && s.max_render_us==30);
  // Empty plan despite staged data distinguishes refill order from producer starvation.
  clock_us+=1000;vs_mic_trace_plan(0,0);
  vs_mic_trace_snapshot(&s);
  assert(s.planned_empty==1 && s.events[0].kind==1);
  assert(s.events[0].staged_bytes==960 && s.events[0].phase==3);
  assert(s.events[0].source_frames==4800 && s.events[0].speaker_active==1);
  clock_us+=1000;vs_mic_trace_empty_completion();
  vs_mic_trace_consumed();vs_mic_trace_request();
  clock_us+=12000;vs_mic_trace_plan(0,0);
  vs_mic_trace_snapshot(&s);
  assert(s.events[2].phase==1 && s.events[2].request_age_us==12000);
  assert(s.events[2].staged_bytes==0);
  vs_mic_trace_begin();clock_us+=35;vs_mic_trace_ready(960);
  vs_mic_trace_snapshot(&s);
  assert(s.slow_producer==1 && s.max_wake_us==12000 && s.max_render_us==35);
  // A non-empty plan followed by an empty completion is retained as a separate case.
  vs_mic_trace_plan(1000,96);clock_us+=1000;vs_mic_trace_empty_completion();
  vs_mic_trace_snapshot(&s);
  assert(s.events[4].kind==2 && s.events[4].requested_bytes==96);
  assert(s.planned_empty==2 && s.completed_empty==2);
  // Ring retains latest events in sequence order, with bounded memory.
  for(unsigned i=0;i<40;i++){clock_us+=1000;vs_mic_trace_plan(0,0);}
  vs_mic_trace_snapshot(&s);assert(s.event_count==45);
  for(unsigned i=0;i<VS_MIC_TRACE_CAPACITY;i++){
    unsigned seq=s.event_count-VS_MIC_TRACE_CAPACITY+i+1;
    assert(s.events[(seq-1)%VS_MIC_TRACE_CAPACITY].sequence==seq);
  }
  vs_mic_trace_stream(false,false);
  clock_us+=(int64_t)1<<33;vs_mic_trace_stream(true,false);
  vs_mic_trace_plan(0,0);vs_mic_trace_snapshot(&s);
  assert(s.stream==2 && s.events[(s.event_count-1)%VS_MIC_TRACE_CAPACITY].stream_age_us==0);
  assert(s.events[(s.event_count-1)%VS_MIC_TRACE_CAPACITY].at_us>((uint64_t)1<<32));
  puts("Mic trace: starvation/staged-ready/completion distinction, timing, ring and stream restart passed");
}
'''

with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)
    (p/'freertos').mkdir()
    (p/'freertos/FreeRTOS.h').write_text('''#pragma once
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
''')
    (p/'esp_timer.h').write_text('#include <stdint.h>\nint64_t esp_timer_get_time(void);\n')
    (p/'test.c').write_text(TEST)
    exe=p/'trace.exe'
    subprocess.run([os.environ.get('CC','gcc'),'-std=c11','-Wall','-Wextra','-Werror','-DVS_MIC_TRACE_DETAILED=1',
                    '-I'+str(p),'-I'+str(ROOT/'main'),str(p/'test.c'),
                    str(ROOT/'main/usb_mic_trace.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
    (p/'test.c').write_text('''#include <assert.h>
#include "usb_mic_trace.h"
int main(void) {
  vs_mic_trace_t s;
  assert(!vs_mic_trace_enabled());
  vs_mic_trace_stream(1,1);vs_mic_trace_source(9600);
  vs_mic_trace_request();vs_mic_trace_begin();vs_mic_trace_ready(960);
  vs_mic_trace_plan(0,0);vs_mic_trace_empty_completion();vs_mic_trace_consumed();
  vs_mic_trace_snapshot(&s);
  assert(s.event_count==0 && s.plans==0 && s.publications==0);
}
''')
    # No esp_timer_get_time definition: the default build must not read the clock.
    subprocess.run([os.environ.get('CC','gcc'),'-std=c11','-Wall','-Wextra','-Werror',
                    '-I'+str(p),'-I'+str(ROOT/'main'),str(p/'test.c'),
                    str(ROOT/'main/usb_mic_trace.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
    print('Default trace disabled: no timing/event writes or clock dependency')
