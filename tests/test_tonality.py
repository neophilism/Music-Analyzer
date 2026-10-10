import numpy as np
import pytest

from music_analyzer.tonality import (
    MAJOR_PROFILE,
    MINOR_PROFILE,
    analyze_tonal_segment,
    profile_candidates,
    summarize_tonality,
)


@pytest.mark.parametrize("profile,tonic,label", [(MAJOR_PROFILE, 0, "C major"), (MINOR_PROFILE, 9, "A minor")])
def test_profile_orientation(profile, tonic, label):
    assert profile_candidates(np.roll(profile, tonic))[0]["key"] == label


@pytest.mark.parametrize("semitones,mode", [([0, 4, 7], "major"), ([0, 3, 7], "minor")])
def test_audio_major_minor_with_detuning(semitones, mode):
    rate = 22050
    time = np.arange(rate * 8) / rate
    frequencies = 261.625565 * 2 ** ((np.array(semitones) + .18) / 12)
    samples = sum(weight * np.sin(2 * np.pi * frequency * time)
                  for weight, frequency in zip([.18, .1, .09], frequencies, strict=True)).astype(np.float32)
    segment = analyze_tonal_segment(samples, 0)
    assert segment is not None
    result = summarize_tonality([segment])
    assert result["mode"] == mode
    assert result["key"].startswith("C ")
    assert abs(result["tuning_cents"] - 18) < 12


def test_silence_and_flat_chroma_abstain():
    assert analyze_tonal_segment(np.zeros(22050 * 4), 0) is None
    assert profile_candidates(np.ones(12)) == []
    assert summarize_tonality([])["mode"] == "unknown"


def test_mode_changes_are_reported_as_mixed():
    segments = []
    for index, profile in enumerate([MAJOR_PROFILE, MINOR_PROFILE, MAJOR_PROFILE, MINOR_PROFILE]):
        candidates = profile_candidates(profile)
        segments.append({"time": index * 30., "chroma": profile.tolist(), "candidates": candidates[:4],
                         "tonal": True, "tuning_cents": 0.})
    assert summarize_tonality(segments)["mode"] == "mixed"
