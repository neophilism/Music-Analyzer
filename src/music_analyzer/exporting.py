"""Byte-preserving exports with exclusive publication, durable recovery, and undo."""

import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import shutil
import sys
import time
import unicodedata
import uuid
from pathlib import Path

from music_analyzer.audio import file_hash
from music_analyzer.sequencing import validate_manual_order

PRODUCER = "music-analyzer-export-1"
FOLDERS = {"positive": "Positive Valence", "negative": "Negative Valence"}
REPORTS = {"album.m3u8", "analysis.csv", "analysis.json", "album-manifest.json"}


class ExportPaused(Exception):
    """A cooperative cancellation; the saved journal can be resumed or undone."""


def _canonical(value):
    return unicodedata.normalize("NFC", str(value)).casefold()


def _exists(path):
    return os.path.lexists(path)


def _identity(path):
    stat = Path(path).stat()
    return [stat.st_dev, stat.st_ino]


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _save(journal, path):
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(journal, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _sync_directory(path.parent)


def _rename_exclusive(source, target):
    """Same-volume atomic rename that refuses an existing destination, even in a race."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        operation = library.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = operation(os.fsencode(source), os.fsencode(target), 4)  # RENAME_EXCL
    elif hasattr(library, "renameat2"):
        operation = library.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = operation(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    else:
        # Both supported targets provide exclusive rename. Hard-link fallback also
        # refuses an existing file and retains the source if publication fails.
        os.link(source, target)
        os.unlink(source)
        result = 0
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))
    _sync_directory(Path(target).parent)
    _sync_directory(Path(source).parent)


def _relative_path(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) > 2:
        raise ValueError("Journal contains an invalid output path.")
    if len(path.parts) == 1 and path.name in REPORTS:
        return path
    if len(path.parts) == 2 and path.parts[0] in FOLDERS.values():
        return path
    raise ValueError("Journal contains an unexpected output path.")


def load_journal(path):
    path = Path(path).expanduser().resolve()
    journal = json.loads(path.read_text(encoding="utf-8"))
    if journal.get("producer") != PRODUCER or len(journal.get("id", "")) != 32:
        raise ValueError("This is not a supported Music Analyzer export journal.")
    if any(c not in "0123456789abcdef" for c in journal["id"]):
        raise ValueError("Invalid export identity.")
    root = Path(journal["root"])
    if root.resolve() != path.parent or path.name != f".music-analyzer-{journal['id']}.journal.json":
        raise ValueError("Keep the export journal in its original output folder.")
    for entry in journal["files"] + journal["backups"]:
        _relative_path(entry["relative"])
        stage_name = Path(entry["stage"])
        if len(stage_name.parts) != 1 or stage_name.name in {".", ".."}:
            raise ValueError("Invalid staging path in journal.")
    return journal


def _reports(tracks, scores, album, snapshot, mappings, export_id):
    positions = {tid: index for index, tid in enumerate(album["order"], 1)}
    output = io.StringIO(newline="")
    fields = ["track_id", "filename", "status", "excluded", "reviewed", "album_position",
              "bucket", "intensity", "dynamics", "tempo", "bpm", "valence", "mood", "mode",
              "integrated_lufs", "lra_lu", "loudness_spread_lu", "loudness_std_lu",
              "rms_dbfs", "crest_db", "tempo_spread_bpm", "tempo_variability_pct", "genres", "error"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for track in tracks:
        score = scores.get(track.id, {})
        row = {key: score.get(key, "") for key in fields}
        row.update(track_id=track.id, filename=track.original_name, status=track.status,
                   excluded=track.excluded, reviewed=track.reviewed,
                   album_position=positions.get(track.id, ""), bpm=track.value("bpm", ""),
                   mode=track.value("mode", ""), mood=track.value("mood", ""),
                   genres="; ".join(track.value("genres", [])), error=track.error)
        for key in ("integrated_lufs", "lra_lu", "loudness_spread_lu", "loudness_std_lu",
                    "rms_dbfs", "crest_db", "tempo_spread_bpm", "tempo_variability_pct"):
            row[key] = track.value(key, "")
        # CSV may be opened in a spreadsheet; preserve text without executing a formula.
        for key in ("filename", "genres", "error"):
            if str(row[key]).startswith(("=", "+", "-", "@")):
                row[key] = "'" + str(row[key])
        writer.writerow(row)
    return {
        "album.m3u8": "#EXTM3U\n" + "\n".join(item["relative"] for item in mappings) + "\n",
        "analysis.csv": output.getvalue(),
        "analysis.json": json.dumps({"snapshot": snapshot, "album": album, "scores": scores,
                                    "tracks": [track.to_dict() for track in tracks]},
                                   ensure_ascii=False, indent=2, allow_nan=False),
        "album-manifest.json": json.dumps({"producer": PRODUCER, "export_id": export_id,
                                          "mappings": mappings, "warnings": album.get("warnings", []),
                                          "excluded": [t.id for t in tracks if t.excluded],
                                          "snapshot_id": snapshot.get("id") if snapshot else None},
                                         ensure_ascii=False, indent=2, allow_nan=False),
    }


def make_export_plan(tracks, scores, album, snapshot, root, project_id, *, move=False,
                     padded=True, previous_journal=None):
    """Build the complete preview without touching audio. Hash preflight runs in the worker."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing output folder.")
    order = album.get("order", []) if album else []
    warnings = validate_manual_order(order, tracks, scores)
    if not order:
        raise ValueError("Build an album containing at least one included track first.")
    by_id = {track.id: track for track in tracks}
    if any(by_id[tid].status != "complete" or scores[tid].get("needs_review")
           or scores[tid].get("bucket") not in FOLDERS for tid in order):
        raise ValueError("Analyze, review, or exclude unresolved recordings before exporting.")
    export_id = uuid.uuid4().hex
    journal = {"producer": PRODUCER, "id": export_id, "root": str(root),
               "project_id": project_id, "move": move, "phase": "planned",
               "created": time.time(), "files": [], "backups": [], "warnings": warnings,
               "previous_journal": str(previous_journal) if previous_journal else None}
    previous = {}
    if previous_journal:
        old = load_journal(previous_journal)
        if old["root"] != str(root) or old["project_id"] != project_id or old["phase"] != "complete":
            raise ValueError("The previous export must be completed and belong to this project and folder.")
        previous = {entry["relative"]: entry for entry in old["files"]}
    width = len(str(len(order))) if padded else 1
    counts = {"positive": 0, "negative": 0}
    mappings = []
    for position, tid in enumerate(order, 1):
        track, score = by_id[tid], scores[tid]
        source = Path(track.path).resolve()
        name = track.original_name
        if not name or any(c in name for c in "/\\\n\r\0") or name in {".", ".."}:
            raise ValueError(f"Filename cannot be represented safely in the playlist: {name!r}")
        relative = f"{FOLDERS[score['bucket']]}/{position:0{width}d}_{name}"
        if len(Path(relative).name.encode("utf-8")) > 255 or len(os.fsencode(root / relative)) > 1023:
            raise ValueError(f"Export path is too long: {relative}")
        if not track.sha256:
            raise ValueError(f"Import the content hash before exporting: {name}")
        counts[score["bucket"]] += 1
        mappings.append({"track_id": tid, "source": str(source), "original_name": name,
                         "relative": relative, "album_position": position,
                         "bucket": score["bucket"], "bucket_rank": counts[score["bucket"]],
                         "sha256": track.sha256})
        journal["files"].append({"kind": "audio", "track_id": tid, "source": str(source),
                                 "relative": relative, "sha256": track.sha256, "size": track.size,
                                 "stage": f"file-{len(journal['files'])}", "state": "pending",
                                 "source_removed": False})
    for name, payload in _reports(tracks, scores, album, snapshot, mappings, export_id).items():
        content = payload.encode("utf-8")
        journal["files"].append({"kind": "report", "relative": name, "payload": payload,
                                 "sha256": hashlib.sha256(content).hexdigest(), "size": len(content),
                                 "stage": f"file-{len(journal['files'])}", "state": "pending"})
    names = [_canonical(entry["relative"]) for entry in journal["files"]]
    if len(names) != len(set(names)):
        raise ValueError("Output names collide after Unicode and case normalization.")
    for entry in journal["files"]:
        target = root / entry["relative"]
        own_source = entry.get("source") == str(target)
        retained = entry["relative"] in previous and previous[entry["relative"]]["sha256"] == entry["sha256"]
        entry["keep_existing"] = bool(own_source or retained)
        if _exists(target) and not own_source and entry["relative"] not in previous:
            raise FileExistsError(f"An unrelated file already exists: {target}")
    retained = {entry["relative"] for entry in journal["files"] if entry["keep_existing"]}
    for relative, entry in previous.items():
        if relative not in retained:
            journal["backups"].append({"relative": relative, "sha256": entry["sha256"],
                                       "stage": f"backup-{len(journal['backups'])}", "state": "pending"})
    return journal


def journal_path(plan):
    return Path(plan["root"]) / f".music-analyzer-{plan['id']}.journal.json"


def create_journal(plan):
    path = journal_path(plan)
    if _exists(path):
        raise FileExistsError(path)
    _save(plan, path)
    return path


def _stage_directory(journal):
    root = Path(journal["root"])
    stage = root / f".music-analyzer-{journal['id']}-staging"
    if stage.is_symlink():
        raise ValueError("Staging folder was replaced by a symbolic link.")
    stage.mkdir(exist_ok=True)
    return stage


def _check_hash(path, expected):
    if Path(path).is_symlink() or not Path(path).is_file() or file_hash(path) != expected:
        raise ValueError(f"File is missing or changed; recoverable files are retained: {path}")


def _copy_verified(source, target, expected, cancel):
    _check_hash(source, expected)
    with Path(source).open("rb") as reader, Path(target).open("wb") as writer:
        while block := reader.read(1024 * 1024):
            if cancel and cancel.is_set():
                raise ExportPaused()
            writer.write(block)
        writer.flush()
        os.fsync(writer.fileno())
    _check_hash(target, expected)
    _check_hash(source, expected)
    shutil.copystat(source, target)


def _preflight(journal):
    root = Path(journal["root"])
    allowed = {entry["relative"] for entry in journal["backups"]}
    allowed.update(entry["relative"] for entry in journal["files"] if entry["keep_existing"] or entry.get("identity"))
    for folder in FOLDERS.values():
        for candidate in root.iterdir():
            if _canonical(candidate.name) == _canonical(folder) and candidate.name != folder:
                raise FileExistsError(f"Folder differs only in case or Unicode: {candidate}")
        directory = root / folder
        if _exists(directory) and (directory.is_symlink() or not directory.is_dir()):
            raise FileExistsError(f"Expected an ordinary output folder: {directory}")
        directory.mkdir(exist_ok=True)
    for entry in journal["files"]:
        target = root / entry["relative"]
        for candidate in target.parent.iterdir():
            if _canonical(candidate.name) == _canonical(target.name):
                relative = candidate.relative_to(root).as_posix()
                if relative != entry["relative"] or relative not in allowed:
                    raise FileExistsError(f"Output collides with an unrelated file: {candidate}")
        if entry["kind"] == "audio" and not entry["source_removed"]:
            source = Path(entry["source"])
            backup = next((b for b in journal["backups"] if root / b["relative"] == source), None)
            recovery = root / f".music-analyzer-{journal['id']}-staging" / backup["stage"] if backup else None
            quarantine = source.parent / f".music-analyzer-{journal['id']}-{entry['stage']}.moved"
            if recovery and recovery.exists():
                _check_hash(recovery, entry["sha256"])
            elif entry.get("removing_source") and quarantine.exists():
                _check_hash(quarantine, entry["sha256"])
            elif entry.get("removing_source") and not source.exists():
                _check_hash(target, entry["sha256"])
                entry["source_removed"] = True
            else:
                _check_hash(source, entry["sha256"])
        if entry["keep_existing"]:
            _check_hash(target, entry["sha256"])
    required = sum(e["size"] for e in journal["files"] if not e["keep_existing"] and e["state"] == "pending")
    if shutil.disk_usage(root).free < required + 1024 * 1024:
        raise OSError(errno.ENOSPC, "Insufficient space to stage and verify this export.")


def execute_export(path, cancel=None, progress=None, *, fault=None):
    """Resume a saved export. A move is verified copy, exclusive publish, then source removal."""
    path = Path(path).resolve()
    journal = load_journal(path)
    if journal["phase"] == "complete":
        return journal
    if journal["phase"] in {"undone", "undoing"}:
        raise ValueError("This export is being undone or was already undone.")
    root, stage = Path(journal["root"]), _stage_directory(journal)
    completed = 0
    total = max(1, len(journal["files"]) * 3 + len(journal["backups"]))

    def checkpoint(label):
        nonlocal completed
        if fault:
            fault(label, journal)
        completed += 1
        if progress:
            progress(min(.99, completed / total), label)
        if cancel and cancel.is_set():
            raise ExportPaused()

    try:
        checkpoint("Checking sources, collisions, and space")
        _preflight(journal)
        journal["phase"], journal["error"] = "staging", ""
        _save(journal, path)
        for entry in journal["files"]:
            checkpoint(f"Staging {entry['relative']}")
            if entry["keep_existing"]:
                entry["state"] = "retained"
            elif entry["state"] == "pending":
                temporary = stage / entry["stage"]
                if entry["kind"] == "audio":
                    _copy_verified(entry["source"], temporary, entry["sha256"], cancel)
                else:
                    with temporary.open("wb") as stream:
                        stream.write(entry["payload"].encode("utf-8"))
                        stream.flush()
                        os.fsync(stream.fileno())
                _check_hash(temporary, entry["sha256"])
                entry["identity"], entry["state"] = _identity(temporary), "staged"
            _save(journal, path)
        journal["phase"] = "backing-up"
        _save(journal, path)
        for entry in journal["backups"]:
            checkpoint(f"Preserving previous {entry['relative']}")
            original, backup = root / entry["relative"], stage / entry["stage"]
            if entry["state"] != "backed-up":
                if backup.exists():
                    _check_hash(backup, entry["sha256"])
                    if _exists(original) and not any(e["relative"] == entry["relative"] and e["state"] == "published" for e in journal["files"]):
                        raise FileExistsError(f"A file appeared after backup: {original}")
                else:
                    _check_hash(original, entry["sha256"])
                    entry["identity"], entry["state"] = _identity(original), "backing-up"
                    _save(journal, path)
                    _rename_exclusive(original, backup)
                    checkpoint("After backup rename")
                entry["state"] = "backed-up"
                _save(journal, path)
        journal["phase"] = "publishing"
        _save(journal, path)
        for entry in journal["files"]:
            checkpoint(f"Publishing {entry['relative']}")
            target, temporary = root / entry["relative"], stage / entry["stage"]
            if entry["keep_existing"]:
                continue
            if _exists(target):
                if _identity(target) != entry.get("identity"):
                    raise FileExistsError(f"An unrelated file appeared: {target}")
                _check_hash(target, entry["sha256"])
            else:
                if entry["state"] == "published":
                    raise ValueError(f"A published file was removed externally: {target}")
                _check_hash(temporary, entry["sha256"])
                entry["state"] = "publishing"
                _save(journal, path)
                _rename_exclusive(temporary, target)
                checkpoint("After output rename")
                _check_hash(target, entry["sha256"])
            entry["state"] = "published"
            _save(journal, path)
        if journal["move"]:
            journal["phase"] = "removing-sources"
            _save(journal, path)
            output_paths = {str(root / e["relative"]) for e in journal["files"]}
            for entry in journal["files"]:
                if entry["kind"] != "audio" or entry["source"] == str(root / entry["relative"]):
                    continue
                checkpoint(f"Completing move {entry['relative']}")
                target, source = root / entry["relative"], Path(entry["source"])
                _check_hash(target, entry["sha256"])
                if entry["source_removed"]:
                    continue
                # A source from a previous export was moved into its retained backup.
                backup = next((b for b in journal["backups"] if root / b["relative"] == source), None)
                if backup:
                    _check_hash(stage / backup["stage"], entry["sha256"])
                elif str(source) in output_paths:
                    # Identical recordings with identical basenames can exchange
                    # retained destinations on re-export. Never remove a new output.
                    _check_hash(source, entry["sha256"])
                else:
                    quarantine = source.parent / f".music-analyzer-{journal['id']}-{entry['stage']}.moved"
                    if not quarantine.exists() and source.exists():
                        _check_hash(source, entry["sha256"])
                        entry["removing_source"] = True
                        _save(journal, path)
                        _rename_exclusive(source, quarantine)
                        checkpoint("After source quarantine")
                    elif not quarantine.exists() and not entry.get("removing_source"):
                        raise ValueError(f"Source disappeared before its verified move: {source}")
                    if quarantine.exists():
                        # Validate the actual renamed object before deleting it;
                        # an external replacement during the move remains recoverable.
                        _check_hash(quarantine, entry["sha256"])
                        quarantine.unlink()
                        _sync_directory(source.parent)
                        checkpoint("After source removal")
                entry["source_removed"] = True
                _save(journal, path)
        journal["phase"] = "complete"
        _save(journal, path)
        if progress:
            progress(1., "Export complete · hashes verified")
    except ExportPaused:
        journal["phase"] = "paused"
        _save(journal, path)
    except Exception as exc:
        journal["phase"], journal["error"] = "failed", str(exc)
        _save(journal, path)
        raise
    return journal


def undo_export(path, cancel=None, progress=None, *, fault=None):
    """Undo complete or partial exports. Externally changed files are preserved."""
    path = Path(path).resolve()
    journal = load_journal(path)
    if journal["phase"] == "undone":
        return journal
    root, stage = Path(journal["root"]), _stage_directory(journal)

    def checkpoint(label):
        if progress:
            progress(.5, label)
        if fault:
            fault(label, journal)
        if cancel and cancel.is_set():
            raise ExportPaused()

    # Check every potential conflict before undo changes any user file.
    backed = {str(root / b["relative"]): b for b in journal["backups"] if (stage / b["stage"]).exists()}
    published = {str(root / e["relative"]): e for e in journal["files"]
                 if e.get("identity") and not e.get("undo_removed")
                 and (root / e["relative"]).exists() and _identity(root / e["relative"]) == e["identity"]}
    for entry in journal["files"]:
        target = root / entry["relative"]
        if entry.get("removing_source") and not Path(entry["source"]).exists():
            entry["source_removed"] = True
        if entry.get("identity") and not entry.get("undo_removed") and _exists(target):
            if _identity(target) != entry["identity"]:
                if entry["state"] in {"published", "publishing"}:
                    raise ValueError(f"Undo conflict; output was replaced: {target}")
            else:
                _check_hash(target, entry["sha256"])
        if entry.get("source_removed") and entry["source"] not in backed:
            source = Path(entry["source"])
            if _exists(source) and str(source) not in published:
                _check_hash(source, entry["sha256"])
        if entry.get("source_removed") and not entry.get("undo_source_restored"):
            recovery_copy = stage / f"undo-{entry['stage']}"
            if not target.exists() and not recovery_copy.exists() and entry["source"] not in backed and not Path(entry["source"]).exists():
                raise ValueError(f"Moved recording is missing; restore it before undo: {target}")
    for entry in journal["backups"]:
        backup, target = stage / entry["stage"], root / entry["relative"]
        if backup.exists():
            _check_hash(backup, entry["sha256"])
            if _exists(target) and str(target) not in published:
                raise FileExistsError(f"Undo would overwrite an unrelated file: {target}")
    journal["phase"] = "undoing"
    _save(journal, path)
    try:
        # Save moved sources before deleting outputs. This also supports cross-volume restoration.
        for entry in journal["files"]:
            if not entry.get("source_removed") or entry["source"] in backed or entry.get("undo_source_restored"):
                continue
            checkpoint(f"Preserving moved source {entry['relative']}")
            if Path(entry["source"]).exists() and entry["source"] not in published:
                _check_hash(entry["source"], entry["sha256"])
                entry["undo_source_restored"] = True
                _save(journal, path)
                continue
            temporary = stage / f"undo-{entry['stage']}"
            if not temporary.exists() or file_hash(temporary) != entry["sha256"]:
                _copy_verified(root / entry["relative"], temporary, entry["sha256"], cancel)
            entry["undo_source_identity"] = _identity(temporary)
            _save(journal, path)
        for entry in journal["files"]:
            if entry["keep_existing"] or entry.get("undo_removed") or not entry.get("identity"):
                continue
            checkpoint(f"Removing exported {entry['relative']}")
            target = root / entry["relative"]
            if _exists(target):
                if _identity(target) != entry["identity"]:
                    # A staged file has not yet been published; a previous export may still occupy the target.
                    if entry["state"] == "staged":
                        continue
                    raise ValueError(f"Undo conflict: {target}")
                _check_hash(target, entry["sha256"])
                entry["undo_removing"] = True
                _save(journal, path)
                target.unlink()
                _sync_directory(target.parent)
                checkpoint("After undo output removal")
            entry["undo_removed"] = True
            _save(journal, path)
        for entry in journal["files"]:
            if not entry.get("source_removed") or entry["source"] in backed or entry.get("undo_source_restored"):
                continue
            checkpoint(f"Restoring original {entry['source']}")
            source, temporary = Path(entry["source"]), stage / f"undo-{entry['stage']}"
            if source.exists():
                _check_hash(source, entry["sha256"])
            else:
                # The original may be on another volume: exclusive copy then verify,
                # never a rename that could lose the only remaining recovery copy.
                with source.open("xb") as writer, temporary.open("rb") as reader:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                    writer.flush()
                    os.fsync(writer.fileno())
                _check_hash(source, entry["sha256"])
                shutil.copystat(temporary, source)
                _sync_directory(source.parent)
                checkpoint("After original restoration")
            entry["undo_source_restored"] = True
            _save(journal, path)
        for entry in journal["backups"]:
            checkpoint(f"Restoring previous {entry['relative']}")
            backup, target = stage / entry["stage"], root / entry["relative"]
            if backup.exists():
                _check_hash(backup, entry["sha256"])
                _rename_exclusive(backup, target)
                checkpoint("After backup restoration")
            elif entry["state"] == "backed-up":
                _check_hash(target, entry["sha256"])
                if _identity(target) != entry.get("identity"):
                    raise ValueError(f"Previous file was replaced during undo: {target}")
            entry["undo_restored"] = True
            _save(journal, path)
        journal["phase"], journal["error"] = "undone", ""
        _save(journal, path)
        if progress:
            progress(1., "Export undone · originals restored")
    except ExportPaused:
        _save(journal, path)
    return journal
