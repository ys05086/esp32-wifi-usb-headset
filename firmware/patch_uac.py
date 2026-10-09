"""Backport FIFO fix from espressif/esp-iot-solution#764 onto UAC 1.3.1.

The upstream PR is not merged. Keep the dependency pinned and fail closed on
source drift. This patch runs after IDF dependency resolution, before compiling.
"""
import hashlib
from pathlib import Path
import sys

HEADER_OLD = '#define CFG_TUD_AUDIO_FUNC_1_EP_IN_SW_BUF_SZ      CFG_TUD_AUDIO_FUNC_1_FORMAT_1_EP_SZ_IN * (MIC_INTERVAL_MS + 1)'
# The first backport (22 packets) left the producer ~5 ms between its refill request and an empty FIFO; it is
# restored like the original before patching, so a component patched by an older build still verifies.
HEADER_PREVIOUS = '''// Headset backport: enough space for refill gate and flow-control midpoint.
#define UAC_MIC_FIFO_PACKETS ((2 * MIC_INTERVAL_MS + 2) > 4 ? (2 * MIC_INTERVAL_MS + 2) : 4)
#define CFG_TUD_AUDIO_FUNC_1_EP_IN_SW_BUF_SZ      (CFG_TUD_AUDIO_FUNC_1_FORMAT_1_EP_SZ_IN * UAC_MIC_FIFO_PACKETS)'''
HEADER_NEW = '''// Headset backport: enough space for refill gate and flow-control midpoint.
// 62 packets (6 KB): the producer is asked at (depth - block) / 2 and the FIFO runs dry ~25 ms later.
// With 22 it was ~5 ms; late producers (up to 34 ms traced) sent empty packets, and iOS answered each
// with 0.1-0.5 s of clicks. Costs ~20 ms more latency, as the FIFO settles at half.
#define UAC_MIC_FIFO_PACKETS ((6 * MIC_INTERVAL_MS + 2) > 4 ? (6 * MIC_INTERVAL_MS + 2) : 4)
#define CFG_TUD_AUDIO_FUNC_1_EP_IN_SW_BUF_SZ      (CFG_TUD_AUDIO_FUNC_1_FORMAT_1_EP_SZ_IN * UAC_MIC_FIFO_PACKETS)'''
SOURCE_OLD = '        xTaskNotifyGive(s_uac_device->mic_task_handle);'
SOURCE_NEW = '''        // Headset backport: prime to half-full before waking the producer.
        // This project has exactly one audio function, with mono PCM16 frames.
        tu_fifo_t *in_ff = tud_audio_get_ep_in_ff();
        if (in_ff != NULL) {
            static const uint8_t zeros[64] = {0};
            uint16_t frame_bytes = MIC_CHANNEL_NUM * CFG_TUD_AUDIO_FUNC_1_FORMAT_1_N_BYTES_PER_SAMPLE_TX;
            uint16_t want = (tu_fifo_depth(in_ff) / 2 / frame_bytes) * frame_bytes;
            while (want > 0) {
                uint16_t chunk = (want > sizeof(zeros)) ? (uint16_t)sizeof(zeros) : want;
                if (tud_audio_write(zeros, chunk) != chunk) {
                    break;
                }
                want -= chunk;
            }
        }
        xTaskNotifyGive(s_uac_device->mic_task_handle);'''

DESCRIPTOR_OLD = '    return desc_configuration;'
DESCRIPTOR_PREVIOUS = '''    // TinyUSB full-speed feedback must match both payload format and EP size.
    // Explicit board profile avoids guessing the host OS from USB requests.
    extern bool vs_usb_apple_feedback(void);
    static uint8_t selected[sizeof(desc_configuration)];
    memcpy(selected, desc_configuration, sizeof(selected));
    for (size_t i = 0; i + 2 <= sizeof(selected) && selected[i] >= 2; i += selected[i]) {
        if (i + selected[i] > sizeof(selected)) break;
        if (selected[i+1] == TUSB_DESC_ENDPOINT && selected[i] >= 7 && selected[i+2] == EPNUM_AUDIO_FB) {
            selected[i+4] = vs_usb_apple_feedback() ? 3 : 4;
            selected[i+5] = 0;
        }
    }
    return selected;'''

DESCRIPTOR_NEW = '''    extern vs_usb_mode_t vs_usb_mode(void);
    static uint8_t selected[sizeof(desc_configuration)];
    // Cached configuration stays valid until reboot; mode changes require reboot.
    static bool ready;
    if (!ready) {
        if (!vs_usb_build_descriptor(desc_configuration, sizeof(desc_configuration),
                                     selected, sizeof(selected), vs_usb_mode())) return NULL;
        ready = true;
    }
    return selected;'''
DESCRIPTOR_INCLUDE_OLD = '#include "uac_descriptors.h"'
DESCRIPTOR_INCLUDE_NEW = DESCRIPTOR_INCLUDE_OLD + '\n#include "usb_descriptor_profile.h"'

PATCHES = [
    ('tusb_uac/tusb_config_uac.h', '47bc7c2520358f2f37ff40cbd8ad4fbde1fdb52e2314dd0739f81d2772a401a2', HEADER_OLD, HEADER_NEW),
    ('usb_device_uac.c', '5980c6c8445001e8728164e43a2371f9b306a005419b0f836d9b7729c26a05d5', SOURCE_OLD, SOURCE_NEW),
    ('tusb/usb_descriptors.c', '606665f4e6c2247d6d272a8ef715c8c36f20336649b97a88289bd3751617d318', DESCRIPTOR_OLD, DESCRIPTOR_NEW),
]
AS_OLD = '#define CFG_TUD_AUDIO_FUNC_1_N_AS_INT             1'
AS_NEW = '#define CFG_TUD_AUDIO_FUNC_1_N_AS_INT             ((MIC_CHANNEL_NUM > 0) + (SPEAK_CHANNEL_NUM > 0))'

# UAC 1.3.1 shares one speaker buffer between the USB ISR and a task. A new
# packet can overwrite that buffer while the task reads it. Transfer ownership
# through a bounded queue, using the ISR-safe FreeRTOS API on TinyUSB 0.19.
SPEAKER_PATCHES = [
    ('static uac_device_t *s_uac_device = NULL;', '''static uac_device_t *s_uac_device = NULL;
#include "freertos/queue.h"
// One packet (192 bytes) per chunk; the first read after a stream restart takes half the FIFO (<= 980).
typedef struct { size_t size; uint8_t data[1024]; } vs_speaker_block_t;
_Static_assert(SPK_INTERVAL_MS * CFG_TUD_AUDIO_FUNC_1_FORMAT_1_EP_SZ_OUT / 2 <= 1024, "speaker chunk too small");
static QueueHandle_t vs_speaker_queue;'''),
    ('''    s_uac_device->spk_data_size = tud_audio_n_read(func_id, s_uac_device->spk_buf, bytes_require);
    xTaskNotifyGive(s_uac_device->spk_task_handle);''', '''    static vs_speaker_block_t block; // USB ISR owns the producer buffer.
    block.size = tud_audio_n_read(func_id, block.data, bytes_require);
    if (block.size && vs_speaker_queue) {
        if (xPortInIsrContext()) {
            BaseType_t woken = pdFALSE;
            xQueueSendFromISR(vs_speaker_queue, &block, &woken);
            if (woken) portYIELD_FROM_ISR();
        } else {
            xQueueSend(vs_speaker_queue, &block, 0);
        }
    }'''),
    ('''        // clear the notification
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (s_uac_device->spk_data_size == 0) {
            continue;
        }
        // playback the data from the ring buffer chunk by chunk
        if (s_uac_device->user_cfg.output_cb) {
            s_uac_device->user_cfg.output_cb((uint8_t *)s_uac_device->spk_buf, s_uac_device->spk_data_size, s_uac_device->user_cfg.cb_ctx);
        }
        s_uac_device->spk_data_size = 0;''', '''        static vs_speaker_block_t block; // Only this task owns the consumer buffer.
        if (xQueueReceive(vs_speaker_queue, &block, pdMS_TO_TICKS(20)) != pdTRUE) continue;
        if (s_uac_device->spk_active && s_uac_device->user_cfg.output_cb) {
            s_uac_device->user_cfg.output_cb(block.data, block.size, s_uac_device->user_cfg.cb_ctx);
        }'''),
    ('    BaseType_t ret_val;', '''    BaseType_t ret_val;
    vs_speaker_queue = xQueueCreate(24, sizeof(vs_speaker_block_t));   // 24 ms of packets
    ESP_RETURN_ON_FALSE(vs_speaker_queue != NULL, ESP_ERR_NO_MEM, TAG, "Speaker queue allocation failed");'''),
]

MIC_PACING_PATCHES = [
    ('#include "usb_device_uac.h"', '#include "usb_device_uac.h"\n#include "usb_mic_refill.h"'),
    ('''    if (fifo_remained < bytes_require) {
        return true;
    }''', '''    if (fifo_remained < bytes_require ||
        !vs_usb_mic_should_refill(tu_fifo_count(sw_in_fifo), tu_fifo_depth(sw_in_fifo), bytes_require)) {
        return true;
    }'''),
    ('''    // load data chunk by chunk
    UAC_ENTER_CRITICAL();''', '''    // Wake the producer only after consuming its staged block. A periodic
    // producer can overwrite unread audio when simultaneous USB OUT adds load.
    bool refill = false;
    UAC_ENTER_CRITICAL();'''),
    ('''        s_uac_device->mic_data_size = 0;
    }
    UAC_EXIT_CRITICAL();

    return true;''', '''        s_uac_device->mic_data_size = 0;
        refill = true;
    }
    UAC_EXIT_CRITICAL();
    if (refill) {
        if (xPortInIsrContext()) {
            BaseType_t woken = pdFALSE;
            vTaskNotifyGiveFromISR(s_uac_device->mic_task_handle, &woken);
            if (woken) portYIELD_FROM_ISR();
        } else xTaskNotifyGive(s_uac_device->mic_task_handle);
    }

    return true;'''),
    ('    TickType_t xLastWakeTime = xTaskGetTickCount();', '    // USB IN consumption paces this producer.'),
    ('            xLastWakeTime = xTaskGetTickCount();', '            // Endpoint opening wakes the first block.'),
    ('        vTaskDelayUntil(&xLastWakeTime, pdMS_TO_TICKS(MIC_INTERVAL_MS));', '        ulTaskNotifyTake(pdTRUE, portMAX_DELAY); // Headset: wait for USB IN consumption'),
]



# Speaker diagnostics, applied last and restored first: what the USB ISR hands over (zero chunks, a full
# handoff queue) and how often a 10 ms packet gap restarts the stream.
SPEAKER_DIAG_PATCHES = [
    ('            xQueueSendFromISR(vs_speaker_queue, &block, &woken);',
     '            extern void vs_usb_diag_speaker_chunk(const uint8_t *data, unsigned size, bool queued);\n'
     '            vs_usb_diag_speaker_chunk(block.data, block.size, xQueueSendFromISR(vs_speaker_queue, &block, &woken) == pdTRUE);'),
    ('            xQueueSend(vs_speaker_queue, &block, 0);',
     '            extern void vs_usb_diag_speaker_chunk(const uint8_t *data, unsigned size, bool queued);\n'
     '            vs_usb_diag_speaker_chunk(block.data, block.size, xQueueSend(vs_speaker_queue, &block, 0) == pdTRUE);'),
    ('        if (xQueueReceive(vs_speaker_queue, &block, pdMS_TO_TICKS(20)) != pdTRUE) continue;',
     '        if (xQueueReceive(vs_speaker_queue, &block, pdMS_TO_TICKS(20)) != pdTRUE) continue;\n'
     '        extern void vs_usb_diag_speaker_backlog(unsigned waiting);\n'
     '        vs_usb_diag_speaker_backlog(uxQueueMessagesWaiting(vs_speaker_queue) + 1);'),
    ('        new_play = true;\n        tud_audio_n_clear_ep_out_ff(func_id);',
     '        new_play = true;\n        extern void vs_usb_diag_speaker_restart(void);\n        vs_usb_diag_speaker_restart();\n'
     '        tud_audio_n_clear_ep_out_ff(func_id);'),
]

# The phone's speaker volume and mute go to the board, which applies them to the sound sent to the PC (an
# iPhone sends the stream at full scale and leaves the volume to the device). Channels past the speaker's
# are refused: the stored arrays have one slot per channel. Applied last and restored first.
VOLUME_PATCHES = [
    ('''    TU_ASSERT(request->bEntityID == UAC2_ENTITY_SPK_FEATURE_UNIT);
    TU_VERIFY(request->bRequest == AUDIO_CS_REQ_CUR);''',
     '''    TU_ASSERT(request->bEntityID == UAC2_ENTITY_SPK_FEATURE_UNIT);
    TU_VERIFY(request->bRequest == AUDIO_CS_REQ_CUR);
    TU_VERIFY(request->bChannelNumber <= CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX);'''),
    ('''        s_uac_device->mute[request->bChannelNumber] = ((audio_control_cur_1_t const *)buf)->bCur;''',
     '''        s_uac_device->mute[request->bChannelNumber] = ((audio_control_cur_1_t const *)buf)->bCur;
        extern void vs_speaker_mute(unsigned channel, bool mute);
        vs_speaker_mute(request->bChannelNumber, s_uac_device->mute[request->bChannelNumber] != 0);'''),
    ('''        s_uac_device->volume[request->bChannelNumber] = ((audio_control_cur_2_t const *)buf)->bCur;''',
     '''        s_uac_device->volume[request->bChannelNumber] = ((audio_control_cur_2_t const *)buf)->bCur;
        extern void vs_speaker_volume(unsigned channel, int16_t volume);
        vs_speaker_volume(request->bChannelNumber, s_uac_device->volume[request->bChannelNumber]);'''),
]

# Added after pacing patches; restore these FIRST so pinned source hashes remain valid.
TRACE_PATCHES = [
    ('#include "usb_mic_refill.h"', '#include "usb_mic_refill.h"\n#include "usb_mic_trace.h"'),
    ('        xTaskNotifyGive(s_uac_device->mic_task_handle);',
     '        vs_mic_trace_request();\n        xTaskNotifyGive(s_uac_device->mic_task_handle);'),
    ('    if (refill) {', '    if (refill) {\n        vs_mic_trace_request();'),
    ('        s_uac_device->mic_data_size = 0;\n        refill = true;',
     '        s_uac_device->mic_data_size = 0;\n        vs_mic_trace_consumed();\n        refill = true;'),
    ('            size_t bytes_read = 0;', '            vs_mic_trace_begin();\n            size_t bytes_read = 0;'),
    ('            s_uac_device->mic_data_size = bytes_read;',
     '            s_uac_device->mic_data_size = bytes_read;\n            vs_mic_trace_ready(bytes_read);'),
]

def patch(root):
    pending = []
    for relative, expected, old, new in PATCHES:
        path = root / relative
        original = path.read_text(encoding='utf-8')
        if relative == 'tusb/usb_descriptors.c':
            original = original.replace(DESCRIPTOR_PREVIOUS, DESCRIPTOR_OLD).replace(DESCRIPTOR_INCLUDE_NEW, DESCRIPTOR_INCLUDE_OLD)
        if relative == 'usb_device_uac.c':
            for volume_old, volume_new in reversed(VOLUME_PATCHES):
                original = original.replace(volume_new, volume_old)
            for diag_old, diag_new in reversed(SPEAKER_DIAG_PATCHES):
                original = original.replace(diag_new, diag_old)
            for trace_old, trace_new in reversed(TRACE_PATCHES):
                original = original.replace(trace_new, trace_old)
            for extra_old, extra_new in SPEAKER_PATCHES + MIC_PACING_PATCHES:
                original = original.replace(extra_new, extra_old)
        if relative.endswith('tusb_config_uac.h'):
            original = original.replace(AS_NEW, AS_OLD).replace(HEADER_PREVIOUS, HEADER_OLD)
        restored = original.replace(new, old) if new in original else original
        if hashlib.sha256(restored.encode()).hexdigest() != expected:
            raise RuntimeError(f'Unexpected UAC 1.3.1 source: {path}')
        if restored.count(old) != 1:
            raise RuntimeError(f'Ambiguous patch anchor: {path}')
        content = restored.replace(old, new)
        if relative == 'usb_device_uac.c':
            for extra_old, extra_new in SPEAKER_PATCHES + MIC_PACING_PATCHES + TRACE_PATCHES + SPEAKER_DIAG_PATCHES + VOLUME_PATCHES:
                if content.count(extra_old) != 1:
                    raise RuntimeError('Unexpected speaker handoff source')
                content = content.replace(extra_old, extra_new)
        if relative.endswith('tusb_config_uac.h'):
            if content.count(AS_OLD) != 1:
                raise RuntimeError('Unexpected UAC streaming interface count')
            content = content.replace(AS_OLD, AS_NEW)
        if relative == 'tusb/usb_descriptors.c':
            if content.count(DESCRIPTOR_INCLUDE_OLD) != 1: raise RuntimeError('Unexpected descriptor include')
            content = content.replace(DESCRIPTOR_INCLUDE_OLD, DESCRIPTOR_INCLUDE_NEW)
        pending.append((path, content))
    for path, content in pending:
        path.write_text(content, encoding='utf-8', newline='\n')
    helper = Path(__file__).parent / 'main' / 'usb_mic_refill.h'
    (root / 'usb_mic_refill.h').write_text(helper.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    descriptor_helper = Path(__file__).parent / 'main' / 'usb_descriptor_profile.h'
    (root / 'tusb' / descriptor_helper.name).write_text(descriptor_helper.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    trace_header = Path(__file__).parent / 'main' / 'usb_mic_trace.h'
    (root / trace_header.name).write_text(trace_header.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    print('UAC 1.3.1: microphone FIFO depth/startup patch verified')


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
