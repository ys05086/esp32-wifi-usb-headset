#include "uart_command.h"
#include <string.h>

void uart_command_init(uart_command_t *c) {
    memset(c, 0, sizeof *c);
    c->line_start = true;
}

uart_command_event_t uart_command_feed(uart_command_t *c, uint8_t byte) {
    bool end = byte == '\r' || byte == '\n';
    if (!c->in_line) {
        bool start = c->line_start;
        c->line_start = end;
        if (start && byte == '@') { c->in_line = true; c->length = 0; c->overflow = false; return COMMAND_NONE; }
        if (byte == 't') return COMMAND_PROBE;
        if (byte == 's') return COMMAND_SILENCE;
        return COMMAND_NONE;
    }
    if (end) {
        c->in_line = false; c->line_start = true;
        if (c->overflow) return COMMAND_TOO_LONG;
        c->line[c->length] = 0;
        return COMMAND_LINE;
    }
    if (c->length < UART_COMMAND_MAX) c->line[c->length++] = (char)byte;
    else c->overflow = true;
    return COMMAND_NONE;
}
