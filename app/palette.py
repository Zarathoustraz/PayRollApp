# -*- coding: utf-8 -*-
"""
palette.py — the app's corporate palette, as hex strings.

Shared by gui/styles.py (QSS) and pdf_generator.py (reportlab HexColor) so
the on-screen app and the printed payslip are unmistakably the same product.
Slate grays + navy blues + crisp white, per spec — no default AI-blue.
"""

NAVY_DARK = "#0F1F3D"     # header bands, sidebar, primary text on light bg
NAVY = "#1E3A5F"          # primary buttons, active tab, links
STEEL = "#3D6690"         # hover states, secondary accents
SLATE = "#5B6B82"         # secondary text, muted labels
SLATE_LIGHT = "#E7EAF0"   # table alt-row, panel fills
BORDER = "#D3D9E2"        # hairlines, input borders
WHITE = "#FFFFFF"
OFF_WHITE = "#F6F7FA"     # app background
TEXT_DARK = "#1C2530"     # primary body text
TEXT_MUTED = "#6B7688"
SUCCESS = "#2E7D5B"       # muted green — confirmations only, used sparingly
DANGER = "#B3432B"        # muted terracotta-red — warnings/delete, not alarm-red
