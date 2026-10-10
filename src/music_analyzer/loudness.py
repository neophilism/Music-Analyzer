"""Streaming mono/stereo BS.1770 loudness and EBU Tech 3342 loudness range.

Filter design follows the published De Man/BS.1770 bilinear coefficients.
No true-peak claim is made: peak_dbfs is the maximum original sample magnitude.
"""

from collections import deque

import numpy as np
from scipy.signal import lfilter


def energy_lufs(energy):
    values = np.asarray(energy, dtype=float)
    with np.errstate(divide="ignore"):
        return -0.691 + 10 * np.log10(values)


def _coefficients(rate):
    k = np.tan(np.pi * 1681.974450955533 / rate)
    q = .7071752369554196
    vh = 10 ** (3.999843853973347 / 20)
    vb = vh ** .4996667741545416
    denominator = 1 + k / q + k * k
    shelf_b = np.array([vh + vb * k / q + k * k, 2 * (k * k - vh), vh - vb * k / q + k * k]) / denominator
    shelf_a = np.array([1, 2 * (k * k - 1) / denominator, (1 - k / q + k * k) / denominator])
    k = np.tan(np.pi * 38.13547087602444 / rate)
    q = .5003270373238773
    denominator = 1 + k / q + k * k
    high_b = np.array([1., -2., 1.])
    high_a = np.array([1, 2 * (k * k - 1) / denominator, (1 - k / q + k * k) / denominator])
    return [(shelf_b, shelf_a), (high_b, high_a)]


class LoudnessMeter:
    def __init__(self, sample_rate: int, channels: int, sustained_threshold: float = -18):
        if channels not in {1, 2}:
            raise ValueError("BS.1770 mono/stereo only; speaker layout is required for other channels.")
        self.sample_rate, self.channels = sample_rate, channels
        self.threshold = sustained_threshold
        self.filters = _coefficients(sample_rate)
        self.states = [np.zeros((2, channels)) for _ in self.filters]
        self.hop = round(sample_rate * .1)
        self.remaining = np.zeros(0)
        self.recent = deque(maxlen=30)
        self.momentary_energy = []
        self.short_energy = []
        self.times = []
        self.hops = 0
        self.square_sum = self.count = self.peak = 0.0

    def feed(self, samples):
        samples = np.asarray(samples, dtype=np.float64)
        if samples.ndim == 1:
            samples = samples[:, None]
        if samples.shape[1] != self.channels or not np.isfinite(samples).all():
            raise ValueError("Invalid channel count or non-finite samples.")
        self.square_sum += float(np.sum(samples ** 2))
        self.count += samples.size
        if samples.size:
            self.peak = max(self.peak, float(np.max(np.abs(samples))))
        filtered = samples
        for index, (b, a) in enumerate(self.filters):
            filtered, self.states[index] = lfilter(b, a, filtered, axis=0, zi=self.states[index])
        # Stereo channels have equal BS.1770 weights; do not average their energy.
        energy = np.concatenate([self.remaining, np.sum(filtered ** 2, axis=1)])
        usable = (len(energy) // self.hop) * self.hop
        for value in energy[:usable].reshape(-1, self.hop).mean(axis=1):
            self.recent.append(float(value))
            self.hops += 1
            if len(self.recent) >= 4:
                self.momentary_energy.append(float(np.mean(list(self.recent)[-4:])))
            if len(self.recent) == 30:
                self.short_energy.append(float(np.mean(self.recent)))
                self.times.append(self.hops * self.hop / self.sample_rate)
        self.remaining = energy[usable:]

    def finish(self) -> dict:
        momentary = np.asarray(self.momentary_energy)
        levels = energy_lufs(momentary)
        absolute = momentary[levels > -70]
        integrated = None
        if len(absolute):
            relative_threshold = float(energy_lufs(np.mean(absolute))) - 10
            gated = momentary[(levels > -70) & (levels > relative_threshold)]
            if len(gated):
                integrated = float(energy_lufs(np.mean(gated)))
        short = np.asarray(self.short_energy)
        short_levels = energy_lufs(short)
        absolute_short = short[short_levels > -70]
        lra = None
        if len(absolute_short):
            threshold = float(energy_lufs(np.mean(absolute_short))) - 20
            gated_short = short_levels[(short_levels > -70) & (short_levels > threshold)]
            if len(gated_short):
                p10, p95 = np.percentile(gated_short, [10, 95])
                lra = float(p95 - p10)
        # Very short tracks have no 3-second estimates; report fallback explicitly.
        finite_levels = short_levels[np.isfinite(short_levels)]
        if not len(finite_levels):
            finite_levels = levels[np.isfinite(levels)]
        percentiles = np.percentile(finite_levels, [5, 50, 90, 95]) if len(finite_levels) else [None] * 4
        rms = np.sqrt(self.square_sum / max(self.count, 1))
        rms_dbfs = float(20 * np.log10(rms)) if rms > 0 else None
        peak_dbfs = float(20 * np.log10(self.peak)) if self.peak > 0 else None
        # Downsample the plotted curve only; statistics use all overlapping windows.
        stride = max(1, len(short_levels) // 2000)
        curve = [[float(t), float(level) if np.isfinite(level) else None]
                 for t, level in zip(self.times[::stride], short_levels[::stride], strict=True)]
        return {"integrated_lufs": integrated, "lra_lu": lra, "rms_dbfs": rms_dbfs,
                "peak_dbfs": peak_dbfs,
                "crest_db": peak_dbfs - rms_dbfs if rms_dbfs is not None else None,
                "loudness_p05": None if percentiles[0] is None else float(percentiles[0]),
                "loudness_p50": None if percentiles[1] is None else float(percentiles[1]),
                "loudness_p90": None if percentiles[2] is None else float(percentiles[2]),
                "loudness_spread_lu": float(percentiles[3] - percentiles[0]) if len(finite_levels) else None,
                "loudness_std_lu": float(np.std(finite_levels)) if len(finite_levels) else None,
                "sustained_fraction": float(np.mean(short_levels > self.threshold)) if len(short_levels) else None,
                "sustained_threshold_lufs": self.threshold, "loudness_curve": curve,
                "loudness_short_track": not len(short_levels), "silent": self.peak < 1e-8}
