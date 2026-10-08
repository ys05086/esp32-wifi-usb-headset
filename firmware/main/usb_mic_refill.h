#pragma once
#include <stdbool.h>
#include <stddef.h>

// TinyUSB's IN flow control regulates around half-full. A demand-paced
// producer must therefore center its refill sawtooth around that midpoint,
// rather than filling to capacity and making the host consume too fast.
static inline bool vs_usb_mic_should_refill(size_t count, size_t depth, size_t block)
{
    return block > 0 && depth >= block && count <= (depth - block) / 2;
}
