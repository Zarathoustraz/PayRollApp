# -*- coding: utf-8 -*-
"""
management_pdf_generator.py — internal "Résumé de Gestion" PDF (Roger's
Theorem breakdown), for project managers pricing client billing rates.

Deliberately a SEPARATE PDF file from the employee's payslip, not a page
appended to it. The spec described it as "attached after the payslip...
strictly for internal use, not to be handed to the employee" — but a
multi-page PDF relies on someone remembering to strip the internal page
before every print/forward/email to that employee, forever. A separate
file with its own unmistakable filename and a confidentiality banner on
every page removes that failure mode entirely rather than depending on
nobody ever making a mistake with it. Generated from the same "GÉNÉRER"
action in the Facturation tab, so nothing extra to remember day to day —
it's just never the same file as the one that goes to the employee.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from . import palette as pal
from .config import CompanyInfo
from .formatting import format_mad, format_number, format_period_fr
from .models import BillingResult, Employee

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm


def _hc(hex_str: str) -> colors.Color:
    return colors.HexColor(hex_str)


class ManagementSummaryPDFGenerator:
    def __init__(self, company: CompanyInfo):
        self.company = company

    def generate(self, employee: Employee, result: BillingResult, output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(output_path), pagesize=A4)

        y = self._draw_header(c, employee, result)
        y = self._draw_confidential_banner(c, y)
        y = self._draw_inputs_block(c, result, y)
        y = self._draw_kpi_blocks(c, result, y)
        y = self._draw_methodology_note(c, y)
        self._draw_confidential_banner(c, MARGIN + 10 * mm, footer=True)

        c.showPage()
        c.save()
        return output_path

    def _draw_header(self, c: canvas.Canvas, employee: Employee, result: BillingResult) -> float:
        band_h = 24 * mm
        c.setFillColor(_hc(pal.NAVY_DARK))
        c.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)
        c.setFillColor(_hc(pal.WHITE))
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN, PAGE_H - 10 * mm, "RÉSUMÉ DE GESTION — RENTABILITÉ & FACTURATION")
        c.setFont("Helvetica", 8.5)
        c.drawString(MARGIN, PAGE_H - 16 * mm, f'{self.company.name} — méthode dite "Théorème de Roger"')

        c.setFont("Helvetica-Bold", 10)
        period = format_period_fr(result.inputs.period_month, result.inputs.period_year)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 10 * mm, employee.full_name)
        c.setFont("Helvetica", 9)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 16 * mm, period)
        return PAGE_H - band_h - 6 * mm

    def _draw_confidential_banner(self, c: canvas.Canvas, y: float, footer: bool = False) -> float:
        h = 9 * mm
        c.setFillColor(_hc(pal.DANGER))
        c.rect(MARGIN, y - h, PAGE_W - 2 * MARGIN, h, stroke=0, fill=1)
        c.setFillColor(_hc(pal.WHITE))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(PAGE_W / 2, y - h + 2.8 * mm,
                              "CONFIDENTIEL — USAGE INTERNE UNIQUEMENT — NE PAS REMETTRE AU SALARIÉ")
        return y - h - 6 * mm

    def _draw_inputs_block(self, c: canvas.Canvas, result: BillingResult, y: float) -> float:
        i = result.inputs
        rows = [
            ("Coût employeur mensuel (base)", format_mad(i.monthly_employer_cost)),
            ("Congés payés annuels", f"{format_number(i.conges_payes_jours, 1)} jours"),
            ("Jours fériés chômés payés annuels", f"{format_number(i.jours_feries, 1)} jours"),
            ("Heures par jour travaillé", f"{format_number(i.heures_par_jour, 2)} h"),
            ("Heures théoriques annuelles", f"{format_number(i.heures_theoriques_annuelles, 1)} h"),
        ]
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(_hc(pal.SLATE))
        c.drawString(MARGIN, y, "PARAMÈTRES UTILISÉS")
        y -= 5 * mm
        table = Table([[lbl, val] for lbl, val in rows], colWidths=[95 * mm, 60 * mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), _hc(pal.TEXT_MUTED)),
            ("TEXTCOLOR", (1, 0), (1, -1), _hc(pal.TEXT_DARK)),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        w, h = table.wrapOn(c, PAGE_W - 2 * MARGIN, y)
        table.drawOn(c, MARGIN, y - h)
        return y - h - 8 * mm

    def _draw_kpi_blocks(self, c: canvas.Canvas, result: BillingResult, y: float) -> float:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(_hc(pal.SLATE))
        c.drawString(MARGIN, y, "INDICATEURS DE RENTABILITÉ")
        y -= 8 * mm

        card_w = (PAGE_W - 2 * MARGIN - 8 * mm) / 2
        card_h = 22 * mm

        def kpi_card(x, y_top, label, value, emphasis=False):
            c.setFillColor(_hc(pal.SLATE_LIGHT) if not emphasis else _hc(pal.NAVY))
            c.roundRect(x, y_top - card_h, card_w, card_h, 2 * mm, stroke=0, fill=1)
            c.setFillColor(_hc(pal.TEXT_MUTED) if not emphasis else _hc(pal.WHITE))
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 5 * mm, y_top - 7 * mm, label.upper())
            c.setFillColor(_hc(pal.NAVY_DARK) if not emphasis else _hc(pal.WHITE))
            c.setFont("Helvetica-Bold", 16)
            c.drawString(x + 5 * mm, y_top - 16 * mm, value)

        kpi_card(MARGIN, y, "Coût horaire théorique (naïf)", format_mad(result.theoretical_hourly_cost) + " / h")
        kpi_card(MARGIN + card_w + 8 * mm, y, "Heures productives réelles / an",
                  f"{format_number(result.actual_productive_hours, 1)} h")
        y -= card_h + 6 * mm
        kpi_card(MARGIN, y, "Coût horaire productif réel (plancher)",
                  format_mad(result.real_productive_hourly_cost) + " / h", emphasis=True)
        kpi_card(MARGIN + card_w + 8 * mm, y, "Majoration plancher recommandée",
                  f"+{result.markup_pct:.1%}", emphasis=True)
        return y - card_h - 8 * mm

    def _draw_methodology_note(self, c: canvas.Canvas, y: float) -> float:
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(_hc(pal.TEXT_MUTED))
        lines = [
            "Méthode : coût annuel total = coût employeur mensuel x 12. Heures non-productives = (congés",
            "payés + jours fériés) x heures/jour, payées mais non facturables. Heures productives réelles =",
            "heures théoriques annuelles - heures non-productives. Coût horaire réel = coût annuel total / heures",
            "productives réelles. La majoration plancher est le taux minimal à appliquer sur les heures",
            "effectivement facturées au client pour recouvrer le coût réel — hors marge commerciale, non incluse ici.",
        ]
        for line in lines:
            c.drawString(MARGIN, y, line)
            y -= 3.6 * mm
        return y - 4 * mm
