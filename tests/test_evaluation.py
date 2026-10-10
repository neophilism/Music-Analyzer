import pytest

from music_analyzer.domain import Track
from music_analyzer.evaluation import evaluate, validate_manifest


def annotation(index, **values):
    return {"sha256": f"{index:064x}", "recording_id": f"recording-{index}", "split": "heldout",
            "instrumental": True, "license": "test fixture", "source": "synthetic test only", **values}


def test_evaluation_ignores_corrections_and_reports_coverage_and_genres():
    tracks = [Track("a", "/happy-name.wav", "happy-name.wav", sha256=f"{1:064x}", status="complete",
                    analysis={"valence": 20, "mood": "angry", "mode": "minor", "key": "C",
                              "needs_review": False, "genre_candidates": [{"label": "heavy metal"}],
                              "integrated_lufs": -10, "bpm": 120},
                    overrides={"valence": 95, "mood": "happy"}, reviewed=True)]
    labels = {"records": [annotation(1, valence="negative", mood_family="angry", genres=["metal"], mode="minor", key="C", bpm=60),
                           annotation(2, valence="positive", mood_family="joy", genres=["classical"])]}
    report = evaluate(tracks, labels)
    assert report["valence"]["accuracy"] == 1
    assert report["valence"]["coverage"] == .5
    assert report["mood_family"]["accepted_accuracy"] == 1
    assert report["per_genre"]["metal"]["genre_top3_recall"] == 1
    assert report["tempo_relative_error"] == 1
    assert report["tempo_octave_relative_error"] == 0
    assert tracks[0].overrides["valence"] == 95


def test_recording_identity_and_preference_pairs_cannot_leak_between_splits():
    records = [annotation(1), annotation(2, split="development", recording_id="recording-1")]
    with pytest.raises(ValueError, match="cannot cross"):
        validate_manifest({"records": records})
    records[1]["recording_id"] = "different"
    with pytest.raises(ValueError, match="cannot cross"):
        validate_manifest({"records": records, "intensity_pairs": [{"lower": records[0]["sha256"], "higher": records[1]["sha256"], "split": "heldout"}]})


def test_no_annotations_produce_no_accuracy_claims():
    report = evaluate([], {"records": []})
    assert report["valence"]["accuracy"] is None
    assert report["mood_family"]["accuracy"] is None
    assert report["intensity"]["agreement"] is None
    assert report["status"] == "No held-out listening evidence supplied"


def test_annotations_require_rights_and_instrumental_status():
    with pytest.raises(ValueError, match="rights"):
        validate_manifest({"records": [annotation(1, license="")]})
    with pytest.raises(ValueError, match="instrumental"):
        validate_manifest({"records": [annotation(1, instrumental=False)]})
