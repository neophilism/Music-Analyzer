"""Exercise the actual frozen GUI, spawned worker, and exports on the target OS."""

import os
import platform
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

from music_analyzer.domain import AnalysisSettings
from music_analyzer.exporting import create_journal, execute_export, make_export_plan
from music_analyzer.models import model_identity
from music_analyzer.project import inspect_track
from music_analyzer.window import MainWindow


def verify_package(app, model_directory=None):
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"
    original_urlopen = urllib.request.urlopen
    def no_download(*_args, **_kwargs):
        raise RuntimeError("Package verification attempted a network request")
    urllib.request.urlopen = no_download
    started = time.monotonic()
    window = None
    try:
        with tempfile.TemporaryDirectory(prefix="music-analyzer-package-") as temporary:
            root = Path(temporary)
            window = MainWindow(root / "Verification.ma-project")
            window._show_error = lambda message: (_ for _ in ()).throw(RuntimeError(message))
            window.show()
            rate = 16000
            times = np.arange(rate * 12) / rate
            for index in range(2):
                samples = (.03 if index == 0 else .2) * np.sin(2 * np.pi * (261.63 + index * 65.4) * times)
                source = root / f"instrumental-{index}.wav"
                sf.write(source, samples, rate)
                window.project.add_track(inspect_track(source))
            settings = AnalysisSettings(model_enabled=bool(model_directory))
            window.runner.start(window.project.tracks(), settings, str(model_directory or ""),
                                model_identity() if model_directory else "none")
            while window.runner.running:
                app.processEvents()
                window.runner.poll()
                if time.monotonic() - started > 300:
                    window.runner.cancel()
                    window.runner.shutdown()
                    raise TimeoutError("Packaged analysis exceeded five minutes.")
                time.sleep(.01)
            tracks = window.project.tracks()
            if any(t.status != "complete" or t.analysis.get("integrated_lufs") is None for t in tracks):
                raise RuntimeError("Packaged worker failed: " + "; ".join(t.error for t in tracks))
            if model_directory and any(not t.analysis.get("genre_candidates") or t.analysis.get("valence") is None for t in tracks):
                raise RuntimeError("Packaged offline model inference did not produce genre and emotion outputs.")
            for index, track in enumerate(tracks):
                # Explicit test-only listener assignments let the smoke verify
                # sequence/export mechanics without asserting synthetic emotions.
                track.overrides, track.reviewed = {"valence": 80 if index == 0 else 20, "arousal": 20 + 60 * index}, True
                window.project.save_track(track)
            window.refresh()
            window.recalculate()
            window.rebuild_order()
            window.close()
            window = MainWindow(root / "Verification.ma-project")
            window.show()
            app.processEvents()
            if (len(window.tracks) != 2 or not all(t.reviewed for t in window.tracks)
                    or not window.snapshot or not window.album or len(window.album["order"]) != 2):
                raise RuntimeError("Reopening the packaged project lost analysis or review state.")
            destination = root / "export"
            destination.mkdir()
            path = create_journal(make_export_plan(window.tracks, window.scores, window.album,
                                                  window.snapshot, destination, "package-verification"))
            exported = execute_export(path)
            if exported["phase"] != "complete" or len((destination / "album.m3u8").read_text().splitlines()) != 3:
                raise RuntimeError("Packaged export did not reconcile.")
            report = {"platform": platform.platform(), "architecture": platform.machine(),
                      "python": platform.python_version(), "frozen": bool(getattr(__import__("sys"), "frozen", False)),
                      "tracks_completed": len(tracks), "tracks_exported": 2,
                      "offline_model": bool(model_directory), "model_identity": model_identity() if model_directory else None,
                      "seconds": time.monotonic() - started,
                      "checks": ["native GUI", "spawned worker", "loudness", "reopened project", "album order", "verified audio export", "relative playlist"]}
            window.close()
            return report
    finally:
        if window is not None:
            window.runner.shutdown()
            window.close()
        urllib.request.urlopen = original_urlopen
