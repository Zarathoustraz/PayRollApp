# -*- coding: utf-8 -*-
"""gui/widgets.py — small reusable pieces shared across tabs."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..formatting import format_mad


class HLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("hline")
        self.setFrameShape(QFrame.Shape.HLine)


class SectionTitle(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("sectionTitle")


class KpiCard(QFrame):
    """Small metric card: big value on top, muted caption below."""

    def __init__(self, label: str, value: str = "—"):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName("kpiValue")
        caption = QLabel(label.upper())
        caption.setObjectName("kpiLabel")
        layout.addWidget(self._value_lbl)
        layout.addWidget(caption)

    def set_value(self, value: str) -> None:
        self._value_lbl.setText(value)


class WarningBanner(QLabel):
    """Hidden by default; call set_message(None) to hide, or a string to show."""

    def __init__(self):
        super().__init__()
        self.setObjectName("warningBanner")
        self.setWordWrap(True)
        self.hide()

    def set_message(self, message: str | None) -> None:
        if message:
            self.setText(f"⚠ {message}")
            self.show()
        else:
            self.hide()


class NetPayCard(QFrame):
    """The prominent navy 'NET À PAYER' card echoing the PDF's own box."""

    def __init__(self):
        super().__init__()
        self.setObjectName("netPayCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        caption = QLabel("NET À PAYER")
        caption.setStyleSheet("color: white; font-size: 13px; font-weight: 700;")
        self._value = QLabel("—")
        self._value.setObjectName("netPayValue")
        layout.addWidget(caption)
        layout.addStretch()
        layout.addWidget(self._value)

    def set_amount(self, amount: float) -> None:
        self._value.setText(format_mad(amount))


class FieldLabel(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("fieldLabel")
