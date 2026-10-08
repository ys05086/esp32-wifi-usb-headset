"""Compile actual pinned UAC descriptors and the application's transformation.

Validate every mode's endpoint ownership, lengths, and unchanged mic/clock bytes.
Also execute the patched TinyUSB function-length selection. No audio/hardware.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from patch_uac import patch as patch_uac
from patch_tinyusb import patch as patch_tinyusb

SDK = '''
#define CONFIG_USB_DEVICE_UAC_AS_PART 0
#define CONFIG_UAC_SPEAKER_CHANNEL_NUM 2
#define CONFIG_UAC_MIC_CHANNEL_NUM 1
#define CONFIG_UAC_SAMPLE_RATE 48000
#define CONFIG_UAC_SPK_INTERVAL_MS 1
#define CONFIG_UAC_MIC_INTERVAL_MS 10
#define CONFIG_UAC_BYTES_PER_SAMPLE 2
#define CONFIG_UAC_BIT_RESOLUTION 16
'''
CONFIG = '''
#pragma once
#define CFG_TUSB_MCU OPT_MCU_NONE
#define CFG_TUSB_OS OPT_OS_NONE
#define CFG_TUSB_RHPORT0_MODE (OPT_MODE_DEVICE | OPT_MODE_FULL_SPEED)
#define CFG_TUD_ENDPOINT0_SIZE 64
#define CFG_TUD_AUDIO 1
#define TUP_DCD_ENDPOINT_MAX 8
'''
MAIN = r'''
static size_t endpoint(const uint8_t *p, size_t n, unsigned ep) {
  for(size_t i=0;i<n;i+=p[i]) {
    assert(p[i]>=2 && i+p[i]<=n);
    if(p[i+1]==5 && p[i+2]==ep) return i;
  }
  return 0;
}
int main(void) {
  size_t n=sizeof(desc_configuration);
  assert(n==CONFIG_TOTAL_LEN);
  const uint8_t *result=tud_descriptor_configuration_cb(0);
  assert(result);
  size_t len=result[2] | (size_t)result[3]<<8;
  assert(len==n-(mode==VS_USB_ADAPTIVE?7:0));
  assert(driver_length((unsigned)len-17)==len-17); // p_desc starts after config+IAD.
  assert(driver_length((unsigned)len-18)==0); // refuse short descriptors.
  assert(tud_descriptor_configuration_cb(0)==result);
  unsigned endpoints=0, declared=0, counted=0;
  for(size_t i=0;i<len;i+=result[i]) {
    assert(result[i]>=2 && i+result[i]<=len);
    if(result[i+1]==4) {
      assert(declared==counted); declared=result[i+4];counted=0;
    }
    if(result[i+1]==5) {counted++; endpoints++;}
  }
  assert(declared==counted);
  assert(endpoints==(mode==VS_USB_ADAPTIVE?2:3));
  size_t mic=endpoint(result,len,0x82), original_mic=endpoint(desc_configuration,n,0x82);
  assert(mic && !memcmp(result+mic,desc_configuration+original_mic,7));
  size_t speaker=endpoint(result,len,0x01), fb=endpoint(result,len,0x81);
  assert(speaker && result[speaker+3]==(mode==VS_USB_ADAPTIVE?0x09:0x05));
  if(mode==VS_USB_ADAPTIVE) assert(!fb);
  else assert(fb && result[fb+4]==(mode==VS_USB_APPLE?3:4));
  // AC clock and terminal tree is bit-identical, up to the first speaker AS interface.
  size_t as=0;
  for(size_t i=9;i<n;i+=desc_configuration[i])
    if(desc_configuration[i+1]==4 && desc_configuration[i+2]==1) {as=i;break;}
  assert(as && !memcmp(result+9,desc_configuration+9,as-9));
  if(mode==VS_USB_STANDARD) assert(!memcmp(result,desc_configuration,n));
  uint8_t bad[sizeof(desc_configuration)], dest[sizeof(desc_configuration)];
  memcpy(bad,desc_configuration,n);bad[9]=0;
  assert(!vs_usb_build_descriptor(bad,n,dest,n,mode));
  assert(!vs_usb_build_descriptor(desc_configuration,n,dest,n-1,mode));
  assert(!vs_usb_build_descriptor(desc_configuration,n,dest,n,(vs_usb_mode_t)3));
  printf("mode %d: actual descriptor length %zu, endpoints %u, mic/clock preserved\n",mode,len,endpoints);
}
'''


def main():
    uac, tiny = map(Path, sys.argv[1:3])
    patch_uac(uac)
    patch_tinyusb(tiny)
    # These callbacks/arrays are the production code, not a handwritten fixture.
    source = (uac / 'tusb/usb_descriptors.c').read_text(encoding='utf-8')
    start = source.index('#define CONFIG_TOTAL_LEN')
    end = source.index('// String Descriptors', start)
    descriptors = source[start:end]
    driver = (tiny / 'src/class/audio/audio_device.c').read_text(encoding='utf-8')
    start = driver.index('          // One UAC2 function;')
    end = driver.index('          break;', start)
    selection = driver[start:end]
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        (folder / 'sdkconfig.h').write_text(SDK)
        (folder / 'tusb_config.h').write_text(CONFIG)
        for mode in range(3):
            code = '''#include <assert.h>
#include <stdio.h>
#include "device/usbd.h"
#include "class/audio/audio.h"
#include "tusb_config_uac.h"
#include "usb_descriptor_profile.h"
'''
            code += f'static vs_usb_mode_t mode={mode};\n'
            code += '''vs_usb_mode_t vs_usb_mode(void) {return mode;}
bool vs_usb_adaptive_out(void) {return mode==VS_USB_ADAPTIVE;}
static unsigned driver_length(unsigned max_len) {
  unsigned i=0;
  struct {unsigned desc_length;} _audiod_fct[1];
'''+selection+'''
  return _audiod_fct[0].desc_length-TUD_AUDIO_DESC_IAD_LEN;
}
'''+descriptors+MAIN
            c, exe = folder / 'test.c', folder / 'test.exe'
            c.write_text(code, encoding='utf-8')
            subprocess.run([os.environ.get('CC','gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(folder), '-I'+str(tiny/'src'), '-I'+str(uac/'tusb_uac'),
                            '-I'+str(ROOT/'main'), str(c), '-o', str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
    print('All three profiles and fail-closed descriptor checks passed.')


if __name__ == '__main__':
    main()
