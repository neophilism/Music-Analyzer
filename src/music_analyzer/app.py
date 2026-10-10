"""Desktop entry point. Safe for spawned workers and frozen applications."""

import argparse
import json
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
    parser.add_argument("--verify-package", action="store_true", help="Verify GUI, spawned analysis, persistence, and export")
    parser.add_argument("--model-directory", type=Path, help="Use an installed model during package verification")
    parser.add_argument("--verification-report", type=Path, help="Write package verification results as JSON")
    parser.add_argument("--install-model", type=Path, help="Explicitly install the pinned model pack into this directory")
    args = parser.parse_args(argv)
    if args.install_model:
        from music_analyzer.models import install_model

        install_model(args.install_model)
        return 0
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("Music Analyzer")
    app.setApplicationName("Music Analyzer")
    if args.verify_package:
        from music_analyzer.package_check import verify_package

        report = verify_package(app, args.model_directory)
        if args.verification_report:
            args.verification_report.parent.mkdir(parents=True, exist_ok=True)
            args.verification_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
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
