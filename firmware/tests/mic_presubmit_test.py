"""Execute the real pinned TX scheduler to reproduce and prevent avoidable empties.

FIFO/USB are simulated, not physical timing. Test both linear and direct FIFO TX.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from patch_tinyusb import PATCHES, patch

PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "usb_mic_refill.h"
#define CFG_TUD_AUDIO_EP_IN_FLOW_CONTROL 1
#define TU_VERIFY(x) do {if (!(x)) return false;} while(0)
typedef struct {unsigned count,depth; uint8_t data[2156];} tu_fifo_t;
typedef struct {unsigned ep_in_alt,ep_in,ep_in_sz; uint16_t packet_sz_tx[3];
  tu_fifo_t ep_in_ff;uint8_t lin_buf_in[98];} audiod_function_t;
static audiod_function_t *current;
static unsigned staged, sent, callbacks, attempts, recovered, published, next_byte, expected_byte;
static uint16_t tu_fifo_count(tu_fifo_t *f) {return f->count;}
static uint16_t tu_min16(uint16_t a,uint16_t b) {return a<b?a:b;}
static unsigned audiod_get_audio_fct_idx(audiod_function_t *a) {(void)a;return 0;}
static void append(tu_fifo_t *f,unsigned n) {
  assert(f->count+n<=f->depth);
  for(unsigned i=0;i<n;i++)f->data[f->count++]=(uint8_t)next_byte++;
}
static void tu_fifo_read_n(tu_fifo_t *f,uint8_t *out,unsigned n) {
  assert(n<=f->count);memcpy(out,f->data,n);f->count-=n;memmove(f->data,f->data+n,f->count);
}
static bool usbd_edpt_xfer(unsigned r,unsigned ep,uint8_t *p,unsigned n) {
  (void)r;(void)ep;sent=n;
  for(unsigned i=0;i<n;i++)assert(p[i]==(uint8_t)expected_byte++);
  return true;
}
static bool usbd_edpt_xfer_fifo(unsigned r,unsigned ep,tu_fifo_t *f,unsigned n) {
  uint8_t p[98];tu_fifo_read_n(f,p,n);return usbd_edpt_xfer(r,ep,p,n);
}
static bool tud_audio_tx_done_isr(unsigned r,unsigned n,unsigned idx,unsigned ep,unsigned alt) {
  (void)r;(void)n;(void)idx;(void)ep;(void)alt;callbacks++;
  tu_fifo_t *f=&current->ep_in_ff;
  if(staged && vs_usb_mic_should_refill(f->count,f->depth,960)) {
    append(f,staged);staged=0;published++;
  }
  return true;
}
void vs_usb_diag_mic_prefill(bool ok) {attempts++;recovered+=ok;}
void vs_mic_trace_plan(unsigned f,unsigned n) {(void)f;(void)n;}
static void reset(audiod_function_t *a,unsigned count,unsigned ready) {
  *a=(audiod_function_t){.ep_in_alt=1,.ep_in=0x82,.ep_in_sz=98,
       .packet_sz_tx={94,96,98},.ep_in_ff={.depth=2156}};
  current=a;staged=ready;sent=callbacks=attempts=recovered=published=next_byte=expected_byte=0;
  append(&a->ep_in_ff,count);
}
'''
MAIN = r'''
int main(void) {
  audiod_function_t a;
  // Measured starvation states: a complete staged block must be used this packet.
  for(unsigned count=2;count<=82;count+=2) {
    reset(&a,count,960);assert(audiod_tx_xfer_isr(0,&a,96));
    assert(published==1 && callbacks==(FIXED?2u:1u));
    assert(FIXED ? (sent>=94 && attempts==1 && recovered==1) : sent==0);
  }
  // Real producer starvation cannot be repaired by inventing/replaying samples.
  reset(&a,40,0);assert(audiod_tx_xfer_isr(0,&a,96));
  assert(sent==0 && published==0 && recovered==0);
  // Closed stream must neither drain nor stage anything.
  reset(&a,40,960);a.ep_in_alt=0;
  assert(!audiod_tx_xfer_isr(0,&a,96));assert(callbacks==0 && attempts==0);
  // Healthy 2 ms producer: unchanged balanced refill, no sample duplication/loss.
  reset(&a,1078,960);unsigned ready_at=0;int64_t total=0;
  for(unsigned tick=0;tick<180000;tick++) {
    if(!staged && tick>=ready_at)staged=960;
    unsigned prior=published;
    assert(audiod_tx_xfer_isr(0,&a,96));assert(sent>=94 && sent<=98);
    total+=sent/2;
    if(published!=prior)ready_at=tick+2;
  }
  assert(attempts==0 && llabs(total-180000LL*48)<48);
  printf("%s: starvation rescue, empty source, stopped stream, ordered PCM and healthy drift %lld passed\n",
         FIXED?"patched":"old-order reproduced",(long long)(total-180000LL*48));
}
'''

def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start)+2]

def main():
    root = Path(sys.argv[1])
    patch(root)
    patched = (root/'src/class/audio/audio_device.c').read_text(encoding='utf-8')
    pristine = patched
    for old,new in reversed(PATCHES):
        pristine = pristine.replace(new,old)
    with tempfile.TemporaryDirectory() as temp:
        for fixed,source in [(0,pristine),(1,patched)]:
            code = PREAMBLE + function(source,'static uint16_t audiod_tx_packet_size(const uint16_t *norminal_size, uint16_t data_count, uint16_t fifo_depth, uint16_t max_depth) {')
            code += function(source,'static bool audiod_tx_xfer_isr(uint8_t rhport, audiod_function_t * audio, uint16_t n_bytes_sent) {') + MAIN
            p=Path(temp);c=p/'test.c';exe=p/'test.exe';c.write_text(code)
            for linear in [0,1]:
                subprocess.run([os.environ.get('CC','gcc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
                                f'-DFIXED={fixed}',f'-DUSE_LINEAR_BUFFER_TX={linear}',
                                '-I'+str(ROOT/'main'),str(c),'-o',str(exe)],check=True)
                subprocess.run([str(exe)],check=True)

if __name__=='__main__':main()
