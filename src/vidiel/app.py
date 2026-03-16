from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from vidiel.ui.main_window import MainWindow, build_stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ViDieL")
    app.setStyleSheet(build_stylesheet())

    window = MainWindow()
    window.show()
    return app.exec()
