# -*- coding: utf-8 -*-
"""formatting.py — shared French-locale display helpers (GUI + PDF)."""
from __future__ import annotations

MONTHS_FR = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def format_mad(amount: float, decimals: int = 2) -> str:
    """4775.0 -> '4 775,00 MAD' (French grouping/decimal convention)."""
    s = f"{amount:,.{decimals}f}"
    s = s.replace(",", "\x00").replace(".", ",").replace("\x00", " ")
    return f"{s} MAD"


def format_number(amount: float, decimals: int = 2) -> str:
    s = f"{amount:,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", " ")


def format_period_fr(month: int, year: int) -> str:
    return f"{MONTHS_FR[month]} {year}"


def format_seniority_fr(years: float) -> str:
    whole_years = int(years)
    months = round((years - whole_years) * 12)
    if months == 12:
        whole_years += 1
        months = 0
    if whole_years == 0 and months == 0:
        return "moins d'un mois"
    parts = []
    if whole_years:
        parts.append(f"{whole_years} an{'s' if whole_years > 1 else ''}")
    if months:
        parts.append(f"{months} mois")
    return " et ".join(parts)
