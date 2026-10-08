"""Execute extracted pinned driver startup/serialization code with a fake USB host.

The unpatched driver must reproduce the defect, and the patched one must pass.
No hardware/audio is accessed. Requires a C compiler and the managed component.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_tinyusb import PATCHES, patch

PREAMBLE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define TUSB_SPEED_FULL 1
#define TUSB_SPEED_HIGH 2
#define CFG_TUD_AUDIO_ENABLE_FEEDBACK_EP 1
#define TU_VERIFY(x) do { if (!(x)) return false; } while (0)
enum { AUDIO_FEEDBACK_METHOD_FREQUENCY_FIXED, AUDIO_FEEDBACK_METHOD_FREQUENCY_FLOAT,
       AUDIO_FEEDBACK_METHOD_FREQUENCY_POWER_OF_2, AUDIO_FEEDBACK_METHOD_FIFO_COUNT };
typedef struct { unsigned method, sample_freq; struct { unsigned mclk_freq; } frequency; } audio_feedback_params_t;
typedef struct {
  unsigned rhport, ep_fb, ep_out_as_intf_num, ep_out_ff;
  uint32_t *fb_buf;
  struct { unsigned frame_shift, compute_method, min_value, max_value, value;
    bool format_correction;
    struct { struct { unsigned fifo_lvl_thr, fifo_lvl_avg, nom_value;
                     uint16_t rate_const[2]; } fifo_count; } compute;
  } feedback;
} audiod_function_t;
static bool apple;
static unsigned sends, lengths[8];
static uint32_t payloads[8];
static unsigned tud_speed_get(void) { return TUSB_SPEED_FULL; }
static unsigned tu_fifo_depth(unsigned *p) { (void)p; return 384; }
static bool tud_audio_feedback_format_correction_cb(unsigned f) { (void)f; return apple; }
static void tud_audio_feedback_params_cb(unsigned f, unsigned a, audio_feedback_params_t *p) {
  (void)f; (void)a; p->method=AUDIO_FEEDBACK_METHOD_FIFO_COUNT; p->sample_freq=48000;
}
static void audiod_set_fb_params_freq(audiod_function_t *a, unsigned f, unsigned m) { (void)a; (void)f; (void)m; }
static void vs_usb_diag_feedback(unsigned v, unsigned b) { (void)v; (void)b; }
static bool usbd_edpt_xfer(unsigned r, unsigned e, uint8_t *p, unsigned len) {
  (void)r; (void)e;
  lengths[sends]=len; payloads[sends]=0; memcpy(&payloads[sends],p,len); sends++; return true;
}
'''

MAIN = r'''
int main(void) {
  int failed=0;
  for (int mode=0; mode<2; mode++) {
    apple=mode; sends=0;
    uint32_t buffer=0;
    audiod_function_t audio={.ep_fb=0x81,.ep_out_as_intf_num=1,.fb_buf=&buffer};
    if (!open_interface(&audio,1,true)) return 2;
    unsigned wanted_len=apple?3:4;
    uint32_t wanted_value=apple?(48u<<14):(48u<<16);
    if (sends!=1 || lengths[0]!=wanted_len || payloads[0]!=wanted_value) {
      printf("mode %d: first transfer len=%u value=%u (expected %u/%u)\n",mode,lengths[0],payloads[0],wanted_len,wanted_value);
      failed++;
    }
    audio.feedback.compute.fifo_count.fifo_lvl_avg=123456;
    audio.feedback.value=48u<<16;
    if (!open_interface(&audio,2,false)) return 3;
    if (sends!=1 || audio.feedback.compute.fifo_count.fifo_lvl_avg!=123456) {
      puts("Opening microphone reset active speaker feedback"); failed++;
    }
  }
  // Adaptive OUT has no feedback endpoint: opening either stream must not send.
  sends=0;
  uint32_t buffer=0;
  audiod_function_t adaptive={.ep_fb=0,.ep_out_as_intf_num=1,.fb_buf=&buffer};
  if (!open_interface(&adaptive,1,false) || !open_interface(&adaptive,2,false) || sends!=0) return 4;
  return failed?1:0;
}
'''


def harness(source):
    start = source.index('static inline bool audiod_fb_send(')
    end = source.index('\n}\n', start) + 3
    serializer = source[start:end]
    start = source.index('audio->feedback.frame_shift = desc_ep->bInterval - 1;')
    start = source.index('\n', start) + 1
    end = source.index('\n          }', start)
    early_send = source[start:end]
    start = source.index('      // Prepare feedback computation') if '      // Prepare feedback computation' in source else source.index('      // Only initialize the newly opened speaker interface.')
    end = source.index('#endif// CFG_TUD_AUDIO_ENABLE_FEEDBACK_EP', start)
    setup = source[start:end]
    return PREAMBLE + serializer + '\nstatic bool open_interface(audiod_function_t *audio, unsigned itf, bool new_speaker) {\nunsigned func_id=0,alt=1; (void)itf;\nif(new_speaker){\n' + early_send + '\n}\n' + setup + '\nreturn true;\n}\n' + MAIN


def main():
    root = Path(sys.argv[1])
    patch(root)
    patched = (root / 'src/class/audio/audio_device.c').read_text(encoding='utf-8')
    pristine = patched
    for old, new in reversed(PATCHES):
        pristine = pristine.replace(new, old)
    with tempfile.TemporaryDirectory() as folder:
        for label, source, expected in [('pristine', pristine, 1), ('patched', patched, 0)]:
            c = Path(folder) / (label + '.c')
            exe = Path(folder) / (label + '.exe')
            c.write_text(harness(source), encoding='utf-8')
            subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', str(c), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe)], check=False)
            if result.returncode != expected:
                raise RuntimeError(f'{label}: expected {expected}, got {result.returncode}')
            print(f'{label}: {"defect reproduced" if expected else "startup and mic-open regression passed"}', flush=True)


if __name__ == '__main__':
    main()
