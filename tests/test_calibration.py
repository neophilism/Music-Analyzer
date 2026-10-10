import pytest

from music_analyzer.calibration import calibrated_valence, fit_intensity_pairs, fit_valence_anchors
from music_analyzer.domain import Track


def test_personal_valence_mapping_preserves_raw_and_explicit_overrides():
    tracks = [Track(id=str(i), path="/x", original_name="x", reviewed=True,
                    analysis={"valence": raw}, overrides={"valence": target})
              for i, (raw, target) in enumerate([(35., 10.), (50., 40.), (70., 90.)])]
    calibration = fit_valence_anchors(tracks)
    assert calibrated_valence(35, calibration) == 10
    assert calibrated_valence(70, calibration) == 90
    assert calibrated_valence(None, calibration) is None
    assert tracks[0].analysis["valence"] == 35
    assert all(a <= b for a, b in zip(calibration["y"], calibration["y"][1:], strict=False))
    with pytest.raises(ValueError):
        fit_valence_anchors(tracks[:2])


def test_personal_pair_fit_is_positive_and_explicitly_training_agreement():
    scores = {"high": {"dynamics": 90., "rhythmic_drive": 20., "arousal": 20., "density": 20.},
              "low": {"dynamics": 10., "rhythmic_drive": 60., "arousal": 60., "density": 60.}}
    fit = fit_intensity_pairs(scores, [{"higher": "high", "lower": "low"}] * 3)
    assert fit["weights"]["dynamics"] > .6
    assert sum(fit["weights"].values()) == pytest.approx(1)
    assert all(value >= 0 for value in fit["weights"].values())
    assert "not an independent" in fit["note"]
