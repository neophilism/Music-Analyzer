"""One-window native listening, review, and album workspace."""

import json
import sqlite3
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from music_analyzer.calibration import fit_intensity_pairs, fit_valence_anchors
from music_analyzer.domain import AnalysisSettings
from music_analyzer.emotion import MOODS
from music_analyzer.exporting import (
    create_journal,
    execute_export,
    load_journal,
    make_export_plan,
)
from music_analyzer.exporting import (
    undo_export as undo_files,
)
from music_analyzer.jobs import BatchRunner
from music_analyzer.models import (
    default_model_directory,
    install_model,
    model_identity,
    model_present,
)
from music_analyzer.project import Project, expand_paths, inspect_track
from music_analyzer.scoring import fingerprint, finite, make_snapshot, score_tracks
from music_analyzer.sequencing import build_album, validate_manual_order
from music_analyzer.ui_support import CurvePlot, ScatterPlot, TaskThread, TrackTable


def button(text, handler, parent=None):
    widget = QPushButton(text, parent)
    widget.clicked.connect(handler)
    return widget


def number_editor(minimum, maximum):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(1)
    widget.setSpecialValueText("Unknown")
    return widget


class TrackFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.review_only = False
        self.query = ""
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        track = model.tracks[row]
        if self.review_only and (track.excluded or not (track.status == "error" or model.scores.get(track.id, {}).get("needs_review", True))):
            return False
        return not self.query or self.query.casefold() in " ".join(map(str, model.values(track))).casefold()


class MainWindow(QMainWindow):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project = Project(project_path)
        self.runner = BatchRunner(self.project)
        self.task = None
        self.closing = False
        self.selected_id = None
        self.tracks, self.scores, self.fractions = [], {}, {}
        self.snapshot = self.project.metadata("snapshot")
        self.album = self.project.metadata("album")
        self.pins = self.project.metadata("pins", {})
        self.model_directory = Path(self.project.metadata("model_directory", str(default_model_directory())))
        self.options = AnalysisSettings(**self.project.metadata("analysis_settings", {}))
        self.resize(1400, 880)
        self.setMinimumSize(1000, 650)
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_menus()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self.refresh()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 12)
        heading = QHBoxLayout()
        title = QLabel("Music Analyzer")
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        heading.addWidget(title)
        heading.addStretch()
        self.summary = QLabel()
        heading.addWidget(self.summary)
        layout.addLayout(heading)
        subtitle = QLabel("Listen, compare, and shape an instrumental album. Your audio stays on this computer.")
        subtitle.setStyleSheet("color: #82909f; padding-bottom: 8px;")
        layout.addWidget(subtitle)
        actions = QHBoxLayout()
        self.add_button = button("Add tracks…", self.add_files)
        self.analyze_button = button("Analyze", self.start_analysis)
        self.build_button = button("Build order", self.rebuild_order)
        self.export_button = button("Export…", self.export_album)
        for name, widget in (("addTracks", self.add_button), ("analyze", self.analyze_button), ("buildOrder", self.build_button), ("export", self.export_button)):
            widget.setObjectName(name)
            widget.setMinimumHeight(34)
            actions.addWidget(widget)
        actions.addStretch()
        actions.addWidget(button("Local model…", self.model_dialog))
        actions.addWidget(button("Preferences…", self.preferences))
        layout.addLayout(actions)
        self.snapshot_note = QLabel()
        self.snapshot_note.setWordWrap(True)
        layout.addWidget(self.snapshot_note)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = QTabWidget()
        workspace = QWidget()
        work_layout = QVBoxLayout(workspace)
        search = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a track, mood, or genre…")
        self.review_filter = QCheckBox("Needs review")
        self.search.textChanged.connect(self._filter_changed)
        self.review_filter.toggled.connect(self._filter_changed)
        search.addWidget(self.search)
        search.addWidget(self.review_filter)
        work_layout.addLayout(search)
        self.table_model = TrackTable(self)
        self.table_model.changed.connect(self._save_edited_track)
        self.proxy = TrackFilter(self)
        self.proxy.setSourceModel(self.table_model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setColumnWidth(0, 44)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 120)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        work_layout.addWidget(self.table, 3)
        self.scatter = ScatterPlot()
        self.scatter.selected.connect(self.select_track)
        work_layout.addWidget(self.scatter, 1)
        review_actions = QHBoxLayout()
        review_actions.addWidget(button("Accept suggested assignments", self.accept_suggested))
        review_actions.addWidget(button("Recalculate scales", self.recalculate))
        review_actions.addStretch()
        work_layout.addLayout(review_actions)
        self.tabs.addTab(workspace, "Tracks & review")
        album_page = QWidget()
        album_layout = QVBoxLayout(album_page)
        order_controls = QHBoxLayout()
        self.order_mode = QComboBox()
        self.order_mode.addItems(["Rising groups + preferred finale", "Prioritize alternation", "Global intensity"])
        self.order_mode.setCurrentIndex(self.project.metadata("order_mode", 0))
        self.profile = QComboBox()
        self.profile.addItems(["Perceived intensity", "Dynamics + tempo"])
        self.profile.setCurrentIndex(1 if self.snapshot and self.snapshot["profile"] == "simple" else 0)
        order_controls.addWidget(self.profile)
        order_controls.addWidget(self.order_mode)
        order_controls.addWidget(button("Build proposal", self.rebuild_order))
        album_layout.addLayout(order_controls)
        self.album_note = QLabel("Build an order after reviewing uncertain tracks. Drag to edit; pin selected positions in the inspector.")
        self.album_note.setWordWrap(True)
        album_layout.addWidget(self.album_note)
        self.album_list = QListWidget()
        self.album_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.album_list.currentItemChanged.connect(self._album_selected)
        self.album_list.model().rowsMoved.connect(self._album_moved)
        album_layout.addWidget(self.album_list, 3)
        self.album_curve = CurvePlot("Album intensity /100 · track position")
        album_layout.addWidget(self.album_curve, 1)
        self.tabs.addTab(album_page, "Album order")
        splitter.addWidget(self.tabs)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        self.track_heading = QLabel("Select a track")
        self.track_heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.track_heading.setWordWrap(True)
        inspector_layout.addWidget(self.track_heading)
        self.track_detail = QLabel("Measurements and interpretation appear here after analysis.")
        self.track_detail.setWordWrap(True)
        inspector_layout.addWidget(self.track_detail)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(lambda *_: self.statusBar().showMessage(self.player.errorString(), 10000))
        playback = QHBoxLayout()
        self.play_button = button("Play / pause", self.toggle_play)
        playback.addWidget(self.play_button)
        self.match_loudness = QCheckBox("Match loudness")
        self.match_loudness.setToolTip("Attenuate analyzed tracks to the quietest measured track. Playback only; audio files are unchanged.")
        self.match_loudness.toggled.connect(self._playback_gain)
        playback.addWidget(self.match_loudness)
        inspector_layout.addLayout(playback)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setAccessibleName("Playback position")
        self.seek_slider.sliderMoved.connect(self.player.setPosition)
        self.player.durationChanged.connect(lambda duration: self.seek_slider.setRange(0, duration))
        self.player.positionChanged.connect(self.seek_slider.setValue)
        inspector_layout.addWidget(self.seek_slider)
        self.waveform = CurvePlot("Waveform envelope · seconds")
        self.waveform.seek.connect(lambda seconds: self.player.setPosition(round(seconds * 1000)))
        inspector_layout.addWidget(self.waveform)
        self.loudness_plot = CurvePlot("Short-term loudness · LUFS")
        inspector_layout.addWidget(self.loudness_plot)
        self.tempo_plot = CurvePlot("Local pulse · BPM")
        inspector_layout.addWidget(self.tempo_plot)
        self.emotion_plot = CurvePlot("Positivity /100 · seconds")
        inspector_layout.addWidget(self.emotion_plot)
        form = QFormLayout()
        self.bpm_edit = number_editor(0, 400)
        self.bpm_edit.setObjectName("bpmOverride")
        self.valence_edit = number_editor(-1, 100)
        self.valence_edit.setObjectName("valenceOverride")
        self.arousal_edit = number_editor(-1, 100)
        self.mode_edit = QComboBox()
        self.mode_edit.addItems(["Automatic", "major", "minor", "mixed", "unknown", "modal/atonal"])
        self.bucket_edit = QComboBox()
        self.bucket_edit.addItems(["Automatic", "positive", "negative"])
        self.mood_edit = QComboBox()
        self.mood_edit.addItems(["Automatic", *MOODS])
        self.genres_edit = QLineEdit()
        for label, editor in (("BPM", self.bpm_edit), ("Positivity 0–100", self.valence_edit), ("Arousal 0–100", self.arousal_edit),
                              ("Mode", self.mode_edit), ("Valence folder", self.bucket_edit), ("Mood", self.mood_edit), ("Genres", self.genres_edit)):
            form.addRow(label, editor)
        inspector_layout.addLayout(form)
        tempo_controls = QHBoxLayout()
        tempo_controls.addWidget(button("½ BPM", lambda: self.bpm_edit.setValue(self.bpm_edit.value() / 2)))
        tempo_controls.addWidget(button("2× BPM", lambda: self.bpm_edit.setValue(self.bpm_edit.value() * 2)))
        tempo_controls.addWidget(button("Tap tempo…", self.tap_dialog))
        inspector_layout.addLayout(tempo_controls)
        edit_controls = QHBoxLayout()
        edit_controls.addWidget(button("Apply & review", self.apply_override))
        edit_controls.addWidget(button("Reset edits", self.reset_override))
        inspector_layout.addLayout(edit_controls)
        self.pin_button = button("Pin current album position", self.toggle_pin)
        inspector_layout.addWidget(self.pin_button)
        inspector_layout.addWidget(button("Relocate missing file…", self.relocate_file))
        inspector_layout.addWidget(button("Reference anchors…", self.reference_dialog))
        self.raw_details = QPlainTextEdit()
        self.raw_details.setReadOnly(True)
        self.raw_details.setMaximumHeight(180)
        self.raw_details.setPlaceholderText("Candidates, reliability, and review reasons")
        inspector_layout.addWidget(self.raw_details)
        inspector_layout.addStretch()
        inspector_scroll.setWidget(inspector)
        splitter.addWidget(inspector_scroll)
        splitter.setSizes([980, 380])
        layout.addWidget(splitter, 1)
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        self.progress_label = QLabel("Ready")
        self.cancel_button = button("Cancel", self.cancel_work)
        self.cancel_button.setEnabled(False)
        progress_row.addWidget(self.progress, 2)
        progress_row.addWidget(self.progress_label, 1)
        progress_row.addWidget(self.cancel_button)
        layout.addLayout(progress_row)
        self.setCentralWidget(root)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("File")
        for text, shortcut, handler in (("New project…", QKeySequence.StandardKey.New, self.new_project),
                                        ("Open project…", QKeySequence.StandardKey.Open, self.open_project),
                                        ("Save project as…", QKeySequence.StandardKey.SaveAs, self.save_as),
                                        ("Add tracks…", "Ctrl+I", self.add_files),
                                        ("Export…", "Ctrl+E", self.export_album),
                                        ("Quit", QKeySequence.StandardKey.Quit, self.close)):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)
            file_menu.addAction(action)
        tools = self.menuBar().addMenu("Tools")
        for text, handler in (("Local model…", self.model_dialog), ("Preferences…", self.preferences),
                              ("Reference anchors…", self.reference_dialog), ("Recover export…", self.recover_export),
                              ("Undo export…", self.undo_export)):
            action = QAction(text, self)
            action.triggered.connect(handler)
            tools.addAction(action)
        help_menu = self.menuBar().addMenu("Help")
        action = QAction("About & accuracy", self)
        action.triggered.connect(lambda: QMessageBox.information(self, "Music Analyzer", "Local instrumental analysis.\n\nLoudness and rhythm are acoustic measurements. Genre, mood, and positivity are uncalibrated model estimates; review them by listening. Major/minor does not determine emotion.\n\nAudio is never uploaded. The optional model downloads about 780 MB once.\n\nFirst distribution target: Apple Silicon, macOS 14+."))
        help_menu.addAction(action)

    @property
    def busy(self):
        return self.runner.running or (self.task is not None and self.task.isRunning())

    def refresh(self):
        self.tracks = self.project.tracks()
        self.scores = score_tracks(self.tracks, self.snapshot) if self.snapshot else {}
        self.table_model.replace(self.tracks, self.scores)
        complete = sum(t.status == "complete" for t in self.tracks)
        review = sum(not t.excluded and self.scores.get(t.id, {}).get("needs_review", True) for t in self.tracks)
        self.summary.setText(f"{len(self.tracks)} tracks  ·  {complete} analyzed  ·  {review} to review")
        self.setWindowTitle(f"{self.project.path.stem} — Music Analyzer")
        stale = self.snapshot and self.snapshot["fingerprint"] != fingerprint(self.tracks)
        self.snapshot_note.setText("Scales are frozen. Measurements or membership changed; choose Recalculate scales to update comparisons." if stale else "Reference-calibrated dynamics · corpus tempo · fixed semantic positivity" if self.snapshot and self.snapshot.get("reference") else "Corpus comparison scales · fixed semantic positivity (50 = neutral)" if self.snapshot else "Add audio files or drag a folder here to begin.")
        self.scatter.set_tracks(self.tracks, self.scores, self.selected_id)
        self._render_album()
        if self.selected_id:
            self.select_track(self.selected_id)
        self._update_busy()

    def _update_busy(self):
        busy = self.busy
        for widget in (self.add_button, self.analyze_button, self.build_button, self.export_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.album_list.setDragEnabled(not busy)

    def _filter_changed(self, *_):
        self.proxy.query = self.search.text()
        self.proxy.review_only = self.review_filter.isChecked()
        self.proxy.invalidateFilter()

    def _selection_changed(self, *_):
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            source = self.proxy.mapToSource(indexes[0])
            self._inspect(self.tracks[source.row()])

    def select_track(self, tid):
        track = next((t for t in self.tracks if t.id == tid), None)
        if not track:
            return
        self._inspect(track)
        row = next(i for i, t in enumerate(self.tracks) if t.id == tid)
        index = self.proxy.mapFromSource(self.table_model.index(row, 1))
        if index.isValid() and self.table.currentIndex().row() != index.row():
            self.table.selectRow(index.row())
            self.table.scrollTo(index)

    def _inspect(self, track):
        self.selected_id = track.id
        self.track_heading.setText(track.original_name)
        score = self.scores.get(track.id, {})
        def fmt(value):
            return f"{value:.1f}" if finite(value) else "unknown"
        self.track_detail.setText(f"{track.duration / 60:.2f} min · {track.sample_rate} Hz · {track.channels} channel(s)\n"
                                  f"LUFS {fmt(track.value('integrated_lufs'))} · LRA {fmt(track.value('lra_lu'))} LU\n"
                                  f"Tempo spread {fmt(track.value('tempo_spread_bpm'))} BPM · volume spread {fmt(track.value('loudness_spread_lu'))} LU\n"
                                  f"Key: {track.value('key', 'unknown')} · intensity coverage {score.get('coverage', 0):.0%}\n"
                                  + ("Duplicate recording · " if track.duplicate_of else "") + (track.error or ""))
        self.waveform.set_points(track.analysis.get("waveform", []))
        self.loudness_plot.set_points(track.analysis.get("loudness_curve", []))
        self.tempo_plot.set_points([(r["time"], r["bpm"]) for r in track.analysis.get("tempo_curve", [])])
        self.emotion_plot.set_points([(r["time"], r["valence"]) for r in track.analysis.get("emotion_curve", [])])
        self.bpm_edit.setValue(track.value("bpm") or 0)
        self.valence_edit.setValue(score.get("valence") if finite(score.get("valence")) else -1)
        self.arousal_edit.setValue(track.value("arousal") if finite(track.value("arousal")) else -1)
        for editor, key in ((self.mode_edit, "mode"), (self.bucket_edit, "bucket"), (self.mood_edit, "mood")):
            value = track.overrides.get(key, "Automatic")
            editor.setCurrentText(value)
        self.genres_edit.setText(", ".join(track.value("genres", [])))
        self.pin_button.setText("Unpin album position" if track.id in self.pins else "Pin current album position")
        details = {key: track.analysis.get(key) for key in ("genre_candidates", "mood_candidates", "key_candidates", "tempo_reliability", "valence_reliability", "model_coverage", "review_reasons", "warnings")}
        details["missing_intensity_components"] = score.get("missing_components", [])
        self.raw_details.setPlainText(json.dumps(details, ensure_ascii=False, indent=2))
        self.scatter.set_tracks(self.tracks, self.scores, track.id)

    def selected_track(self):
        return next((t for t in self.tracks if t.id == self.selected_id), None)

    def _save_edited_track(self, track):
        if self.busy:
            self.refresh()
            return
        self.project.save_track(track)
        self.refresh()

    def _start_task(self, function, success=None, item=None):
        if self.busy:
            return
        self.task = TaskThread(function, self)
        self.task.progress.connect(self._task_progress)
        self.task.failed.connect(self._show_error)
        if success:
            self.task.succeeded.connect(success)
        if item:
            self.task.item.connect(item)
        self.task.finished.connect(self._task_finished)
        self.task.start()
        self._update_busy()

    def _task_progress(self, fraction, description):
        self.progress.setValue(round(fraction * 1000))
        self.progress_label.setText(description)

    def _task_finished(self):
        finished_task = self.task
        self.task = None
        if finished_task:
            finished_task.deleteLater()
        self.refresh()
        self.progress_label.setText("Ready · changes saved")
        if self.closing:
            self.close()

    def add_files(self):
        if self.busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add instrumental recordings", "", "Audio (*.wav *.wave *.aif *.aiff *.flac *.mp3 *.m4a *.aac *.ogg *.opus);;All files (*)")
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths):
        def importer(task):
            expanded = expand_paths(paths)
            for index, path in enumerate(expanded):
                if task.cancel_event.is_set():
                    break
                task.progress.emit(index / max(len(expanded), 1), f"Importing {index + 1}/{len(expanded)} · {path.name}")
                task.item.emit(inspect_track(path, self.options.ffmpeg_path))
            return len(expanded)
        self._start_task(importer, item=self._imported)

    def _imported(self, track):
        self.project.add_track(track)
        self.refresh()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.import_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def start_analysis(self):
        if self.busy or not self.tracks:
            return
        available = self.options.model_enabled and model_present(self.model_directory)
        self.fractions = {}
        self.runner.start([t for t in self.tracks if not t.excluded], self.options,
                          str(self.model_directory) if available else "", model_identity() if available else "none")
        self._update_busy()
        if not self.runner.running:
            self._analysis_finished()

    def _poll(self):
        if not self.runner.processes:
            return
        events = self.runner.poll()
        changed = False
        for event in events:
            if event["type"] == "progress":
                self.fractions[event["id"]] = event["fraction"]
                self.progress_label.setText(event["phase"])
            else:
                self.fractions.pop(event["id"], None)
                changed = True
        done = self.runner.completed + self.runner.failed
        fraction = (done + sum(self.fractions.values())) / max(self.runner.total, 1)
        self.progress.setValue(round(fraction * 1000))
        eta = self.runner.eta
        self.statusBar().showMessage(f"{done}/{self.runner.total} complete · {self.runner.failed} failed" + (f" · ETA {eta / 60:.1f} min" if eta is not None else ""))
        if changed:
            self.refresh()
        if not self.runner.running:
            self._analysis_finished()

    def _analysis_finished(self):
        if self.snapshot is None:
            self.recalculate()
        else:
            self.refresh()
        self.progress_label.setText("Analysis complete · review uncertain interpretations")
        self._update_busy()
        if self.closing:
            self.close()

    def cancel_work(self):
        if self.runner.running:
            self.runner.cancel()
        if self.task and self.task.isRunning():
            self.task.cancel_event.set()
        self.progress_label.setText("Cancelling · completed work is saved")

    def recalculate(self):
        if self.busy:
            return
        try:
            profile = "simple" if self.profile.currentIndex() else "perceived"
            self.snapshot = make_snapshot(self.project.tracks(), profile=profile,
                                          weights=self.project.metadata("intensity_weights"),
                                          reference_ids=self.project.metadata("reference_ids"),
                                          valence_calibration=self.project.metadata("valence_calibration"))
            self.project.set_metadata("snapshot", self.snapshot)
            self.refresh()
        except ValueError as exc:
            self._show_error(str(exc))

    def accept_suggested(self):
        if self.busy:
            return
        for track in self.tracks:
            if not track.excluded and track.status == "complete" and finite(track.value("valence")):
                track.reviewed = True
                self.project.save_track(track)
        self.refresh()

    def apply_override(self):
        track = self.selected_track()
        if not track or self.busy:
            return
        track.overrides["bpm"] = self.bpm_edit.value() or None
        track.overrides["valence"] = self.valence_edit.value() if self.valence_edit.value() >= 0 else None
        track.overrides["arousal"] = self.arousal_edit.value() if self.arousal_edit.value() >= 0 else None
        track.overrides["genres"] = [value.strip() for value in self.genres_edit.text().split(",") if value.strip()]
        for editor, key in ((self.mode_edit, "mode"), (self.bucket_edit, "bucket"), (self.mood_edit, "mood")):
            if editor.currentText() == "Automatic":
                track.overrides.pop(key, None)
            else:
                track.overrides[key] = editor.currentText()
        track.reviewed = True
        self.project.save_track(track)
        self.refresh()

    def reset_override(self):
        track = self.selected_track()
        if track and not self.busy:
            track.overrides, track.reviewed = {}, False
            self.project.save_track(track)
            self.refresh()

    def rebuild_order(self):
        if self.busy:
            return
        if not self.snapshot or (self.snapshot["profile"] == "simple") != bool(self.profile.currentIndex()):
            self.recalculate()
        if not self.snapshot:
            return
        try:
            mode = ["balanced", "alternating", "global"][self.order_mode.currentIndex()]
            album = build_album(self.tracks, self.scores, mode, self.pins)
            self.album = album.to_dict()
            self.album["snapshot_id"] = self.snapshot["id"]
            self.album["fingerprint"] = fingerprint(self.tracks)
            self.project.set_metadata("album", self.album)
            self.project.set_metadata("order_mode", self.order_mode.currentIndex())
            self._render_album()
            self.tabs.setCurrentIndex(1)
        except ValueError as exc:
            self._show_error(str(exc))

    def _render_album(self):
        self.album_list.blockSignals(True)
        self.album_list.clear()
        by_id = {t.id: t for t in self.tracks}
        order = self.album.get("order", []) if self.album else []
        points = []
        for position, tid in enumerate(order, 1):
            if tid not in by_id or tid not in self.scores:
                continue
            score = self.scores[tid]
            intensity = score.get("intensity")
            label = f"{position:03d}  ·  {by_id[tid].original_name}   |   {score.get('bucket', '?')}  ·  intensity {intensity:.1f}" if finite(intensity) else f"{position:03d}  ·  {by_id[tid].original_name} · unresolved"
            if tid in self.pins:
                label += "  ·  pinned"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tid)
            self.album_list.addItem(item)
            points.append((position, intensity))
        self.album_list.blockSignals(False)
        self.album_curve.set_points(points)
        if self.album:
            self.album_note.setText("\n".join(self.album.get("warnings", [])) or "Each group rises by intensity. Drag to create a custom order.")

    def _album_selected(self, current, _):
        if current:
            self.select_track(current.data(Qt.ItemDataRole.UserRole))

    def _album_moved(self, *_):
        if not self.album:
            return
        order = [self.album_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.album_list.count())]
        try:
            warnings = validate_manual_order(order, self.tracks, self.scores, self.pins)
            self.album["order"], self.album["warnings"] = order, warnings
            self.album["custom"] = True
            self.project.set_metadata("album", self.album)
        except ValueError as exc:
            self._show_error(str(exc))
        QTimer.singleShot(0, self._render_album)

    def toggle_pin(self):
        if not self.album or not self.selected_id or self.busy:
            return
        tid = self.selected_id
        if tid in self.pins:
            self.pins.pop(tid)
        elif tid in self.album["order"]:
            self.pins[tid] = self.album["order"].index(tid) + 1
        self.project.set_metadata("pins", self.pins)
        self.refresh()

    def toggle_play(self):
        track = self.selected_track()
        if not track:
            return
        url = QUrl.fromLocalFile(track.path)
        if self.player.source() != url:
            self.player.setSource(url)
        self._playback_gain()
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _playback_gain(self, *_):
        track = self.selected_track()
        volume = 1.
        levels = [t.value("integrated_lufs") for t in self.tracks if finite(t.value("integrated_lufs"))]
        if self.match_loudness.isChecked() and track and levels and finite(track.value("integrated_lufs")):
            volume = min(1., 10 ** ((min(levels) - track.value("integrated_lufs")) / 20))
        self.audio_output.setVolume(volume)

    def tap_dialog(self):
        from music_analyzer.rhythm import tap_tempo
        dialog = QDialog(self)
        dialog.setWindowTitle("Tap tempo")
        layout = QVBoxLayout(dialog)
        label = QLabel("Tap at least four steady beats; Apply & review saves the estimate.")
        layout.addWidget(label)
        times = []
        def tap():
            times.append(time.monotonic())
            if len(times) >= 4:
                bpm, variability = tap_tempo(times)
                self.bpm_edit.setValue(bpm)
                label.setText(f"{bpm:.1f} BPM · tap variability {variability:.1f}%")
        layout.addWidget(button("Tap beat", tap))
        layout.addWidget(button("Done", dialog.accept))
        dialog.exec()

    def model_dialog(self):
        if self.busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Local music model")
        layout = QVBoxLayout(dialog)
        text = QLabel("The music-specific LAION CLAP model runs on this computer.\nDownload: about 780 MB. Apache-2.0 model metadata.\nGenre and emotion are similarity estimates, not calibrated probabilities.\n\nNo tracks are uploaded. Installation is the only network action.\n\n" + ("Installed at: " if model_present(self.model_directory) else "Install location: ") + str(self.model_directory))
        text.setWordWrap(True)
        layout.addWidget(text)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        install = controls.addButton("Install / verify model", QDialogButtonBox.ButtonRole.ActionRole)
        def begin():
            dialog.accept()
            self._start_task(lambda task: install_model(self.model_directory, task.progress.emit, task.cancel_event.is_set))
        install.clicked.connect(begin)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        dialog.exec()

    def preferences(self):
        if self.busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Analysis preferences")
        form = QFormLayout(dialog)
        model = QCheckBox("Use installed model for genre and emotion")
        model.setChecked(self.options.model_enabled)
        stride = QComboBox()
        stride.addItems(["Full coverage · 10 seconds", "Faster sampling · 30 seconds", "Fast sampling · 60 seconds"])
        stride.setCurrentIndex({10.: 0, 30.: 1, 60.: 2}.get(self.options.model_stride_seconds, 0))
        device = QComboBox()
        device.addItems(["cpu", "mps"])
        device.setCurrentText(self.options.device)
        normalized = QCheckBox("Gain-normalized model input (source audio unchanged)")
        normalized.setChecked(self.options.model_profile == "gain-normalized")
        ffmpeg = QLineEdit(self.options.ffmpeg_path)
        ffmpeg.setPlaceholderText("Automatic PATH / Homebrew lookup")
        form.addRow(model)
        form.addRow("Model coverage", stride)
        form.addRow("Device", device)
        form.addRow(normalized)
        form.addRow("FFmpeg executable", ffmpeg)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self.options.model_enabled = model.isChecked()
            self.options.model_stride_seconds = [10., 30., 60.][stride.currentIndex()]
            self.options.device = device.currentText()
            self.options.model_profile = "gain-normalized" if normalized.isChecked() else "original"
            self.options.ffmpeg_path = ffmpeg.text().strip()
            self.project.set_metadata("analysis_settings", self.options.to_dict())

    def reference_dialog(self):
        if self.busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("References & personal intensity")
        dialog.resize(600, 650)
        layout = QVBoxLayout(dialog)
        text = QLabel("Choose your actual quiet and dense recordings to establish dynamics anchors at 5 and 95.\nThe corpus scale remains available separately. Weights affect intensity; positivity stays independent.")
        text.setWordWrap(True)
        layout.addWidget(text)
        form = QFormLayout()
        quiet, dense = QComboBox(), QComboBox()
        quiet.addItem("Use corpus dynamics", None)
        dense.addItem("Choose dense reference", None)
        for track in self.tracks:
            if track.status == "complete" and not track.excluded:
                quiet.addItem(track.original_name, track.id)
                dense.addItem(track.original_name, track.id)
        references = self.project.metadata("reference_ids")
        if references:
            quiet.setCurrentIndex(max(0, quiet.findData(references[0])))
            dense.setCurrentIndex(max(0, dense.findData(references[1])))
        form.addRow("Quiet dynamics reference", quiet)
        form.addRow("Dense dynamics reference", dense)
        from music_analyzer.scoring import DEFAULT_WEIGHTS
        current = self.project.metadata("intensity_weights", DEFAULT_WEIGHTS)
        weight_editors = {}
        for key in DEFAULT_WEIGHTS:
            editor = QDoubleSpinBox()
            editor.setRange(0, 100)
            editor.setValue(current[key] / sum(current.values()) * 100)
            weight_editors[key] = editor
            form.addRow(key.replace("_", " ").title() + " weight", editor)
        layout.addLayout(form)
        positivity_controls = QHBoxLayout()
        def learn_positivity():
            try:
                calibration = fit_valence_anchors(self.tracks)
                self.project.set_metadata("valence_calibration", calibration)
                self.recalculate()
                self.statusBar().showMessage("Personal positivity mapping learned from reviewed corrections", 10000)
            except ValueError as exc:
                self._show_error(str(exc))
        def reset_positivity():
            self.project.set_metadata("valence_calibration", None)
            self.recalculate()
        positivity_controls.addWidget(button("Learn positivity from corrections", learn_positivity))
        positivity_controls.addWidget(button("Reset positivity mapping", reset_positivity))
        layout.addLayout(positivity_controls)
        pairs = self.project.metadata("intensity_pairs", [])
        pair_form = QFormLayout()
        higher, lower = QComboBox(), QComboBox()
        for track in self.tracks:
            if not track.excluded and track.id in self.scores:
                higher.addItem(track.original_name, track.id)
                lower.addItem(track.original_name, track.id)
        if lower.count() > 1:
            lower.setCurrentIndex(1)
        pair_form.addRow("A feels more intense", higher)
        pair_form.addRow("than B", lower)
        layout.addLayout(pair_form)
        pair_note = QLabel(f"{len(pairs)} recorded intensity comparisons")
        layout.addWidget(pair_note)
        pair_controls = QHBoxLayout()
        def add_pair():
            if higher.currentData() and lower.currentData() and higher.currentData() != lower.currentData():
                pairs.append({"higher": higher.currentData(), "lower": lower.currentData()})
                self.project.set_metadata("intensity_pairs", pairs)
                pair_note.setText(f"{len(pairs)} recorded intensity comparisons")
        def fit_pairs():
            try:
                fitted = fit_intensity_pairs(self.scores, pairs)
                for key, value in fitted["weights"].items():
                    weight_editors[key].setValue(value * 100)
                pair_note.setText(f"{fitted['pairs_used']} fitting pairs · agreement {fitted['training_pair_agreement']:.0%} (personal fit, not held-out accuracy)")
            except ValueError as exc:
                self._show_error(str(exc))
        pair_controls.addWidget(button("Add A > B comparison", add_pair))
        pair_controls.addWidget(button("Fit weights from comparisons", fit_pairs))
        layout.addLayout(pair_controls)
        preset_name = QLineEdit()
        preset_name.setPlaceholderText("Personal preset name")
        layout.addWidget(preset_name)
        preset_controls = QHBoxLayout()
        def preset():
            return {"weights": {key: editor.value() / 100 for key, editor in weight_editors.items()},
                    "valence_calibration": self.project.metadata("valence_calibration"), "name": preset_name.text().strip() or "Personal"}
        def save_preset():
            path, _ = QFileDialog.getSaveFileName(dialog, "Save personal preset", "music-intensity-preset.json", "JSON (*.json)")
            if path:
                Path(path).write_text(json.dumps(preset(), indent=2), encoding="utf-8")
        def load_preset():
            from music_analyzer.scoring import validate_weights
            path, _ = QFileDialog.getOpenFileName(dialog, "Load personal preset", "", "JSON (*.json)")
            if not path:
                return
            try:
                loaded = json.loads(Path(path).read_text(encoding="utf-8"))
                validate_weights(loaded["weights"])
                for key, value in loaded["weights"].items():
                    weight_editors[key].setValue(value / sum(loaded["weights"].values()) * 100)
                self.project.set_metadata("valence_calibration", loaded.get("valence_calibration"))
                preset_name.setText(loaded.get("name", "Personal"))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._show_error(str(exc))
        preset_controls.addWidget(button("Save preset…", save_preset))
        preset_controls.addWidget(button("Load preset…", load_preset))
        layout.addLayout(preset_controls)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec():
            references = [quiet.currentData(), dense.currentData()] if quiet.currentData() else None
            try:
                values = preset()
                make_snapshot(self.tracks, weights=values["weights"], reference_ids=references)
                self.project.set_metadata("reference_ids", references)
                self.project.set_metadata("intensity_weights", values["weights"])
                self.project.set_metadata("preset_name", values["name"])
                self.recalculate()
            except ValueError as exc:
                self._show_error(str(exc))

    def relocate_file(self):
        track = self.selected_track()
        if not track or self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Locate the original recording")
        if path:
            try:
                self.project.relocate(track, path)
                self.refresh()
            except (ValueError, OSError) as exc:
                self._show_error(str(exc))

    def _switch_project(self, path):
        if self.busy:
            return
        try:
            project = Project(path)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._show_error(str(exc))
            return
        self.player.stop()
        self.project.close()
        self.project = project
        self.runner = BatchRunner(project)
        self.snapshot = project.metadata("snapshot")
        self.album = project.metadata("album")
        self.pins = project.metadata("pins", {})
        self.options = AnalysisSettings(**project.metadata("analysis_settings", {}))
        self.model_directory = Path(project.metadata("model_directory", str(default_model_directory())))
        self.selected_id = None
        self.profile.setCurrentIndex(1 if self.snapshot and self.snapshot["profile"] == "simple" else 0)
        self.order_mode.setCurrentIndex(project.metadata("order_mode", 0))
        self.refresh()

    def new_project(self):
        if self.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "New project", "Untitled.ma-project", "Music Analyzer project (*.ma-project)")
        if path:
            if Path(path).exists():
                self._show_error("Choose a new filename. Open project loads an existing project.")
            else:
                self._switch_project(path)

    def open_project(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Music Analyzer project (*.ma-project)")
        if path:
            self._switch_project(path)

    def save_as(self):
        if self.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save project as", "Album.ma-project", "Music Analyzer project (*.ma-project)")
        if path:
            if Path(path).exists():
                self._show_error("Choose a new filename to preserve the existing project.")
                return
            with sqlite3.connect(path) as destination:
                self.project.connection.backup(destination)
            self._switch_project(path)

    def export_album(self):
        if self.busy:
            return
        if not self.album or not self.snapshot or self.album.get("snapshot_id") != self.snapshot["id"] or self.album.get("fingerprint") != fingerprint(self.tracks):
            self._show_error("Build an order from the current scores before exporting.")
            return
        project_id = self.project.metadata("project_id") or uuid.uuid4().hex
        self.project.set_metadata("project_id", project_id)
        previous = self.project.metadata("last_export")
        try:
            old = load_journal(previous) if previous and Path(previous).exists() else None
            if old and old["phase"] not in {"complete", "undone"}:
                raise ValueError("Resume or undo the unfinished export using the Tools menu first.")
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Preview numbered album export")
        dialog.resize(950, 650)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Two valence folders retain global album positions. Open album.m3u8 for the combined playing order."))
        form = QFormLayout()
        layout.addLayout(form)
        mode = QComboBox()
        mode.addItems(["Export Copies", "Organize originals (move after verification)"])
        form.addRow("Action", mode)
        parents = {str(Path(t.path).parent) for t in self.tracks if not t.excluded}
        default_root = old["root"] if old else next(iter(parents)) if len(parents) == 1 else str(self.project.path.parent)
        destination = QLineEdit(default_root)
        folder_row = QHBoxLayout()
        folder_row.addWidget(destination)

        def browse():
            chosen = QFileDialog.getExistingDirectory(dialog, "Choose the album output folder", destination.text())
            if chosen:
                destination.setText(chosen)

        folder_row.addWidget(button("Choose folder…", browse))
        form.addRow("Folder", folder_row)
        padded = QCheckBox("Pad numbers for alphabetical sorting (001_ through 200_)")
        padded.setChecked(True)
        form.addRow(padded)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setAccessibleName("Original to export filename preview")
        layout.addWidget(preview)
        note = QLabel()
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        current = {}

        def update_preview(*_):
            current.clear()
            try:
                root = Path(destination.text()).expanduser().resolve()
                prior = previous if old and old["phase"] == "complete" and root == Path(old["root"]) else None
                plan = make_export_plan(self.tracks, self.scores, self.album, self.snapshot, root, project_id,
                                        move=bool(mode.currentIndex()), padded=padded.isChecked(), previous_journal=prior)
                current["plan"] = plan
                names = {t.id: t.original_name for t in self.tracks}
                preview.setPlainText("\n".join(f"{names[e['track_id']]}  →  {e['relative']}" for e in plan["files"] if e["kind"] == "audio"))
                details = [f"{len(self.album['order'])} recordings · {sum(t.excluded for t in self.tracks)} excluded · source audio bytes preserved."]
                details.extend(plan["warnings"])
                if plan["move"]:
                    details.append("Originals are removed only after every output is published and verified. Undo restores original names and locations.")
                note.setText("\n".join(details))
                buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Organize originals" if plan["move"] else "Export copies")
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
            except (OSError, ValueError) as exc:
                preview.setPlainText(str(exc))
                note.setText("Resolve this conflict before exporting.")
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        destination.textChanged.connect(update_preview)
        mode.currentIndexChanged.connect(update_preview)
        padded.toggled.connect(update_preview)
        update_preview()
        if dialog.exec() == QDialog.DialogCode.Accepted and "plan" in current:
            try:
                path = create_journal(current["plan"])
                self.project.set_metadata("last_export", str(path))
                self.player.stop()
                self._start_task(lambda task: execute_export(path, task.cancel_event, task.progress.emit), self._export_finished)
            except (OSError, ValueError) as exc:
                self._show_error(str(exc))

    def _export_finished(self, journal):
        tracks = {track.id: track for track in self.project.tracks()}
        for entry in journal["files"]:
            if entry["kind"] != "audio" or entry["track_id"] not in tracks:
                continue
            track = tracks[entry["track_id"]]
            if journal["phase"] == "undone":
                path = Path(entry["source"])
            elif journal["move"] and (entry["source_removed"] or entry["source"] == str(Path(journal["root"]) / entry["relative"])):
                path = Path(journal["root"]) / entry["relative"]
            else:
                continue
            if path.is_file():
                stat = path.stat()
                track.path, track.size, track.mtime_ns = str(path), stat.st_size, stat.st_mtime_ns
                self.project.save_track(track)
        if journal["phase"] == "undone":
            self.project.set_metadata("last_export", journal.get("previous_journal"))
        self.refresh()
        if journal["phase"] == "paused":
            QMessageBox.information(self, "Export paused", "Progress is saved. Use Tools → Resume export or Undo export to continue.")
        else:
            QMessageBox.information(self, "Export", "Originals restored." if journal["phase"] == "undone" else f"Export complete. Open album.m3u8 in:\n{journal['root']}")

    def _journal_action(self, undo=False):
        if self.busy:
            return
        path = self.project.metadata("last_export")
        if not path or not Path(path).exists():
            path, _ = QFileDialog.getOpenFileName(self, "Choose an export journal", "", "Export journal (*.journal.json)")
        if not path:
            return
        try:
            journal = load_journal(path)
            if journal["project_id"] != self.project.metadata("project_id"):
                raise ValueError("Open the project that created this export before recovering or undoing it.")
            verb = "Undo" if undo else "Resume"
            count = sum(e["kind"] == "audio" for e in journal["files"])
            details = f"{verb} the {count}-recording export in:\n{journal['root']}\n\n"
            details += "Undo restores moved originals and previous managed exports. Changed or unrelated files are preserved." if undo else "Completed operations are checked and remaining operations continue from the saved journal."
            if QMessageBox.question(self, f"{verb} export", details) != QMessageBox.StandardButton.Yes:
                return
            self.project.set_metadata("last_export", str(path))
            self.player.stop()
            operation = undo_files if undo else execute_export
            self._start_task(lambda task: operation(path, task.cancel_event, task.progress.emit), self._export_finished)
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))

    def recover_export(self):
        self._journal_action()

    def undo_export(self):
        self._journal_action(undo=True)

    def _show_error(self, message):
        QMessageBox.warning(self, "Music Analyzer", message)

    def closeEvent(self, event):
        if self.busy:
            self.closing = True
            self.cancel_work()
            event.ignore()
            return
        self.timer.stop()
        self.runner.shutdown()
        self.player.stop()
        self.project.close()
        event.accept()
