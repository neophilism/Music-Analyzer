"""Small native table, background task, and plots used by the desktop window."""

import math
import threading

from PySide6.QtCore import QAbstractTableModel, QPointF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from music_analyzer.scoring import finite


class TaskThread(QThread):
    progress = Signal(float, str)
    item = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function
        self.cancel_event = threading.Event()

    def run(self):
        try:
            result = self.function(self)
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class TrackTable(QAbstractTableModel):
    changed = Signal(object)
    HEADERS = ["Use", "Track", "Status", "Intensity", "Dynamics", "Tempo /100", "BPM", "Positivity", "Mood", "Mode", "Genres"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks, self.scores = [], {}

    def replace(self, tracks, scores):
        self.beginResetModel()
        self.tracks, self.scores = tracks, scores
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.tracks)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def values(self, track):
        score = self.scores.get(track.id, {})
        status = "Excluded" if track.excluded else "Needs review" if track.status == "complete" and score.get("needs_review", True) else track.status.title()
        return [not track.excluded, track.original_name, status, score.get("intensity"), score.get("dynamics"),
                score.get("tempo"), track.value("bpm"), score.get("valence"), track.value("mood", "—"),
                track.value("mode", "—"), ", ".join(track.value("genres", []))]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        track = self.tracks[index.row()]
        value = self.values(track)[index.column()]
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Unchecked if track.excluded else Qt.CheckState.Checked
        if role == Qt.ItemDataRole.UserRole:
            return value if value is not None else -1 if 3 <= index.column() <= 7 else ""
        if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole}:
            if index.column() == 0:
                return ""
            return f"{value:.1f}" if finite(value) else "—" if value is None else str(value)
        if role == Qt.ItemDataRole.ForegroundRole:
            if track.excluded:
                return QColor("#82909f")
            if index.column() == 2 and (track.status == "error" or self.scores.get(track.id, {}).get("needs_review")):
                return QColor("#d98b27")
        if role == Qt.ItemDataRole.ToolTipRole:
            return track.error or "\n".join(track.analysis.get("review_reasons", [])) or track.path
        if role == Qt.ItemDataRole.TextAlignmentRole and 3 <= index.column() <= 7:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsUserCheckable if index.column() == 0 else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.isValid() and index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            track = self.tracks[index.row()]
            track.excluded = value not in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
            self.changed.emit(track)
            self.dataChanged.emit(index, index)
            return True
        return False


class CurvePlot(QWidget):
    seek = Signal(float)

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title, self.points = title, []
        self.color = QColor("#6f9bf5")
        self.setMinimumHeight(130)
        self.setAccessibleName(title)
        self.setToolTip("Click the waveform to seek during playback")

    def set_points(self, points, title=None):
        self.points = [(float(x), float(y)) for x, y in points if finite(x) and finite(y)]
        if title is not None:
            self.title = title
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        painter.drawText(12, 20, self.title)
        left, right, top, bottom = 48, self.width() - 16, 34, self.height() - 25
        grid = QColor(self.palette().text().color())
        grid.setAlpha(35)
        painter.setPen(QPen(grid, 1))
        for fraction in (0., .5, 1.):
            y = bottom - fraction * (bottom - top)
            painter.drawLine(QPointF(left, y), QPointF(right, y))
        if not self.points:
            painter.setPen(self.palette().text().color())
            painter.drawText(left, (top + bottom) // 2, "Available after analysis")
            return
        xs, ys = zip(*self.points, strict=True)
        self.x_min, self.x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        if abs(y_max - y_min) < .001:
            y_min -= 1
            y_max += 1
        padding = .08 * (y_max - y_min)
        y_min, y_max = y_min - padding, y_max + padding
        path = QPainterPath()
        for index, (x, y) in enumerate(self.points):
            point = QPointF(left + (x - self.x_min) / max(self.x_max - self.x_min, 1e-9) * (right - left),
                            bottom - (y - y_min) / (y_max - y_min) * (bottom - top))
            if index:
                path.lineTo(point)
            else:
                path.moveTo(point)
        painter.setPen(QPen(self.color, 1.7))
        painter.drawPath(path)
        painter.setPen(self.palette().text().color())
        painter.drawText(4, top + 5, f"{y_max:.0f}")
        painter.drawText(4, bottom, f"{y_min:.0f}")
        painter.drawText(left, self.height() - 7, f"{self.x_min:.0f}")
        painter.drawText(right - 36, self.height() - 7, f"{self.x_max:.0f}")

    def mousePressEvent(self, event):
        if self.points and event.button() == Qt.MouseButton.LeftButton:
            fraction = min(1, max(0, (event.position().x() - 48) / max(1, self.width() - 64)))
            self.seek.emit(self.x_min + fraction * (self.x_max - self.x_min))


class ScatterPlot(QWidget):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points, self.selected_id, self.locations = [], None, []
        self.setMinimumHeight(200)
        self.setAccessibleName("Tracks by intensity and positivity")

    def set_tracks(self, tracks, scores, selected_id=None):
        self.points = [(t.id, t.original_name, scores[t.id]["intensity"], scores[t.id]["valence"])
                       for t in tracks if not t.excluded and t.id in scores and finite(scores[t.id].get("intensity")) and finite(scores[t.id].get("valence"))]
        self.selected_id = selected_id
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        left, right, top, bottom = 50, self.width() - 20, 30, self.height() - 36
        painter.setPen(self.palette().text().color())
        painter.drawText(12, 18, "Emotion & intensity")
        grid = QColor(self.palette().text().color())
        grid.setAlpha(50)
        painter.setPen(QPen(grid, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(left, (top + bottom) / 2), QPointF(right, (top + bottom) / 2))
        self.locations = []
        for tid, name, intensity, valence in self.points:
            x, y = left + intensity / 100 * (right - left), bottom - valence / 100 * (bottom - top)
            color = QColor("#43b7a2" if valence >= 50 else "#a58bec")
            painter.setBrush(color)
            painter.setPen(QPen(self.palette().text().color(), 2) if tid == self.selected_id else Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), 6 if tid == self.selected_id else 4, 6 if tid == self.selected_id else 4)
            self.locations.append((tid, name, x, y))
        painter.setPen(self.palette().text().color())
        painter.drawText(left, self.height() - 10, "Intensity  0 → 100")
        painter.drawText(6, top + 10, "+100")
        painter.drawText(6, bottom, "0")
        painter.drawText(right - 72, (top + bottom) // 2 - 5, "neutral 50")

    def mousePressEvent(self, event):
        if not self.locations:
            return
        position = event.position()
        tid, _, x, y = min(self.locations, key=lambda row: math.hypot(row[2] - position.x(), row[3] - position.y()))
        if math.hypot(x - position.x(), y - position.y()) < 12:
            self.selected.emit(tid)
