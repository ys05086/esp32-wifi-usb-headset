"""Pinned TinyUSB 0.19.0~3: initialize feedback before the first USB transfer."""
import hashlib
from pathlib import Path
import sys

EXPECTED = '5b684293f812f6948ea27193a1d190d27bd9f75e195175d344b560e919f5dcf9'
DWC_EXPECTED = 'b02378ee5b90f4eb00fee6289ab7531432e7e41b91e618c0319890b03b9fb25f'
# Restricted backport of TinyUSB d4fa8912c598ec6ef020d4e46ebd33c716e24dbb:
# prime single ISO IN packets directly, preserving EP0/non-ISO and DMA paths.
DWC_OLD = '''    // Enable tx fifo empty interrupt only if there is data. Note must after depctl enable
    if (dir == TUSB_DIR_IN && total_bytes != 0) {
      dwc2->diepempmsk |= (1 << epnum);
    }'''
DWC_NEW = '''    // Headset: ISO audio cannot afford a second interrupt before
    // its first packet reaches the hardware FIFO (TinyUSB d4fa8912 backport).
    if (dir == TUSB_DIR_IN && total_bytes != 0) {
      if (depctl.type == DEPCTL_EPTYPE_ISOCHRONOUS && num_packets == 1 &&
          total_bytes <= ((dep->dtxfsts & DTXFSTS_INEPTFSAV_Msk) << 2)) {
        dwc2->diepempmsk &= ~(1u << epnum);
        if (xfer->ff) {
          volatile uint32_t* tx_fifo = dwc2->fifo[epnum];
          tu_fifo_read_n_const_addr_full_words(xfer->ff, (void*)(uintptr_t)tx_fifo, total_bytes);
        } else {
          dfifo_write_packet(dwc2, epnum, xfer->buffer, total_bytes);
          xfer->buffer += total_bytes;
        }
      } else {
        dwc2->diepempmsk |= (1u << epnum);
      }
    }'''
DWC_IN_IRQ = '''  // IN endpoint interrupt handling.
  if (gintsts & GINTSTS_IEPINT) {
    // IEPINT bit read-only, clear using DIEPINTn
    handle_ep_irq(rhport, TUSB_DIR_IN);
  }

'''
DWC_RX_ANCHOR = '''#if CFG_TUD_DWC2_SLAVE_ENABLE
  // RxFIFO non-empty interrupt handling.'''
DWC_ISO_ANCHOR = '''  // Incomplete isochronous IN transfer interrupt handling.'''
DWC_RETRY_OLD = '''      if (xfer->iso_retry > 0) {
        xfer->iso_retry--;'''
DWC_RETRY_NEW = '''      if (xfer->iso_retry > 0) {
        extern void vs_usb_diag_retry(unsigned ep_addr);
        vs_usb_diag_retry(epnum | TUSB_DIR_IN_MASK);
        xfer->iso_retry--;'''


# Frame-level diagnostics and the late re-arm fix, applied last and restored first: the frame each
# isochronous endpoint is armed in, the frame each OUT packet arrived in, and arming the right frame.
DWC_DIAG_PATCHES = [
    ("""      const uint16_t byte_count = grxstsp.byte_count;
      xfer_ctl_t* xfer = XFER_CTL_BASE(epnum, TUSB_DIR_OUT);
""", """      const uint16_t byte_count = grxstsp.byte_count;
      xfer_ctl_t* xfer = XFER_CTL_BASE(epnum, TUSB_DIR_OUT);
      if (epnum) {
        extern void vs_usb_diag_out_rx(unsigned frame4);
        vs_usb_diag_out_rx(grxstsp.frame_number);
      }
"""),
    ("""  uint8_t iso_retry; // ISO retry counter
} xfer_ctl_t;""", """  uint8_t iso_retry; // ISO retry counter
  uint16_t iso_frame;       // Headset: the frame this isochronous endpoint was last armed for
  bool iso_frame_valid;
} xfer_ctl_t;"""),
    # The fix. An endpoint is armed for the frame after the current one. When the interrupt that re-arms it
    # runs just after the SOF of the frame following the one it last served (the microphone's IN work is
    # handled first, and the speaker's packet comes late in the frame), that skips a frame and its packet:
    # 1.5-2% lost while both directions stream, none with the speaker alone. Arm that frame instead.
    ("""  if (depctl.type == DEPCTL_EPTYPE_ISOCHRONOUS) {
    const dwc2_dsts_t dsts = {.value = dwc2->dsts};
    const uint32_t odd_now = dsts.frame_number & 1u;
    if (odd_now) {
      depctl.set_data0_iso_even = 1;
    } else {
      depctl.set_data1_iso_odd = 1;
    }
  }""", """  if (depctl.type == DEPCTL_EPTYPE_ISOCHRONOUS) {
    const dwc2_dsts_t dsts = {.value = dwc2->dsts};
    const uint32_t now = dsts.frame_number;
    uint32_t target = (now + 1u) & 0x3FFFu;
    if (xfer->iso_frame_valid && ((xfer->iso_frame + 1u) & 0x3FFFu) == now) {
      target = now;   // re-armed after that frame's SOF: its packet is still to come
    }
    xfer->iso_frame = (uint16_t) target;
    xfer->iso_frame_valid = true;
    extern void vs_usb_diag_iso_arm(unsigned epnum, unsigned dir, unsigned frame);
    vs_usb_diag_iso_arm(epnum, dir, now);
    if (target & 1u) {
      depctl.set_data1_iso_odd = 1;
    } else {
      depctl.set_data0_iso_even = 1;
    }
  }"""),
    # The IN retry re-arms for the next frame by itself: keep the record in step.
    ("""        if (odd_now) {
          depctl.set_data0_iso_even = 1;
        } else {
          depctl.set_data1_iso_odd = 1;
        }
        epin->diepctl = depctl.value;""", """        xfer->iso_frame = (uint16_t) ((dsts.frame_number + 1u) & 0x3FFFu);
        xfer->iso_frame_valid = true;
        if (odd_now) {
          depctl.set_data0_iso_even = 1;
        } else {
          depctl.set_data1_iso_odd = 1;
        }
        epin->diepctl = depctl.value;"""),
]


def patch_dwc(root):
    path = root / 'src/portable/synopsys/dwc2/dcd_dwc2.c'
    original = path.read_text(encoding='utf-8')
    for diag_old, diag_new in reversed(DWC_DIAG_PATCHES):
        original = original.replace(diag_new, diag_old)
    original = original.replace(DWC_NEW, DWC_OLD)
    original = original.replace(DWC_RETRY_NEW, DWC_RETRY_OLD)
    if DWC_IN_IRQ + DWC_RX_ANCHOR in original:
        original = original.replace(DWC_IN_IRQ + DWC_RX_ANCHOR, DWC_RX_ANCHOR)
        original = original.replace(DWC_ISO_ANCHOR, DWC_IN_IRQ + DWC_ISO_ANCHOR)
    if hashlib.sha256(original.encode()).hexdigest() != DWC_EXPECTED or original.count(DWC_OLD) != 1:
        raise RuntimeError(f'Unexpected pinned DWC2 source: {path}')
    # Upstream b4e7c25c: service IN before OUT at high interrupt latency.
    for anchor in (DWC_IN_IRQ, DWC_RX_ANCHOR, DWC_RETRY_OLD):
        if original.count(anchor) != 1:
            raise RuntimeError('Ambiguous DWC2 IRQ patch')
    content = original.replace(DWC_OLD, DWC_NEW).replace(DWC_IN_IRQ, '')
    content = content.replace(DWC_RX_ANCHOR, DWC_IN_IRQ + DWC_RX_ANCHOR)
    content = content.replace(DWC_RETRY_OLD, DWC_RETRY_NEW)
    for diag_old, diag_new in DWC_DIAG_PATCHES:
        if content.count(diag_old) != 1:
            raise RuntimeError('Ambiguous DWC2 diagnostic patch')
        content = content.replace(diag_old, diag_new)
    path.write_text(content, encoding='utf-8', newline='\n')

PATCHES = [
    ('  // Send everything in ISO EP FIFO\n  uint16_t n_bytes_tx;', '''  // A staged block may already be ready when the previous FIFO runs dry.
  // Rescue only this starvation case before packet sizing; keep the normal
  // post-submit refill gate and its flow-control midpoint unchanged.
  #if CFG_TUD_AUDIO_EP_IN_FLOW_CONTROL
  if (audio->packet_sz_tx[0] && tu_fifo_count(&audio->ep_in_ff) < audio->packet_sz_tx[0]) {
    TU_VERIFY(tud_audio_tx_done_isr(rhport, n_bytes_sent, idx_audio_fct, audio->ep_in, audio->ep_in_alt));
    extern void vs_usb_diag_mic_prefill(bool recovered);
    vs_usb_diag_mic_prefill(tu_fifo_count(&audio->ep_in_ff) >= audio->packet_sz_tx[0]);
  }
  #endif
  // Send everything in ISO EP FIFO
  uint16_t n_bytes_tx;'''),
    ('  uint16_t n_bytes_tx;', '''  uint16_t n_bytes_tx;
  uint16_t vs_fifo_before = tu_fifo_count(&audio->ep_in_ff);'''),
    ('  #if USE_LINEAR_BUFFER_TX\n  tu_fifo_read_n(&audio->ep_in_ff, audio->lin_buf_in, n_bytes_tx);',
     '''  // Trace before scheduling, without changing packet sizing/refill order.
  extern void vs_mic_trace_plan(unsigned fifo_bytes, unsigned requested_bytes);
  vs_mic_trace_plan(vs_fifo_before, n_bytes_tx);
  #if USE_LINEAR_BUFFER_TX
  tu_fifo_read_n(&audio->ep_in_ff, audio->lin_buf_in, n_bytes_tx);'''),
    ('          _audiod_fct[i].desc_length = CFG_TUD_AUDIO_FUNC_1_DESC_LEN;', '''          // One UAC2 function; adaptive OUT removes its 7-byte feedback descriptor.
          extern bool vs_usb_adaptive_out(void);
          _audiod_fct[i].desc_length = CFG_TUD_AUDIO_FUNC_1_DESC_LEN - (vs_usb_adaptive_out() ? 7 : 0);
          TU_VERIFY(_audiod_fct[i].desc_length >= TUD_AUDIO_DESC_IAD_LEN &&
                    _audiod_fct[i].desc_length - TUD_AUDIO_DESC_IAD_LEN <= max_len);'''),
    ('    usbd_edpt_close(rhport, audio->ep_fb);', '    if (audio->ep_fb) usbd_edpt_close(rhport, audio->ep_fb);'),
    ('      uint8_t const *p_desc_end = _audiod_fct[i].p_desc + _audiod_fct[i].desc_length;',
     '      // Headset: p_desc starts after the IAD, including for a missing feedback EP.\n      uint8_t const *p_desc_end = _audiod_fct[i].p_desc + _audiod_fct[i].desc_length - TUD_AUDIO_DESC_IAD_LEN;'),
    ('''void audiod_reset(uint8_t rhport) {
  (void) rhport;''', '''void audiod_reset(uint8_t rhport) {
  (void) rhport;
  vs_usb_diag_state(false, false);'''),
    ('#include "audio_device.h"', '''#include "audio_device.h"
// Headset diagnostic hooks: counters only, no allocation or logging in ISR.
extern void vs_usb_diag_xfer(unsigned kind, unsigned result, unsigned bytes);
extern void vs_usb_diag_state(bool mic, bool speaker);
extern void vs_usb_diag_feedback(unsigned value, unsigned bytes);'''),
    ('''            // Schedule first feedback transmit
            audiod_fb_send(audio);''', '''            // Headset: defer until format and nominal rate are initialized.'''),
    ('''      // Prepare feedback computation if endpoint is available
      if (audio->ep_fb != 0) {''', '''      // Only initialize the newly opened speaker interface. Opening the mic
      // must not reset feedback while its endpoint is already transmitting.
      if (audio->ep_fb != 0 && audio->ep_out_as_intf_num == itf) {'''),
    ('''        audio->feedback.max_value = (fb_param.sample_freq / frame_div + 1) << 16;''', '''        audio->feedback.max_value = (fb_param.sample_freq / frame_div + 1) << 16;
        // A valid first packet, including before the first speaker OUT arrives.
        audio->feedback.value = (uint32_t)(((uint64_t)fb_param.sample_freq << 16) / frame_div);'''),
    ('''          // nothing to do
          default:
            break;
        }
      }
#endif// CFG_TUD_AUDIO_ENABLE_FEEDBACK_EP''', '''          // nothing to do
          default:
            break;
        }
        TU_VERIFY(audiod_fb_send(audio));
      }
#endif// CFG_TUD_AUDIO_ENABLE_FEEDBACK_EP'''),
    ('''  tud_control_status(rhport, p_request);

  return true;
}

// Invoked when class request DATA stage is finished.''', '''  vs_usb_diag_state(audio->ep_in != 0, audio->ep_out != 0);
  tud_control_status(rhport, p_request);

  return true;
}

// Invoked when class request DATA stage is finished.'''),
    ('''  return usbd_edpt_xfer(audio->rhport, audio->ep_fb, (uint8_t *) audio->fb_buf, apply_correction ? 3 : 4);''', '''  vs_usb_diag_feedback(audio->feedback.value, apply_correction ? 3 : 4);
  return usbd_edpt_xfer(audio->rhport, audio->ep_fb, (uint8_t *) audio->fb_buf, apply_correction ? 3 : 4);'''),
    ('''    if (audio->ep_in == ep_addr) {
      // USB 2.0''', '''    if (audio->ep_in == ep_addr) {
      vs_usb_diag_xfer(0, result, xferred_bytes);
      // USB 2.0'''),
    ('''    if (audio->ep_out == ep_addr) {
      audiod_rx_xfer_isr''', '''    if (audio->ep_out == ep_addr) {
      vs_usb_diag_xfer(1, result, xferred_bytes);
      audiod_rx_xfer_isr'''),
    ('''    if (audio->ep_fb == ep_addr) {
      // Schedule a transmit''', '''    if (audio->ep_fb == ep_addr) {
      vs_usb_diag_xfer(2, result, xferred_bytes);
      // Schedule a transmit'''),
]


def patch(root):
    path = root / 'src/class/audio/audio_device.c'
    original = path.read_text(encoding='utf-8')
    for old, new in reversed(PATCHES):
        original = original.replace(new, old)
    if hashlib.sha256(original.encode()).hexdigest() != EXPECTED:
        raise RuntimeError(f'Unexpected pinned TinyUSB audio source: {path}')
    content = original
    for old, new in PATCHES:
        if content.count(old) != 1:
            raise RuntimeError(f'Ambiguous TinyUSB patch: {old[:80]}')
        content = content.replace(old, new)
    path.write_text(content, encoding='utf-8', newline='\n')
    patch_dwc(root)
    print('TinyUSB: feedback startup ordering and diagnostic hooks verified')


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
