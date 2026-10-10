import shutil

import numpy as np
import pytest
import soundfile as sf

from music_analyzer.project import Project, expand_paths, inspect_track


def test_project_reopen_duplicate_and_relocation(tmp_path):
    source = tmp_path / "7_original.wav"
    sf.write(source, np.zeros(8000), 8000)
    duplicate = tmp_path / "duplicate.wav"
    shutil.copyfile(source, duplicate)
    with Project(tmp_path / "album.ma-project") as project:
        first = inspect_track(source)
        assert first.status == "pending"
        assert project.add_track(first)
        assert not project.add_track(inspect_track(source))
        assert not project.add_track(inspect_track(duplicate), keep_duplicates=False)
        second = inspect_track(duplicate)
        assert project.add_track(second)
        assert second.duplicate_of == first.id
        first.analysis = {"bpm": 120}
        first.overrides = {"bpm": 60, "valence": 25}
        first.status = "analyzing"
        project.save_track(first)
        project.set_metadata("order", [first.id, second.id])
        replacement = tmp_path / "relocated.wav"
        shutil.copyfile(source, replacement)
        project.relocate(first, replacement)
    with Project(tmp_path / "album.ma-project") as project:
        first = project.tracks()[0]
        assert first.status == "pending"
        assert first.value("bpm") == 60 and first.analysis["bpm"] == 120
        assert first.original_name == "7_original.wav"
        assert first.path.endswith("relocated.wav")
        assert len(project.metadata("order")) == 2
        wrong = tmp_path / "wrong.wav"
        sf.write(wrong, np.ones(8000) * .1, 8000)
        with pytest.raises(ValueError, match="hash"):
            project.relocate(first, wrong)


def test_corrupt_file_and_directory_import(tmp_path):
    (tmp_path / "broken.mp3").write_bytes(b"this is not audio")
    (tmp_path / "ignore.txt").write_text("ignore")
    track = inspect_track(tmp_path / "broken.mp3")
    assert track.status == "error" and track.error
    assert expand_paths([tmp_path, tmp_path / "broken.mp3"]) == [tmp_path / "broken.mp3"]
