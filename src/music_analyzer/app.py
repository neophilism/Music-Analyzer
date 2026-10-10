"""Desktop entry point. Safe for spawned workers and frozen applications."""

import argparse
import multiprocessing
import sys
import tempfile
from pathlib import Path

from platformdirs import user_data_dir
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from music_analyzer.window import MainWindow


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Music Analyzer desktop")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--smoke", action="store_true", help="Launch and exit for package verification")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("Music Analyzer")
    app.setApplicationName("Music Analyzer")
    temporary = tempfile.TemporaryDirectory(prefix="music-analyzer-smoke-") if args.smoke else None
    project = args.project or (str(Path(temporary.name) / "Smoke.ma-project") if temporary else
                               str(Path(user_data_dir("MusicAnalyzer", "MusicAnalyzer")) / "Projects" / "Untitled.ma-project"))
    try:
        window = MainWindow(project)
        window.show()
        if args.smoke:
            QTimer.singleShot(150, window.close)
        result = app.exec()
    finally:
        if temporary:
            temporary.cleanup()
    return result
