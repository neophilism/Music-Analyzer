"""Desktop entry point. Safe for spawned workers and frozen applications."""

import argparse
import multiprocessing
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Music Analyzer desktop")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--smoke", action="store_true", help="Launch and exit for package verification")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("Music Analyzer")
    app.setApplicationName("Music Analyzer")
    window = QMainWindow()
    window.setWindowTitle("Music Analyzer")
    window.resize(1280, 820)
    window.setCentralWidget(QLabel("Music Analyzer · local instrumental workspace"))
    window.show()
    if args.smoke:
        QTimer.singleShot(150, app.quit)
    return app.exec()
