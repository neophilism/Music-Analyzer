"""Local pulse estimates with explicitly retained octave ambiguity."""

import numpy as np
from scipy.signal import find_peaks, resample_poly

HOP = 256
FRAME = 1024


def mono_resample(samples, source_rate, target_rate=22050):
    data = np.asarray(samples, dtype=np.float32)
    mono = data.mean(axis=1) if data.ndim == 2 else data
    if data.ndim == 2 and np.mean(mono ** 2) < .01 * np.mean(data ** 2):
        mono = data[:, int(np.argmax(np.mean(data ** 2, axis=0)))]
    if source_rate == target_rate:
        return mono
    divisor = np.gcd(source_rate, target_rate)
    return resample_poly(mono, target_rate // divisor, source_rate // divisor).astype(np.float32)


def spectral_features(samples, rate=22050):
    if len(samples) < FRAME:
        return np.zeros(0), {"onset_rate": None, "density_raw": None}
    frames = np.lib.stride_tricks.sliding_window_view(samples, FRAME)[::HOP]
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(FRAME), axis=1)).astype(np.float32)
    flux = np.maximum(np.diff(np.log1p(spectrum * 10), axis=0), 0).mean(axis=1)
    envelope = np.concatenate([[0], flux])
    median = np.median(envelope)
    spread = np.median(np.abs(envelope - median))
    onsets, _ = find_peaks(envelope, height=median + 2 * max(spread, 1e-5),
                           prominence=max(spread, 1e-4), distance=max(1, int(.08 * rate / HOP)))
    duration = len(samples) / rate
    flatness = np.exp(np.mean(np.log(spectrum + 1e-10), axis=1)) / np.maximum(spectrum.mean(axis=1), 1e-10)
    zcr = np.mean(np.abs(np.diff(np.signbit(samples))))
    onset_rate = len(onsets) / duration
    density = .5 * float(np.median(flatness)) + .3 * min(float(zcr) * 4, 1) + .2 * min(onset_rate / 8, 1)
    return envelope, {"onset_rate": float(onset_rate), "density_raw": float(density)}


def estimate_window(envelope, rate=22050):
    envelope = np.asarray(envelope, dtype=float)
    centered = np.maximum(envelope - np.median(envelope), 0)
    if len(centered) < rate / HOP * 3 or np.max(centered, initial=0) < 1e-5:
        return None
    peaks, _ = find_peaks(centered, prominence=np.max(centered) * .15,
                          distance=max(1, int(.08 * rate / HOP)))
    if len(peaks) < 4:
        return None
    intervals = np.diff(peaks)
    cadence = 60 * rate / (HOP * np.mean(intervals))
    regularity = (np.percentile(intervals, 95) - np.percentile(intervals, 5)) / np.median(intervals)
    # Regular attacks give a sub-frame estimate over several intervals. This
    # avoids choosing a third repetition because its lag happens to land exactly
    # on the spectral hop grid. Irregular music falls through to autocorrelation.
    if 40 <= cadence <= 240 and regularity < .15:
        strength = float(max(.25, .9 - regularity))
        return {"raw_bpm": float(cadence), "bpm": float(cadence), "pulse_strength": strength,
                "alternatives": [float(v) for v in (cadence / 2, cadence, cadence * 2) if 30 <= v <= 300]}
    fft_size = 1 << (2 * len(centered) - 1).bit_length()
    transform = np.fft.rfft(centered, n=fft_size)
    acf = np.fft.irfft(transform * transform.conjugate())[:len(centered)]
    if acf[0] <= 1e-12:
        return None
    acf /= acf[0]
    minimum = max(2, int(60 * rate / (240 * HOP)))
    maximum = min(len(acf) - 2, int(60 * rate / (40 * HOP)))
    candidates, _ = find_peaks(acf[minimum:maximum + 1], prominence=.05)
    candidates += minimum
    if not len(candidates):
        return None
    # Biased autocorrelation gently favors the first supported repetition rather
    # than claiming that an arbitrary 120 BPM prior is the observed pulse.
    lag = int(candidates[np.argmax(acf[candidates])])
    strength = float(acf[lag])
    if strength < .20:
        return None
    left, center, right = acf[lag - 1:lag + 2]
    denominator = left - 2 * center + right
    offset = .5 * (left - right) / denominator if abs(denominator) > 1e-12 else 0
    bpm = 60 * rate / (HOP * (lag + np.clip(offset, -.5, .5)))
    return {"raw_bpm": float(bpm), "bpm": float(bpm), "pulse_strength": strength,
            "alternatives": [float(v) for v in (bpm / 2, bpm, bpm * 2) if 30 <= v <= 300]}


def tempo_windows(samples, start, rate=22050):
    envelope, features = spectral_features(samples, rate)
    window = round(12 * rate / HOP)
    step = round(6 * rate / HOP)
    result = []
    for offset in range(0, max(1, len(envelope) - window + 1), step):
        segment = envelope[offset:offset + window]
        estimate = estimate_window(segment, rate)
        if estimate:
            estimate["time"] = float(start + (offset + len(segment) / 2) * HOP / rate)
            result.append(estimate)
    return result, features


def weighted_median(values, weights):
    order = np.argsort(values, kind="stable")
    sorted_values = np.asarray(values)[order]
    cumulative = np.cumsum(np.asarray(weights)[order])
    return float(sorted_values[np.searchsorted(cumulative, cumulative[-1] / 2)])


def summarize_tempo(windows: list[dict]) -> dict:
    if not windows:
        return {"bpm": None, "tempo_spread_bpm": None, "tempo_variability_pct": None,
                "tempo_reliability": 0., "tempo_ambiguous": False, "tempo_curve": [],
                "tempo_status": "No stable pulse detected"}
    windows = [dict(w) for w in windows]
    weights = [w["pulse_strength"] for w in windows]
    reference = np.exp(weighted_median(np.log([w["raw_bpm"] for w in windows]), weights))
    folded = 0
    for window in windows:
        ratio = window["raw_bpm"] / reference
        if ratio > 1.7 or ratio < .58:
            candidate = min(window["alternatives"], key=lambda v: abs(np.log(v / reference)))
            if abs(np.log(candidate / reference)) < .18:
                window["bpm"] = candidate
                folded += 1
    values = [w["bpm"] for w in windows]
    representative = weighted_median(values, weights)
    p05, p95 = np.percentile(values, [5, 95])
    strength = float(np.average(weights))
    return {"bpm": representative, "tempo_spread_bpm": float(p95 - p05),
            "tempo_variability_pct": float(100 * (p95 - p05) / representative),
            "tempo_reliability": strength, "tempo_ambiguous": folded > 0,
            "tempo_octave_adjustments": folded, "tempo_curve": windows,
            "tempo_status": "Pulse candidates; half/double-time alternatives remain possible"}


def tap_tempo(timestamps: list[float]) -> tuple[float, float]:
    if len(timestamps) < 4:
        raise ValueError("Tap at least four beats.")
    intervals = np.diff(timestamps)
    if not np.all(np.isfinite(intervals)) or np.any(intervals <= 0):
        raise ValueError("Tap times must be finite and increasing.")
    median = float(np.median(intervals))
    return 60 / median, float(100 * np.median(np.abs(intervals - median)) / median)
