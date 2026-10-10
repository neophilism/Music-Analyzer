"""Transactional SQLite project persistence; one connection on the owning thread."""

import json
import sqlite3
import time
import uuid
from pathlib import Path

from music_analyzer.audio import SUPPORTED_EXTENSIONS, file_hash, probe_audio
from music_analyzer.domain import Track

SCHEMA_VERSION = 1


def inspect_track(path: str | Path, ffmpeg_path: str = "") -> Track:
    source = Path(path).expanduser().resolve()
    track = Track(id=uuid.uuid4().hex, path=str(source), original_name=source.name)
    try:
        before = source.stat()
        track.size, track.mtime_ns = before.st_size, before.st_mtime_ns
        track.sha256 = file_hash(source)
        info = probe_audio(source, ffmpeg_path)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source changed during import. Import it again once writing finishes.")
        for name, value in info.items():
            setattr(track, name, value)
    except (OSError, ValueError, RuntimeError) as exc:
        track.status, track.error = "error", str(exc)
    return track


def expand_paths(paths: list[str | Path]) -> list[Path]:
    result = []
    seen = set()
    for value in paths:
        path = Path(value).expanduser()
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                resolved = candidate.resolve()
                if resolved not in seen:
                    result.append(resolved)
                    seen.add(resolved)
    return result


class Project:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self.connection.close()
            raise ValueError("This project was made by a newer application version.")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, result TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            PRAGMA user_version=1;
        """)
        self.connection.commit()
        # A killed job is resumable. Completed tracks and edits are never discarded.
        for track in self.tracks():
            if track.status in {"queued", "analyzing"}:
                track.status = "pending"
                self.save_track(track)

    def close(self):
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def tracks(self) -> list[Track]:
        return [Track(**json.loads(row[0])) for row in self.connection.execute("SELECT data FROM tracks ORDER BY rowid")]

    def track(self, track_id: str) -> Track | None:
        row = self.connection.execute("SELECT data FROM tracks WHERE id=?", (track_id,)).fetchone()
        return Track(**json.loads(row[0])) if row else None

    def save_track(self, track: Track):
        with self.connection:
            self.connection.execute(
                "INSERT INTO tracks VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (track.id, json.dumps(track.to_dict(), allow_nan=False)),
            )

    def add_track(self, track: Track, keep_duplicates: bool = True) -> bool:
        tracks = self.tracks()
        if any(existing.path == track.path for existing in tracks):
            return False
        duplicate = next((t for t in tracks if track.sha256 and t.sha256 == track.sha256), None)
        if duplicate:
            if not keep_duplicates:
                return False
            track.duplicate_of = duplicate.id
        self.save_track(track)
        return True

    def remove_track(self, track_id: str):
        with self.connection:
            self.connection.execute("DELETE FROM tracks WHERE id=?", (track_id,))

    def set_metadata(self, key: str, value):
        with self.connection:
            self.connection.execute("INSERT INTO metadata VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                    (key, json.dumps(value, allow_nan=False)))

    def metadata(self, key: str, default=None):
        row = self.connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def cache_get(self, key: str):
        row = self.connection.execute("SELECT result FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key: str, result: dict):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                                    (key, json.dumps(result, allow_nan=False), time.time()))

    def relocate(self, track: Track, new_path: str | Path):
        candidate = Path(new_path).resolve()
        if file_hash(candidate) != track.sha256:
            raise ValueError("Replacement recording does not match the imported content hash.")
        track.path = str(candidate)
        stat = candidate.stat()
        track.size, track.mtime_ns = stat.st_size, stat.st_mtime_ns
        self.save_track(track)
