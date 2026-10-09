#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Each board's own Wi-Fi: "ESP32-Headset-1A2B" from its MAC, and a random password made on first boot,
// so knowing this firmware is not enough to join someone's board.
#define BOARD_SSID_PREFIX "ESP32-Headset-"
#define BOARD_SSID_LEN (sizeof BOARD_SSID_PREFIX - 1 + 4)
#define BOARD_PASSWORD_RANDOM 12            // characters drawn, 5 bits each: 60 bits
#define BOARD_PASSWORD_LEN 14               // as shown, "abcd-efgh-jkmn"

void board_ssid_make(const uint8_t mac[6], char out[BOARD_SSID_LEN + 1]);
// One random byte per character; the 32-letter alphabet leaves out 0/o and 1/l so it reads back cleanly.
void board_password_make(const uint8_t random[BOARD_PASSWORD_RANDOM], char out[BOARD_PASSWORD_LEN + 1]);
// WPA2 passphrase rules: 8-63 printable ASCII characters.
bool board_password_valid(const char *password);
