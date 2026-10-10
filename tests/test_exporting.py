import json
import threading
from pathlib import Path

import pytest

from music_analyzer.audio import file_hash
from music_analyzer.domain import Track
from music_analyzer.exporting import (
    create_journal,
    execute_export,
    load_journal,
    make_export_plan,
    undo_export,
)


class PowerLoss(BaseException):
    pass


def corpus(root):
    tracks, scores = [], {}
    for index, name in enumerate(["01_Étude.wav", "quiet.wav", "怒り.flac", "final.mp3"]):
        source = root / name
        source.write_bytes(bytes([index + 1]) * (2048 + index))
        track = Track(str(index), str(source), name, sha256=file_hash(source), size=source.stat().st_size,
                      status="complete", reviewed=True)
        tracks.append(track)
        scores[track.id] = {"bucket": "positive" if index % 2 == 0 else "negative",
                            "intensity": 10 + index * 20, "needs_review": False}
    album = {"order": ["0", "1", "3", "2"], "warnings": []}
    return tracks, scores, album


def start(root, destination=None, **options):
    tracks, scores, album = corpus(root)
    plan = make_export_plan(tracks, scores, album, {"id": "snapshot"}, destination or root, "test-project", **options)
    return tracks, scores, album, create_journal(plan)


def test_copy_manifest_playlist_hashes_and_undo(tmp_path):
    tracks, _, _, path = start(tmp_path)
    result = execute_export(path)
    assert result["phase"] == "complete"
    manifest = json.loads((tmp_path / "album-manifest.json").read_text())
    playlist = (tmp_path / "album.m3u8").read_text().splitlines()[1:]
    assert playlist == [item["relative"] for item in manifest["mappings"]]
    assert len(playlist) == len(tracks)
    for item in manifest["mappings"]:
        assert file_hash(tmp_path / item["relative"]) == item["sha256"]
    assert playlist[0].endswith("1_01_Étude.wav")
    undo_export(path)
    assert all(Path(t.path).exists() for t in tracks)
    assert not (tmp_path / "album.m3u8").exists()
    assert not list((tmp_path / "Positive Valence").iterdir())


@pytest.mark.parametrize("label", ["After output rename", "After source quarantine", "After source removal"])
def test_move_recovers_power_loss_and_restores_originals(tmp_path, label):
    tracks, _, _, path = start(tmp_path, move=True)

    def crash(event, _):
        if event == label:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        execute_export(path, fault=crash)
    result = execute_export(path)
    assert result["phase"] == "complete"
    assert not any(Path(t.path).exists() for t in tracks)
    assert undo_export(path)["phase"] == "undone"
    for track in tracks:
        assert file_hash(track.path) == track.sha256


def test_cancel_resume_does_not_remove_sources(tmp_path):
    tracks, _, _, path = start(tmp_path, move=True)
    cancel = threading.Event()

    def cancel_after_stage(event, _):
        if event.startswith("Publishing"):
            cancel.set()

    result = execute_export(path, cancel, fault=cancel_after_stage)
    assert result["phase"] == "paused"
    assert all(Path(t.path).exists() for t in tracks)
    cancel.clear()
    assert execute_export(path, cancel)["phase"] == "complete"
    undo_export(path)


def test_changed_source_and_unrelated_case_collision_preserved(tmp_path):
    tracks, scores, album = corpus(tmp_path)
    folder = tmp_path / "Positive Valence"
    folder.mkdir()
    unrelated = folder / "1_01_ÉTUDE.wav"
    unrelated.write_bytes(b"unrelated")
    with pytest.raises(FileExistsError):
        path = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "p"))
        execute_export(path)
    assert unrelated.read_bytes() == b"unrelated"
    unrelated.unlink()
    path = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "p"))
    Path(tracks[0].path).write_bytes(b"changed externally")
    with pytest.raises(ValueError, match="changed"):
        execute_export(path)
    assert Path(tracks[0].path).read_bytes() == b"changed externally"


def test_undo_conflict_checks_all_outputs_before_deleting_any(tmp_path):
    _, _, _, path = start(tmp_path, move=True)
    result = execute_export(path)
    audio = [e for e in result["files"] if e["kind"] == "audio"]
    changed = tmp_path / audio[-1]["relative"]
    changed.write_bytes(b"external change")
    with pytest.raises(ValueError, match="changed"):
        undo_export(path)
    assert all((tmp_path / e["relative"]).exists() for e in audio)
    assert changed.read_bytes() == b"external change"


@pytest.mark.parametrize("label", ["After backup rename", "After output rename"])
def test_reexport_preserves_basename_and_recovers_previous_export(tmp_path, label):
    tracks, scores, album, first = start(tmp_path, move=True)
    old = execute_export(first)
    by_id = {e["track_id"]: e for e in old["files"] if e["kind"] == "audio"}
    for track in tracks:
        track.path = str(tmp_path / by_id[track.id]["relative"])
    album["order"] = list(reversed(album["order"]))
    second = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "test-project", move=True, previous_journal=first))

    def crash(event, _):
        if event == label:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        execute_export(second, fault=crash)
    current = execute_export(second)
    assert current["phase"] == "complete"
    new_audio = [e for e in current["files"] if e["kind"] == "audio"]
    assert next(e for e in new_audio if e["track_id"] == "0")["relative"].endswith("4_01_Étude.wav")
    assert len(list((tmp_path / "Positive Valence").iterdir())) == 2
    undo_export(second)
    for entry in old["files"]:
        assert file_hash(tmp_path / entry["relative"]) == entry["sha256"]
    undo_export(first)
    assert all((tmp_path / t.original_name).exists() for t in tracks)


@pytest.mark.parametrize("label", ["After undo output removal", "After original restoration", "After backup restoration"])
def test_undo_recovers_power_loss(tmp_path, label):
    tracks, scores, album, first = start(tmp_path, move=True)
    result = execute_export(first)
    path = first
    if label == "After backup restoration":
        for track in tracks:
            entry = next(e for e in result["files"] if e.get("track_id") == track.id)
            track.path = str(tmp_path / entry["relative"])
        album["order"] = list(reversed(album["order"]))
        path = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "test-project", move=True, previous_journal=first))
        execute_export(path)

    def crash(event, _):
        if event == label:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        undo_export(path, fault=crash)
    assert undo_export(path)["phase"] == "undone"


def test_copy_between_source_and_destination_filesystems_logic(tmp_path):
    source, output = tmp_path / "sources", tmp_path / "output"
    source.mkdir()
    output.mkdir()
    tracks, _, _, path = start(source, output, move=True)
    execute_export(path)
    assert not any(Path(t.path).exists() for t in tracks)
    undo_export(path)
    assert all(file_hash(t.path) == t.sha256 for t in tracks)


def test_disk_failure_keeps_originals_and_can_retry(tmp_path, monkeypatch):
    tracks, _, _, path = start(tmp_path, move=True)
    from music_analyzer import exporting

    original = exporting._rename_exclusive

    def disk_failure(*_):
        raise OSError(28, "disk full")

    monkeypatch.setattr(exporting, "_rename_exclusive", disk_failure)
    with pytest.raises(OSError, match="disk full"):
        execute_export(path)
    assert all(Path(t.path).exists() for t in tracks)
    assert load_journal(path)["phase"] == "failed"
    monkeypatch.setattr(exporting, "_rename_exclusive", original)
    assert execute_export(path)["phase"] == "complete"


def test_undo_partial_export_before_previous_backup(tmp_path):
    tracks, scores, album, first = start(tmp_path)
    execute_export(first)
    album["order"] = list(reversed(album["order"]))
    second = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "test-project", previous_journal=first))
    cancel = threading.Event()

    def pause(event, _):
        if event.startswith("Preserving previous"):
            cancel.set()

    execute_export(second, cancel, fault=pause)
    assert undo_export(second)["phase"] == "undone"
    for entry in load_journal(first)["files"]:
        assert file_hash(tmp_path / entry["relative"]) == entry["sha256"]


def test_unicode_normalization_collision_and_permissions(tmp_path, monkeypatch):
    tracks, scores, album = corpus(tmp_path)
    directory = tmp_path / "Positive Valence"
    directory.mkdir()
    decomposed = directory / "1_01_E\u0301tude.wav"
    decomposed.write_bytes(b"other")
    with pytest.raises(FileExistsError):
        path = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "p"))
        execute_export(path)
    assert decomposed.read_bytes() == b"other"
    decomposed.unlink()
    path = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "p"))
    from music_analyzer import exporting

    def denied(*_):
        raise PermissionError("destination is read only")

    monkeypatch.setattr(exporting, "_rename_exclusive", denied)
    with pytest.raises(PermissionError, match="read only"):
        execute_export(path)
    assert all(Path(t.path).exists() for t in tracks)


def test_reexport_identical_audio_names_never_deletes_retained_output(tmp_path):
    tracks, scores = [], {}
    for i in range(2):
        directory = tmp_path / str(i)
        directory.mkdir()
        source = directory / "same.wav"
        source.write_bytes(b"same recording")
        tracks.append(Track(str(i), str(source), source.name, sha256=file_hash(source), size=14,
                            status="complete", reviewed=True))
        scores[str(i)] = {"bucket": "positive", "intensity": 10, "needs_review": False}
    album = {"order": ["0", "1"]}
    first = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "p", move=True))
    result = execute_export(first)
    for track in tracks:
        entry = next(e for e in result["files"] if e.get("track_id") == track.id)
        track.path = str(tmp_path / entry["relative"])
    album["order"].reverse()
    second = create_journal(make_export_plan(tracks, scores, album, {}, tmp_path, "p", move=True, previous_journal=first))
    execute_export(second)
    assert len(list((tmp_path / "Positive Valence").iterdir())) == 2
    undo_export(second)
    undo_export(first)
    assert (tmp_path / "0/same.wav").exists() and (tmp_path / "1/same.wav").exists()
