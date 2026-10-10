from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from music_analyzer.domain import Track
from music_analyzer.window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_native_review_override_order_and_project_reopen(app, tmp_path):
    window = MainWindow(tmp_path / "album.ma-project")
    window._show_error = lambda message: pytest.fail(message)
    for i, valence in enumerate([80, 20, 85, 15]):
        window.project.add_track(Track(id=str(i), path=f"/{i}.wav", original_name=f"{i}.wav", status="complete",
                                      analysis={"bpm": 70 + i * 20, "integrated_lufs": -32 + i * 5,
                                                "loudness_p90": -30 + i * 5, "sustained_fraction": .1 * i,
                                                "valence": valence, "arousal": 20 + i * 20,
                                                "onset_rate": i + 1, "density_raw": .1 + i * .1, "needs_review": True}))
    window.refresh()
    window.recalculate()
    assert window.table_model.rowCount() == 4
    window.bucket_filter.setCurrentIndex(1)
    assert window.proxy.rowCount() == 2
    window.bucket_filter.setCurrentIndex(2)
    assert window.proxy.rowCount() == 2
    window.bucket_filter.setCurrentIndex(0)
    window.select_track("0")
    window.valence_edit.setValue(72)
    window.refresh()  # Arrival of another worker result must not discard a typed correction.
    assert window.valence_edit.value() == 72
    window.apply_override()
    assert window.project.tracks()[0].analysis["valence"] == 80
    assert window.project.tracks()[0].overrides["valence"] == 72
    window.accept_suggested()
    window.rebuild_order()
    assert len(window.album["order"]) == 4
    window.select_track("0")
    window.toggle_pin()
    assert "0" in window.pins
    window.close()
    reopened = MainWindow(tmp_path / "album.ma-project")
    assert len(reopened.album["order"]) == 4 and "0" in reopened.pins
    reopened.close()


def test_export_updates_project_paths_and_undo_restores_names(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from music_analyzer.audio import file_hash
    from music_analyzer.exporting import (
        create_journal,
        execute_export,
        make_export_plan,
        undo_export,
    )

    monkeypatch.setattr(QMessageBox, "information", lambda *_: None)
    window = MainWindow(tmp_path / "album.ma-project")
    tracks, scores = [], {}
    for i in range(2):
        path = tmp_path / f"original-{i}.wav"
        path.write_bytes(bytes([i]) * 500)
        track = Track(str(i), str(path), path.name, sha256=file_hash(path), size=500,
                      status="complete", reviewed=True)
        tracks.append(track)
        scores[track.id] = {"bucket": "positive", "intensity": i * 50, "needs_review": False}
        window.project.add_track(track)
    plan = make_export_plan(tracks, scores, {"order": ["0", "1"]}, {}, tmp_path, "project", move=True)
    journal = create_journal(plan)
    window._export_finished(execute_export(journal))
    moved = window.project.tracks()
    assert moved[0].original_name == "original-0.wav"
    assert Path(moved[0].path).name == "1_original-0.wav"
    window._export_finished(undo_export(journal))
    assert window.project.tracks()[0].path == tracks[0].path
    window.close()
