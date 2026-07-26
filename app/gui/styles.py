# -*- coding: utf-8 -*-
"""
styles.py — QSS for the whole app. One stylesheet, applied once at
QApplication level, built from the shared palette in app/palette.py so the
screen and the printed payslip never drift apart.
"""
from .. import palette as pal

FONT_FAMILY = "'Segoe UI', 'Segoe UI Semibold', Arial, sans-serif"

APP_QSS = f"""
* {{
    font-family: {FONT_FAMILY};
}}

QMainWindow, QDialog, QWidget#root {{
    background-color: {pal.OFF_WHITE};
}}

QWidget {{
    color: {pal.TEXT_DARK};
    font-size: 13px;
}}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {pal.BORDER};
    background: {pal.WHITE};
    border-radius: 4px;
    top: -1px;
}}
QTabBar::tab {{
    background: {pal.OFF_WHITE};
    color: {pal.SLATE};
    border: 1px solid {pal.BORDER};
    border-bottom: none;
    padding: 9px 22px;
    font-weight: 600;
    font-size: 13px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background: {pal.WHITE};
    color: {pal.NAVY_DARK};
    border-bottom: 2px solid {pal.NAVY};
}}
QTabBar::tab:hover:!selected {{
    color: {pal.NAVY};
    background: {pal.SLATE_LIGHT};
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {pal.WHITE};
    color: {pal.NAVY_DARK};
    border: 1px solid {pal.BORDER};
    border-radius: 4px;
    padding: 7px 16px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {pal.SLATE_LIGHT};
    border-color: {pal.STEEL};
}}
QPushButton:pressed {{
    background-color: {pal.BORDER};
}}
QPushButton:disabled {{
    color: {pal.TEXT_MUTED};
    background-color: {pal.OFF_WHITE};
}}

QPushButton#primary {{
    background-color: {pal.NAVY};
    color: {pal.WHITE};
    border: 1px solid {pal.NAVY};
    padding: 9px 20px;
    font-size: 14px;
}}
QPushButton#primary:hover {{
    background-color: {pal.STEEL};
    border-color: {pal.STEEL};
}}
QPushButton#primary:pressed {{
    background-color: {pal.NAVY_DARK};
}}
QPushButton#primary:disabled {{
    background-color: {pal.BORDER};
    border-color: {pal.BORDER};
    color: {pal.TEXT_MUTED};
}}

QPushButton#danger {{
    color: {pal.DANGER};
    border-color: {pal.DANGER};
}}
QPushButton#danger:hover {{
    background-color: #F7EAE6;
}}

QPushButton#flat {{
    border: none;
    background: transparent;
    color: {pal.SLATE};
    font-weight: 500;
    padding: 4px 8px;
}}
QPushButton#flat:hover {{
    color: {pal.NAVY};
    text-decoration: underline;
}}

/* ---------- Inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: {pal.WHITE};
    border: 1px solid {pal.BORDER};
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: {pal.STEEL};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 1.5px solid {pal.NAVY};
}}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {{
    background: {pal.OFF_WHITE};
    color: {pal.TEXT_MUTED};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {pal.WHITE};
    border: 1px solid {pal.BORDER};
    selection-background-color: {pal.SLATE_LIGHT};
    selection-color: {pal.NAVY_DARK};
    outline: none;
}}

/* ---------- Labels ---------- */
QLabel#sectionTitle {{
    color: {pal.NAVY_DARK};
    font-size: 15px;
    font-weight: 700;
    padding-bottom: 2px;
}}
QLabel#fieldLabel {{
    color: {pal.SLATE};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#kpiValue {{
    color: {pal.NAVY_DARK};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#kpiLabel {{
    color: {pal.TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}}
QLabel#netPayValue {{
    color: {pal.WHITE};
    font-size: 26px;
    font-weight: 700;
}}
QLabel#warningBanner {{
    background-color: #FBEDE7;
    color: {pal.DANGER};
    border: 1px solid {pal.DANGER};
    border-radius: 4px;
    padding: 8px 12px;
    font-weight: 600;
}}

/* ---------- Containers ---------- */
QFrame#card {{
    background: {pal.WHITE};
    border: 1px solid {pal.BORDER};
    border-radius: 6px;
}}
QFrame#netPayCard {{
    background-color: {pal.NAVY};
    border-radius: 6px;
}}
QFrame#sidebar {{
    background: {pal.WHITE};
    border-left: 1px solid {pal.BORDER};
}}
QFrame#hline {{
    background-color: {pal.BORDER};
    max-height: 1px;
    min-height: 1px;
}}

/* ---------- Table ---------- */
QTableView {{
    background: {pal.WHITE};
    alternate-background-color: {pal.OFF_WHITE};
    gridline-color: {pal.BORDER};
    border: 1px solid {pal.BORDER};
    border-radius: 4px;
    selection-background-color: {pal.SLATE_LIGHT};
    selection-color: {pal.NAVY_DARK};
}}
QHeaderView::section {{
    background-color: {pal.NAVY_DARK};
    color: {pal.WHITE};
    padding: 7px;
    border: none;
    font-weight: 600;
    font-size: 12px;
}}
QTableView::item {{
    padding: 5px;
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {pal.BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {pal.SLATE};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

QStatusBar {{
    background: {pal.NAVY_DARK};
    color: {pal.WHITE};
}}

QMenuBar {{
    background: {pal.WHITE};
    border-bottom: 1px solid {pal.BORDER};
}}
QMenuBar::item:selected {{
    background: {pal.SLATE_LIGHT};
}}
QMenu {{
    background: {pal.WHITE};
    border: 1px solid {pal.BORDER};
}}
QMenu::item:selected {{
    background: {pal.SLATE_LIGHT};
    color: {pal.NAVY_DARK};
}}

QToolTip {{
    background: {pal.NAVY_DARK};
    color: {pal.WHITE};
    border: none;
    padding: 4px 8px;
}}
"""
