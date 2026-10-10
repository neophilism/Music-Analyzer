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
    window.select_track("0")
    window.valence_edit.setValue(72)
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
