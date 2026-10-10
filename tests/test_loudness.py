import re
import shutil
import subprocess

import numpy as np
import pyloudnorm as pyln
import pytest
import soundfile as sf

from music_analyzer.loudness import LoudnessMeter


def measure(samples, rate, chunk=17003):
    meter = LoudnessMeter(rate, 1 if samples.ndim == 1 else samples.shape[1])
    for start in range(0, len(samples), chunk):
        meter.feed(samples[start:start + chunk])
    return meter.finish()


@pytest.mark.parametrize("channels", [1, 2])
def test_lufs_matches_independent_meter_and_chunk_boundaries(channels):
    rate = 48000
    rng = np.random.default_rng(19)
    samples = rng.normal(0, .05, (rate * 8, channels))
    samples[:rate] *= .1
    expected = pyln.Meter(rate, filter_class="DeMan").integrated_loudness(samples)
    result = measure(samples, rate)
    assert abs(result["integrated_lufs"] - expected) < .05
    assert abs(measure(samples, rate, 240000)["integrated_lufs"] - result["integrated_lufs"]) < 1e-6
    assert result["loudness_std_lu"] > 0


def test_silence_and_short_tracks_are_explicit():
    result = measure(np.zeros(48000 * 4), 48000)
    assert result["integrated_lufs"] is None and result["silent"]
    result = measure(np.ones(4800) * .01, 48000)
    assert result["integrated_lufs"] is None and result["lra_lu"] is None
    assert result["loudness_short_track"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="Independent FFmpeg reference is unavailable")
def test_lufs_and_lra_against_ffmpeg(tmp_path):
    rate = 48000
    time = np.arange(rate * 45) / rate
    gain = np.repeat([.01, .05, .015, .12, .03], rate * 9)
    samples = np.sin(2 * np.pi * 997 * time) * gain
    source = tmp_path / "reference.wav"
    sf.write(source, samples, rate, subtype="FLOAT")
    result = subprocess.run(["ffmpeg", "-nostdin", "-i", str(source), "-af", "ebur128", "-f", "null", "-"],
                            capture_output=True, timeout=30)
    log = result.stderr.decode()
    integrated = float(re.findall(r"I:\s+([-\d.]+) LUFS", log)[-1])
    lra = float(re.findall(r"LRA:\s+([-\d.]+) LU", log)[-1])
    measured = measure(samples, rate)
    assert abs(measured["integrated_lufs"] - integrated) < .2
    assert abs(measured["lra_lu"] - lra) < .5
