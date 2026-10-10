import math

import pytest

from music_analyzer.domain import Track
from music_analyzer.scoring import make_snapshot, mapped, score_tracks


def track(identifier, lufs=-18, bpm=100, valence=20):
    return Track(id=str(identifier), path=f"/{identifier}.wav", original_name=f"{identifier}.wav", status="complete",
                 analysis={"integrated_lufs": lufs, "loudness_p90": lufs + 2, "sustained_fraction": .3,
                           "bpm": bpm, "onset_rate": 2, "density_raw": .2, "valence": valence,
                           "arousal": 50, "needs_review": False})


def test_ties_missing_and_fixed_negative_valence():
    tracks = [track(i) for i in range(10)]
    snapshot = make_snapshot(tracks)
    values = score_tracks(tracks, snapshot)
    assert {v["tempo"] for v in values.values()} == {50}
    assert {v["valence"] for v in values.values()} == {20}
    assert {v["valence_corpus_rank"] for v in values.values()} == {50}
    assert all(v["bucket"] == "negative" for v in values.values())
    assert mapped(None, 0, 1) is None and mapped(math.nan, 0, 1) is None
    tracks[0].overrides["bpm"] = None
    value = score_tracks(tracks, snapshot)["0"]
    assert value["tempo"] is None and value["simple_intensity"] == value["dynamics"]
    assert "tempo" in value["missing_components"]


def test_real_reference_anchors_and_frozen_snapshot():
    tracks = [track("quiet", -34, 65), track("dense", -7, 180)]
    snapshot = make_snapshot(tracks, reference_ids=("quiet", "dense"))
    values = score_tracks(tracks, snapshot)
    assert values["quiet"]["dynamics"] == pytest.approx(5)
    assert values["dense"]["dynamics"] == pytest.approx(95)
    tracks.append(track("new", -12, 140))
    assert score_tracks(tracks, snapshot)["quiet"]["dynamics"] == 5
    assert snapshot["members"] == ["quiet", "dense"]
    with pytest.raises(ValueError, match="distinct"):
        make_snapshot(tracks, reference_ids=("dense", "quiet"))


def test_simple_matches_sum_order_and_outliers_clip():
    tracks = [track(i, -35 + i * 3, 45 + i * 16) for i in range(10)]
    scores = score_tracks(tracks, make_snapshot(tracks, profile="simple"))
    for value in scores.values():
        assert value["intensity"] == pytest.approx((value["dynamics"] + value["tempo"]) / 2)
        assert 0 <= value["intensity"] <= 100
    assert [t.id for t in sorted(tracks, key=lambda t: scores[t.id]["intensity"])] == [str(i) for i in range(10)]
