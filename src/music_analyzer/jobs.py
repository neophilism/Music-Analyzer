"""Bounded spawned workers with durable incremental results and cooperative cancel."""

import multiprocessing as mp
import queue
import time
from collections import deque
from pathlib import Path

from music_analyzer.domain import AnalysisSettings, Track
from music_analyzer.engine import AnalysisCancelled, analyze_track, cache_key
from music_analyzer.project import Project


def _worker(jobs, results, cancel):
    while True:
        payload = jobs.get()
        if payload is None:
            break
        track, settings, directory = payload
        track_id = track["id"]
        try:
            if cancel.is_set():
                raise AnalysisCancelled()

            def progress(fraction, phase, tid=track_id):
                try:
                    results.put_nowait({"type": "progress", "id": tid,
                                        "fraction": fraction, "phase": phase})
                except queue.Full:
                    pass

            result = analyze_track(track, settings, directory, cancel, progress)
            results.put({"type": "complete", "id": track_id, "result": result})
        except AnalysisCancelled:
            results.put({"type": "cancelled", "id": track_id})
        except Exception as exc:
            results.put({"type": "error", "id": track_id, "error": f"{type(exc).__name__}: {exc}"})


class BatchRunner:
    """Call poll on the project's owning thread (GUI timer or CLI loop)."""

    def __init__(self, project: Project):
        self.project = project
        self.context = mp.get_context("spawn")
        self.processes = []
        self.pending = deque()
        self.active: dict[str, Track] = {}
        self.keys = {}
        self.total = self.completed = self.failed = 0
        self.started = self.cancelled_at = None

    @property
    def running(self):
        return bool(self.pending or self.active)

    @property
    def eta(self):
        if not self.completed or self.started is None:
            return None
        return max(0, self.total - self.completed - self.failed) * (time.monotonic() - self.started) / self.completed

    def start(self, tracks: list[Track], settings: AnalysisSettings, model_directory: str = "", model_identity: str = "none"):
        if self.running:
            raise RuntimeError("An analysis batch is already running.")
        self.shutdown()
        settings.validate()
        self.settings = settings
        self.model_directory = model_directory
        self.total = len(tracks)
        self.completed = self.failed = 0
        self.started = time.monotonic()
        self.cancelled_at = None
        self.events = []
        self.keys = {}
        for track in tracks:
            key = cache_key(track.sha256, settings, model_identity)
            self.keys[track.id] = key
            cached = self.project.cache_get(key) if track.sha256 else None
            try:
                stat = Path(track.path).stat()
                unchanged = (stat.st_size, stat.st_mtime_ns) == (track.size, track.mtime_ns)
            except OSError:
                unchanged = False
            if not unchanged:
                cached = None
            if cached is not None:
                track.analysis, track.status, track.error = cached, "complete", ""
                self.project.save_track(track)
                self.completed += 1
                self.events.append({"type": "cached", "id": track.id})
            else:
                track.status, track.error = "queued", ""
                self.project.save_track(track)
                self.pending.append(track)
        if self.pending:
            self.job_queue = self.context.Queue(maxsize=settings.workers)
            self.result_queue = self.context.Queue(maxsize=128)
            self.cancel_event = self.context.Event()
            for _ in range(settings.workers):
                process = self.context.Process(target=_worker, args=(self.job_queue, self.result_queue, self.cancel_event), daemon=True)
                process.start()
                self.processes.append(process)

    def cancel(self):
        if not self.running:
            return
        self.cancelled_at = time.monotonic()
        self.cancel_event.set()
        while self.pending:
            track = self.pending.popleft()
            track.status = "pending"
            self.project.save_track(track)

    def poll(self) -> list[dict]:
        events, self.events = self.events, []
        if not self.processes:
            return events
        while True:
            try:
                event = self.result_queue.get_nowait()
            except queue.Empty:
                break
            track = self.active.get(event["id"])
            if track is None:
                continue
            if event["type"] == "complete":
                track.analysis, track.status, track.error = event["result"], "complete", ""
                self.project.cache_put(self.keys[track.id], track.analysis)
                self.completed += 1
            elif event["type"] == "error":
                track.status, track.error = "error", event["error"]
                self.failed += 1
            elif event["type"] == "cancelled":
                track.status, track.error = "pending", ""
            if event["type"] != "progress":
                self.project.save_track(track)
                del self.active[track.id]
            events.append(event)
        dead = any(not p.is_alive() for p in self.processes)
        timed_out = self.cancelled_at is not None and time.monotonic() - self.cancelled_at > 5
        if dead or timed_out:
            for track in [*self.active.values(), *self.pending]:
                track.status = "pending" if self.cancelled_at else "error"
                track.error = "" if self.cancelled_at else "Analysis worker exited unexpectedly. Retry this track."
                self.project.save_track(track)
                events.append({"type": "cancelled" if self.cancelled_at else "error", "id": track.id, "error": track.error})
            self.active.clear()
            self.pending.clear()
        while self.pending and len(self.active) < self.settings.workers and self.cancelled_at is None:
            track = self.pending.popleft()
            track.status = "analyzing"
            self.project.save_track(track)
            self.active[track.id] = track
            self.job_queue.put((track.to_dict(), self.settings.to_dict(), self.model_directory))
        if not self.running:
            self.shutdown()
        return events

    def shutdown(self):
        for process in self.processes:
            if process.is_alive():
                try:
                    self.job_queue.put_nowait(None)
                except queue.Full:
                    pass
                process.join(timeout=.2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=.5)
            process.close()
        self.processes = []
        for name in ("job_queue", "result_queue"):
            value = getattr(self, name, None)
            if value is not None:
                value.cancel_join_thread()
                value.close()
