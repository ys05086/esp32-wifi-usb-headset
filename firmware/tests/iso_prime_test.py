"""Run the actual before/after DWC2 scheduling fragment against fake FIFO I/O."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_tinyusb import DWC_OLD, DWC_NEW

HEAD = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#define TUSB_DIR_IN 1
#define DEPCTL_EPTYPE_ISOCHRONOUS 1
#define DTXFSTS_INEPTFSAV_Msk 0xffff
struct regs { unsigned diepempmsk; uint32_t fifo[3][64]; };
struct transfer { void *ff; uint8_t *buffer; };
static unsigned wrote, fifo_wrote;
static void tu_fifo_read_n_const_addr_full_words(void *f,void *p,unsigned n) {(void)f;(void)p;fifo_wrote+=n;}
static void dfifo_write_packet(struct regs *r,unsigned e,void *b,unsigned n) {(void)r;(void)e;(void)b;wrote+=n;}
static int run(unsigned total_bytes, unsigned dir, unsigned type, unsigned num_packets,
               unsigned space_words, bool use_ff, bool immediate) {
  unsigned epnum=2; struct regs hw={.diepempmsk=4}; struct regs *dwc2=&hw;
  struct {unsigned dtxfsts;} reg={space_words}, *dep=&reg;
  struct {unsigned type;} depctl={type};
  uint8_t buffer[256]; struct transfer transfer={.ff=use_ff?buffer:0,.buffer=buffer}, *xfer=&transfer;
  wrote=fifo_wrote=0;
  (void)dep;(void)depctl;(void)xfer;(void)num_packets;
'''
TAIL = r'''
  if ((wrote+fifo_wrote != (immediate?total_bytes:0)) ||
      (immediate && ((hw.diepempmsk & 4) || xfer->buffer-buffer != (use_ff?0:(int)total_bytes)))) return 1;
  if (immediate && ((use_ff && wrote) || (!use_ff && fifo_wrote))) return 2;
  return 0;
}
int main(void) {
  int failures=0;
  failures+=run(3,1,1,1,1,false,true); // Apple feedback
  failures+=run(4,1,1,1,1,false,true); // Standard feedback
  failures+=run(96,1,1,1,25,true,true); // mono mic software FIFO
  failures+=run(98,1,1,1,25,true,true); // flow-control extra frame
  failures+=run(96,1,1,1,0,true,false); // fallback if hardware lacks space
  failures+=run(96,1,0,1,25,false,false); // non-ISO unchanged
  failures+=run(192,1,1,2,64,true,false); // multi-packet unchanged
  failures+=run(0,1,1,1,25,true,false); // ZLP unchanged
  failures+=run(96,0,1,1,25,true,false); // OUT unchanged
  printf("FIFO scheduling failures: %d\n",failures);
  return failures?1:0;
}
'''
with tempfile.TemporaryDirectory() as folder:
    for name, fragment, expected in [('old',DWC_OLD,1),('new',DWC_NEW,0)]:
        source=Path(folder)/(name+'.c'); exe=Path(folder)/(name+'.exe')
        source.write_text(HEAD+fragment+TAIL,encoding='utf-8')
        subprocess.run([os.environ.get('CC','gcc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',str(source),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)])
        if result.returncode!=expected: raise RuntimeError(f'{name}: unexpected result {result.returncode}')
