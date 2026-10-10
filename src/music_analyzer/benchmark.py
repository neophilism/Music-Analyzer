"""Reproducible corpus/worker/export benchmark; synthetic results are not music accuracy."""

import argparse
import json
import multiprocessing
import platform
import resource
import time
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf

from music_analyzer.domain import AnalysisSettings
from music_analyzer.exporting import create_journal, execute_export, make_export_plan
from music_analyzer.jobs import BatchRunner
from music_analyzer.models import model_identity
from music_analyzer.project import Project, expand_paths, inspect_track
from music_analyzer.scoring import make_snapshot, score_tracks
from music_analyzer.sequencing import build_album


def generate_fixtures(root, count=200, seconds=12.5):
    root.mkdir(parents=True, exist_ok=True)
    rate = 16000
    times = np.arange(round(rate * seconds)) / rate
    formats = [("wav", "WAV", "PCM_16"), ("flac", "FLAC", "PCM_16"),
               ("aif", "AIFF", "PCM_16"), ("ogg", "OGG", "VORBIS")]
    for index in range(count):
        frequency, bpm = 180 + index * 2.3, 60 + index % 121
        level = .01 + .25 * (index / max(count - 1, 1))
        envelope = .6 + .4 * np.sin(2 * np.pi * times / seconds) ** 2
        samples = level * envelope * (np.sin(2 * np.pi * frequency * times)
                                     + .3 * np.sin(2 * np.pi * frequency * 1.5 * times))
        for beat in np.arange(0, seconds, 60 / bpm):
            start, length = round(beat * rate), min(320, len(samples) - round(beat * rate))
            samples[start:start + length] += .1 * np.hanning(length)
        if index % 3 == 0:
            samples = np.column_stack([samples, samples * .9])
        suffix, format_name, subtype = formats[index % len(formats)]
        sf.write(root / f"fixture-{index:03d}.{suffix}", samples, rate, format=format_name, subtype=subtype)


def drain(runner, *, cancel_after=None, timeout=3600):
    events, polls, peak_workers = [], [], 0
    deadline = time.monotonic() + timeout
    while runner.running:
        if time.monotonic() > deadline:
            runner.cancel()
            runner.shutdown()
            raise TimeoutError("Benchmark exceeded its time limit; completed results remain saved.")
        started = time.perf_counter()
        events.extend(runner.poll())
        polls.append(time.perf_counter() - started)
        peak_workers = max(peak_workers, len(runner.active))
        if cancel_after is not None and runner.completed >= cancel_after:
            runner.cancel()
            cancel_after = None
        time.sleep(.01)
    events.extend(runner.poll())
    return events, max(polls, default=0), peak_workers


def run_benchmark(root, *, count=200, seconds=12.5, source_folder=None, workers=1):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    synthetic = source_folder is None
    sources = Path(source_folder).resolve() if source_folder else root / "fixtures"
    if synthetic:
        generate_fixtures(sources, count, seconds)
    paths = expand_paths([sources])
    started = time.perf_counter()
    project_path = root / "benchmark.ma-project"
    with Project(project_path) as project:
        for path in paths:
            project.add_track(inspect_track(path))
        import_seconds = time.perf_counter() - started
        settings = AnalysisSettings(model_enabled=False, workers=workers)
        runner = BatchRunner(project)
        started = time.perf_counter()
        runner.start(project.tracks(), settings)
        _, poll_max, peak_workers = drain(runner, cancel_after=min(5, len(paths)))
        saved = sum(track.status == "complete" for track in project.tracks())
    # Reopen simulates an application restart after a cancelled batch.
    with Project(project_path) as project:
        runner = BatchRunner(project)
        runner.start([t for t in project.tracks() if t.status != "complete"], settings)
        events, poll_resume, peak_resume = drain(runner)
        analysis_seconds = time.perf_counter() - started
        tracks = project.tracks()
        statuses = dict(Counter(t.status for t in tracks))
        started = time.perf_counter()
        runner.start([t for t in tracks if t.status == "complete"], settings)
        cached, _, _ = drain(runner)
        cache_seconds = time.perf_counter() - started
        score_seconds, export_seconds, exported, journal_bytes = None, None, 0, None
        if synthetic:
            # These are explicit test-only listener edits for exercising sequencing;
            # raw model outputs remain unavailable. They never enter audio analysis.
            for index, track in enumerate(tracks):
                if track.status == "complete":
                    track.reviewed = True
                    track.overrides = {"valence": 80 if index % 2 == 0 else 20,
                                       "arousal": index / max(len(tracks) - 1, 1) * 100,
                                       "bpm": track.value("bpm") or 60 + index % 121}
                    project.save_track(track)
            started = time.perf_counter()
            snapshot = make_snapshot(tracks)
            scores = score_tracks(tracks, snapshot)
            album = build_album(tracks, scores).to_dict()
            score_seconds = time.perf_counter() - started
            destination = root / "export"
            destination.mkdir(exist_ok=True)
            started = time.perf_counter()
            path = create_journal(make_export_plan(tracks, scores, album, snapshot, destination, "benchmark"))
            result = execute_export(path)
            export_seconds = time.perf_counter() - started
            exported = sum(entry["kind"] == "audio" for entry in result["files"])
            journal_bytes = path.stat().st_size
    divisor = 1024 ** 2 if platform.system() == "Darwin" else 1024
    report = {"platform": platform.platform(), "python": platform.python_version(),
              "purpose": "Synthetic mechanics/performance; no emotion or genre accuracy claim" if synthetic else "User-supplied corpus acoustic performance",
              "tracks": len(paths), "formats": dict(Counter(path.suffix for path in paths)),
              "fixture_seconds": seconds if synthetic else None, "models_enabled": False,
              "workers": workers, "peak_active_workers": max(peak_workers, peak_resume),
              "import_seconds": import_seconds, "analysis_with_cancel_and_restart_seconds": analysis_seconds,
              "completed_before_restart": saved, "final_statuses": statuses,
              "resume_event_counts": dict(Counter(e["type"] for e in events)),
              "cache_event_counts": dict(Counter(e["type"] for e in cached)),
              "cached_batch_seconds": cache_seconds, "cached_scoring_and_order_seconds": score_seconds,
              "max_poll_seconds": max(poll_max, poll_resume), "export_seconds": export_seconds,
              "exported_tracks": exported, "journal_bytes": journal_bytes,
              "peak_parent_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor,
              "peak_child_rss_mib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / divisor,
              "memory_note": "Maximum individual child RSS, not simultaneous aggregate worker memory",
              "model_identity": model_identity(), "heldout_quality": "unverified"}
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New benchmark directory")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seconds", type=float, default=12.5)
    parser.add_argument("--source-folder", type=Path)
    parser.add_argument("--workers", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a new empty benchmark directory to avoid reusing old results.")
    if args.count < 1 or args.seconds < 2:
        parser.error("Use at least one track and at least two seconds per fixture.")
    print(json.dumps(run_benchmark(args.output, count=args.count, seconds=args.seconds,
                                   source_folder=args.source_folder, workers=args.workers), indent=2), flush=True)


if __name__ == "__main__":
    main()
