import numpy as np
import pytest

from music_analyzer.rhythm import summarize_tempo, tap_tempo, tempo_windows


def clicks(bpm, duration=24, rate=22050):
    samples = np.zeros(round(duration * rate), dtype=np.float32)
    for time in np.arange(.2, duration, 60 / bpm):
        offset = round(time * rate)
        pulse = np.exp(-np.arange(200) / 25) * np.random.default_rng(offset).normal(size=200)
        count = min(200, len(samples) - offset)
        samples[offset:offset + count] = pulse[:count]
    return samples


@pytest.mark.parametrize("bpm", [60, 80, 100, 120, 160, 200])
def test_stable_click_tempo(bpm):
    windows, _ = tempo_windows(clicks(bpm), 0)
    result = summarize_tempo(windows)
    assert result["bpm"] is not None
    assert abs(result["bpm"] - bpm) < 1
    assert result["tempo_variability_pct"] < 2


def test_octave_ambiguity_does_not_become_variability():
    windows = [{"time": i * 6., "raw_bpm": bpm, "bpm": bpm, "pulse_strength": .8,
                "alternatives": [bpm / 2, bpm, bpm * 2]} for i, bpm in enumerate([80., 160., 80., 80.])]
    result = summarize_tempo(windows)
    assert result["bpm"] == 80 and result["tempo_spread_bpm"] == 0
    assert result["tempo_ambiguous"]
    assert result["tempo_curve"][1]["raw_bpm"] == 160


def test_silence_and_tap_correction():
    windows, _ = tempo_windows(np.zeros(22050 * 12), 0)
    assert summarize_tempo(windows)["bpm"] is None
    assert tap_tempo([0., .5, 1., 1.5]) == (120, 0)
    with pytest.raises(ValueError):
        tap_tempo([0, .5])


def test_tempo_ramp_is_retained_and_local_estimates_are_accurate():
    rate, duration, first, last = 22050, 60, 90, 130
    slope = (last - first) / duration
    samples = np.zeros(rate * duration, dtype=np.float32)
    for beat in range(1, 110):
        time = (-first + np.sqrt(first ** 2 + 120 * slope * beat)) / slope
        offset = round(time * rate)
        if offset + 200 >= len(samples):
            break
        samples[offset:offset + 200] = np.exp(-np.arange(200) / 25) * np.random.default_rng(beat).normal(size=200)
    windows, _ = tempo_windows(samples, 0)
    assert len(windows) >= 5
    for window in windows:
        expected = first + slope * window["time"]
        assert abs(window["bpm"] - expected) / expected < .05
    assert summarize_tempo(windows)["tempo_variability_pct"] > 15
