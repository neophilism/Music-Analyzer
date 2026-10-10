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
