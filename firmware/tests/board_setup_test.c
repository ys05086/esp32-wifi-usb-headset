#include "board_identity.h"
#include "uart_command.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void identity(void) {
    char ssid[BOARD_SSID_LEN + 1], password[BOARD_PASSWORD_LEN + 1];
    const uint8_t mac[6] = {0x24, 0x58, 0x7c, 0xd1, 0x1a, 0x2b};
    board_ssid_make(mac, ssid);
    assert(!strcmp(ssid, "ESP32-Headset-1A2B"));
    uint8_t random[BOARD_PASSWORD_RANDOM];
    for (int i = 0; i < BOARD_PASSWORD_RANDOM; i++) random[i] = (uint8_t)(i * 37 + 200);
    board_password_make(random, password);
    assert(strlen(password) == BOARD_PASSWORD_LEN && password[4] == '-' && password[9] == '-');
    assert(board_password_valid(password));
    for (const char *c = password; *c; c++) assert(*c == '-' || strchr("abcdefghijkmnpqrstuvwxyz23456789", *c));
    // every byte value lands on a letter, and the high bits do not matter (no bias over 256 values)
    unsigned seen[32] = {0};
    for (int v = 0; v < 256; v++) {
        memset(random, v, sizeof random);
        board_password_make(random, password);
        seen[strchr("abcdefghijkmnpqrstuvwxyz23456789", password[0]) - "abcdefghijkmnpqrstuvwxyz23456789"]++;
    }
    for (int i = 0; i < 32; i++) assert(seen[i] == 8);
    assert(!board_password_valid("short"));
    assert(!board_password_valid("tab\tinside!"));
    assert(board_password_valid("12345678"));
    char long_one[65]; memset(long_one, 'a', 64); long_one[64] = 0;
    assert(!board_password_valid(long_one));
    long_one[63] = 0;
    assert(board_password_valid(long_one));
}

static uart_event_t feed(uart_command_t *c, const char *text, uart_event_t *last_line) {
    uart_event_t last = UART_NONE;
    for (const char *p = text; *p; p++) {
        uart_event_t e = uart_command_feed(c, (uint8_t)*p);
        if (e != UART_NONE) last = e;
        if (e == UART_LINE && last_line) *last_line = e;
    }
    return last;
}

static void commands(void) {
    uart_command_t c;
    uart_command_init(&c);
    // the probe keys still work on their own
    assert(uart_command_feed(&c, 't') == UART_PROBE);
    assert(uart_command_feed(&c, 's') == UART_SILENCE);
    assert(uart_command_feed(&c, '\n') == UART_NONE);
    // a setup line, with 't' and 's' inside, ends on CR or LF and does not start the probe
    assert(feed(&c, "@set {\"usb_mode\":\"standard\"}\r\n", NULL) == UART_LINE);
    assert(!strcmp(c.line, "set {\"usb_mode\":\"standard\"}"));
    assert(feed(&c, "@get\n", NULL) == UART_LINE && !strcmp(c.line, "get"));
    // '@' in the middle of a line is not a command (a 't' there is a probe key, as any 't' outside a command)
    assert(feed(&c, "x@ge\n", NULL) == UART_NONE);
    // too long: reported once, then the next line works
    char big[UART_COMMAND_MAX + 10];
    big[0] = '@'; memset(big + 1, 'a', sizeof big - 3); big[sizeof big - 2] = '\n'; big[sizeof big - 1] = 0;
    assert(feed(&c, big, NULL) == UART_TOO_LONG);
    assert(feed(&c, "@new-password\n", NULL) == UART_LINE && !strcmp(c.line, "new-password"));
    // exactly the maximum fits
    big[UART_COMMAND_MAX + 1] = '\n'; big[UART_COMMAND_MAX + 2] = 0;
    assert(feed(&c, big, NULL) == UART_LINE && strlen(c.line) == UART_COMMAND_MAX);
}

int main(void) {
    identity();
    commands();
    puts("board setup: identity, password and COM command tests passed");
    return 0;
}
