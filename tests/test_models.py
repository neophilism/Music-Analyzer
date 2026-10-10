import os
from pathlib import Path

import numpy as np
import pytest

from music_analyzer.models import (
    ClapBackend,
    model_manifest,
    model_present,
    summarize_genres,
    verify_model,
)


def test_manifest_and_missing_model_are_explicit(tmp_path):
    manifest = model_manifest()
    assert manifest["license"] == "Apache-2.0"
    assert len(manifest["revision"]) == 40
    assert all(len(asset["sha256"]) == 64 for asset in manifest["assets"])
    assert not model_present(tmp_path)
    with pytest.raises(ValueError, match="asset"):
        verify_model(tmp_path)
    assert summarize_genres([])["genres"] == []


@pytest.mark.model
@pytest.mark.skipif(not os.environ.get("MUSIC_ANALYZER_TEST_MODEL"), reason="Pinned model not installed for this test")
def test_actual_offline_inference(monkeypatch):
    import urllib.request

    def no_network(*args, **kwargs):
        raise AssertionError("Inference attempted a network request")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    backend = ClapBackend(Path(os.environ["MUSIC_ANALYZER_TEST_MODEL"]))
    time = np.arange(48000 * 10) / 48000
    samples = (.1 * np.sin(2 * np.pi * 261.63 * time)).astype(np.float32)
    scores = backend.infer(samples)
    assert scores and all(np.isfinite(v) and -1 <= v <= 1 for v in scores.values())
    result = summarize_genres([{"duration": 10, "scores": scores}])
    assert len(result["genre_candidates"]) == 5
    from music_analyzer.emotion import summarize_emotion

    emotion = summarize_emotion([{"time": 0, "duration": 10, "scores": scores}], 10)
    assert 0 <= emotion["valence"] <= 100 and 0 <= emotion["arousal"] <= 100
    assert emotion["mood_candidates"] and emotion["model_coverage"] == 1


@pytest.mark.model
@pytest.mark.skipif(not os.environ.get("MUSIC_ANALYZER_TEST_MODEL"), reason="Pinned model not installed for this test")
def test_actual_engine_predictions_ignore_names_tags_and_overrides(tmp_path, monkeypatch):
    import threading
    import urllib.request

    import soundfile as sf

    from music_analyzer.domain import AnalysisSettings
    from music_analyzer.engine import analyze_track
    from music_analyzer.project import inspect_track

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("Inference used network"))
    time = np.arange(16000 * 12) / 16000
    first = tmp_path / "happy-major-classical.wav"
    second = tmp_path / "angry-minor-metal.wav"
    sf.write(first, (.1 * np.sin(2 * np.pi * 261.63 * time)).astype(np.float32), 16000)
    second.write_bytes(first.read_bytes())
    outputs = []
    for index, path in enumerate((first, second)):
        track = inspect_track(path)
        track.overrides = {"valence": 100 if index == 0 else 0, "mode": "major" if index == 0 else "minor"}
        outputs.append(analyze_track(track.to_dict(), AnalysisSettings().to_dict(),
                                     os.environ["MUSIC_ANALYZER_TEST_MODEL"], threading.Event(), lambda *_: None))
    assert outputs[0] == outputs[1]
