#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — entry point. Kept at the repository root (rather than inside
app/) so the PyInstaller spec has one unambiguous script to analyse.
"""
import sys

from PyQt6.QtWidgets import QApplication

from app.gui.main_window import MainWindow
from app.gui.styles import APP_QSS


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # neutral base so the QSS palette isn't fighting a themed native style
    app.setStyleSheet(APP_QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
