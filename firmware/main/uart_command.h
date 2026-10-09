#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// The COM port carries the log and two kinds of input:
//   't' or 's' outside a setup line: start or stop the probe tone (as before)
//   a line starting with '@': a setup command, e.g. "@get" or "@set {...}", ended by CR or LF
#define UART_COMMAND_MAX 384

typedef enum { UART_NONE, UART_PROBE, UART_SILENCE, UART_LINE, UART_TOO_LONG } uart_event_t;
typedef struct {
    char line[UART_COMMAND_MAX + 1];   // the command without '@', NUL-terminated on UART_LINE
    size_t length;
    bool in_line, overflow, line_start;
} uart_command_t;

void uart_command_init(uart_command_t *c);
uart_event_t uart_command_feed(uart_command_t *c, uint8_t byte);
