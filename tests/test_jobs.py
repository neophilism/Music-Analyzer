import time

import numpy as np
import soundfile as sf

from music_analyzer.domain import AnalysisSettings
from music_analyzer.jobs import BatchRunner
from music_analyzer.project import Project, inspect_track


def run_to_completion(runner, timeout=30):
    deadline = time.monotonic() + timeout
    events = []
    while runner.running and time.monotonic() < deadline:
        events.extend(runner.poll())
        time.sleep(.02)
    events.extend(runner.poll())
    assert not runner.running
    return events


def test_spawn_cache_failure_and_preserved_edits(tmp_path):
    source = tmp_path / "audio.wav"
    sf.write(source, np.sin(np.arange(8000) * .1) * .1, 8000)
    with Project(tmp_path / "project.ma-project") as project:
        good = inspect_track(source)
        good.overrides = {"valence": 80}
        project.add_track(good)
        bad = inspect_track(tmp_path / "missing.wav")
        project.add_track(bad)
        runner = BatchRunner(project)
        settings = AnalysisSettings(model_enabled=False)
        runner.start(project.tracks(), settings)
        events = run_to_completion(runner)
        assert {e["type"] for e in events} >= {"complete", "error"}
        assert project.tracks()[0].overrides == {"valence": 80}
        runner.start([project.tracks()[0]], settings)
        assert not runner.running
        assert runner.poll()[0]["type"] == "cached"
        assert runner.completed == 1


def test_cancel_queued_and_restart(tmp_path):
    source = tmp_path / "audio.wav"
    sf.write(source, np.zeros(8000), 8000)
    with Project(tmp_path / "project.ma-project") as project:
        project.add_track(inspect_track(source))
        runner = BatchRunner(project)
        runner.start(project.tracks(), AnalysisSettings(model_enabled=False))
        runner.cancel()
        runner.poll()
        assert not runner.running
        assert project.tracks()[0].status == "pending"
        runner.start(project.tracks(), AnalysisSettings(model_enabled=False))
        run_to_completion(runner)
        assert project.tracks()[0].status == "complete"
