#pragma once
#include <stdbool.h>
#include "esp_err.h"
#include "usb_descriptor_profile.h"
void usb_profile_init(void);
bool vs_usb_apple_feedback(void);
bool vs_usb_adaptive_out(void);
vs_usb_mode_t vs_usb_mode(void);
const char *vs_usb_mode_name(void);
esp_err_t usb_profile_save(vs_usb_mode_t mode);
