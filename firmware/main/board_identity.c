#include "board_identity.h"
#include <string.h>

static const char alphabet[] = "abcdefghijkmnpqrstuvwxyz23456789";

void board_ssid_make(const uint8_t mac[6], char out[BOARD_SSID_LEN + 1]) {
    static const char hex[] = "0123456789ABCDEF";
    size_t n = sizeof BOARD_SSID_PREFIX - 1;
    memcpy(out, BOARD_SSID_PREFIX, n);
    out[n] = hex[mac[4] >> 4]; out[n+1] = hex[mac[4] & 15];
    out[n+2] = hex[mac[5] >> 4]; out[n+3] = hex[mac[5] & 15];
    out[n+4] = 0;
}

void board_password_make(const uint8_t random[BOARD_PASSWORD_RANDOM], char out[BOARD_PASSWORD_LEN + 1]) {
    _Static_assert(sizeof alphabet - 1 == 32, "one random byte maps evenly onto 32 letters");
    for (size_t i = 0, o = 0; i < BOARD_PASSWORD_RANDOM; i++) {
        if (i && i % 4 == 0) out[o++] = '-';
        out[o++] = alphabet[random[i] & 31];
    }
    out[BOARD_PASSWORD_LEN] = 0;
}

bool board_password_valid(const char *password) {
    size_t n = strlen(password);
    if (n < 8 || n > 63) return false;
    for (size_t i = 0; i < n; i++)
        if (password[i] < 0x20 || password[i] > 0x7e) return false;
    return true;
}
