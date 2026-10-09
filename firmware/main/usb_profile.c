#include "usb_profile.h"
#include "nvs_flash.h"
#include "nvs.h"
#include <stdint.h>

static vs_usb_mode_t active_mode;
vs_usb_mode_t usb_profile_saved(void) {
    vs_usb_mode_t mode=VS_USB_STANDARD;
    nvs_handle_t handle;
    if(nvs_open("vs_usb",NVS_READONLY,&handle)==ESP_OK) {
        uint8_t value=0;
        // Keep legacy 0/1 settings. Value 2 adds the experimental profile.
        if(nvs_get_u8(handle,"apple",&value)==ESP_OK && value<=VS_USB_ADAPTIVE)
            mode=(vs_usb_mode_t)value;
        nvs_close(handle);
    }
    return mode;
}
void usb_profile_init(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    active_mode=usb_profile_saved();
}
vs_usb_mode_t vs_usb_mode(void) { return active_mode; }
bool vs_usb_apple_feedback(void) { return active_mode==VS_USB_APPLE; }
bool vs_usb_adaptive_out(void) { return active_mode==VS_USB_ADAPTIVE; }
const char *vs_usb_mode_name(void) {
    return active_mode==VS_USB_ADAPTIVE?"adaptive":active_mode==VS_USB_APPLE?"apple":"standard";
}
// TinyUSB asks this when opening the feedback endpoint. Match its descriptor.
bool tud_audio_feedback_format_correction_cb(uint8_t func_id) {
    (void)func_id; return vs_usb_apple_feedback();
}
esp_err_t usb_profile_save(vs_usb_mode_t mode) {
    if(mode<VS_USB_STANDARD || mode>VS_USB_ADAPTIVE) return ESP_ERR_INVALID_ARG;
    nvs_handle_t handle;
    esp_err_t result=nvs_open("vs_usb",NVS_READWRITE,&handle);
    if(result!=ESP_OK) return result;
    result=nvs_set_u8(handle,"apple",(uint8_t)mode);
    if(result==ESP_OK) result=nvs_commit(handle);
    nvs_close(handle); return result;
}
