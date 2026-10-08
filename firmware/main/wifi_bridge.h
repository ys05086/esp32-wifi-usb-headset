#pragma once
#include <stddef.h>
#include <stdint.h>
void wifi_bridge_init(void);
void wifi_bridge_read(uint8_t *out, size_t bytes);
void wifi_bridge_speaker(const uint8_t *stereo, size_t bytes);
