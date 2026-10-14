"""PC-side microphone gain; no added audio buffering or device-volume changes."""
import math
import numpy as np

MAX_MICROPHONE_PERCENT = 1000


def microphone_percent(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 100
    return round(min(MAX_MICROPHONE_PERCENT, max(0, value))) if math.isfinite(value) else 100


def microphone_db(percent):
    percent = microphone_percent(percent)
    return 20 * math.log10(percent / 100) if percent else None


class GainRamp:
    """A ten-millisecond ramp, retaining progress across short callbacks."""
    def __init__(self, gain=1.0):
        self.current = self.target = gain
        self.remaining = 0

    def apply(self, samples, gain, sample_rate):
        gain = min(MAX_MICROPHONE_PERCENT / 100, max(0.0, gain)) if math.isfinite(gain) else 1.0
        if gain != self.target:
            self.target = gain
            self.remaining = max(1, round(sample_rate * .01))
        if not self.remaining:
            return samples if gain == 1.0 else samples * gain
        count = min(len(samples), self.remaining)
        output = np.empty_like(samples, dtype=np.float64)
        step = (self.target - self.current) / self.remaining
        output[:count] = samples[:count] * (self.current + step * np.arange(1, count + 1))
        self.current += step * count
        self.remaining -= count
        if not self.remaining:
            self.current = self.target
        output[count:] = samples[count:] * self.current
        return output
