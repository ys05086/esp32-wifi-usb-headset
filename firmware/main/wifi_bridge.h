#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
void wifi_bridge_init(void);
void wifi_bridge_read(uint8_t *out, size_t bytes);
void wifi_bridge_speaker(const uint8_t *stereo, size_t bytes);
// The phone set its speaker volume (1/256 dB) or mute on a feature unit channel (TinyUSB task).
void vs_speaker_volume(unsigned channel, int16_t volume);
void vs_speaker_mute(unsigned channel, bool mute);
// Setup (board_config): put the board's own Wi-Fi name and password into the running access point;
// save and join a router (an empty SSID forgets it); the router's SSID and, when joined, the board's IP there.
esp_err_t wifi_bridge_apply_ap(void);
esp_err_t wifi_bridge_set_station(const char *ssid, const char *password);
bool wifi_bridge_station(char ssid[33], char ip[16]);
