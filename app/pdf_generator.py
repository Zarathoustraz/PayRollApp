# -*- coding: utf-8 -*-
"""
pdf_generator.py — renders a PayrollResult as a professional Moroccan
"bulletin de paie" PDF, with an encrypted, scannable QR authenticity stamp.

Built directly on reportlab's canvas (not Platypus flowables) so every
element's position is exact and reproducible — appropriate for a document
that's meant to be verifiable. Uses the built-in Helvetica family only:
no font embedding, so the PDF renders identically wherever it's opened,
including on the GitHub Actions build runner which has no "Segoe UI".
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from . import palette as pal
from .config import CompanyInfo
from .crypto_utils import PayslipQRCodec
from .formatting import format_mad, format_period_fr, format_seniority_fr
from .models import Employee, PayrollResult

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm


def _hc(hex_str: str) -> colors.Color:
    return colors.HexColor(hex_str)


class PayslipPDFGenerator:
    def __init__(self, company: CompanyInfo, qr_codec: PayslipQRCodec):
        self.company = company
        self.qr_codec = qr_codec

    def generate(self, employee: Employee, result: PayrollResult, output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(output_path), pagesize=A4)

        y = self._draw_header(c, result)
        y = self._draw_employee_block(c, employee, result, y)
        y = self._draw_gains_retenues_table(c, employee, result, y)
        y = self._draw_net_a_payer(c, result, y)
        y = self._draw_employer_cost_block(c, result, y)
        self._draw_qr_and_footer(c, employee, result, y)

        c.showPage()
        c.save()
        return output_path

    # -- sections ---------------------------------------------------------

    def _draw_header(self, c: canvas.Canvas, result: PayrollResult) -> float:
        band_h = 26 * mm
        c.setFillColor(_hc(pal.NAVY_DARK))
        c.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)

        text_x = MARGIN
        logo_path = Path(self.company.logo_path) if self.company.logo_path else None
        if logo_path and logo_path.exists():
            logo_size = 16 * mm
            logo_y = PAGE_H - band_h + (band_h - logo_size) / 2
            try:
                c.drawImage(str(logo_path), MARGIN, logo_y, width=logo_size, height=logo_size,
                             preserveAspectRatio=True, mask="auto")
                text_x = MARGIN + logo_size + 5 * mm
            except Exception:
                pass  # a corrupt/unsupported logo file must never break payslip generation

        c.setFillColor(_hc(pal.WHITE))
        c.setFont("Helvetica-Bold", 15)
        c.drawString(text_x, PAGE_H - 10 * mm, self.company.name)
        c.setFont("Helvetica", 8.5)
        c.drawString(text_x, PAGE_H - 15 * mm, self.company.activity)
        c.drawString(text_x, PAGE_H - 19.5 * mm, self.company.address)

        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 10 * mm, "BULLETIN DE PAIE")
        c.setFont("Helvetica", 10)
        period = format_period_fr(result.inputs.period_month, result.inputs.period_year)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 16 * mm, period)

        return PAGE_H - band_h - 6 * mm

    def _draw_employee_block(self, c: canvas.Canvas, employee: Employee, result: PayrollResult, y: float) -> float:
        left_rows = [
            ("Salarié(e)", employee.full_name),
            ("CIN", employee.cin or "—"),
            ("N° CNSS", employee.cnss_number or "—"),
            ("Situation familiale", employee.marital_status),
        ]
        right_rows = [
            ("Date d'embauche", employee.hire_date.strftime("%d/%m/%Y")),
            ("Ancienneté", format_seniority_fr(result.seniority_years)),
            ("Personnes à charge", str(result.inputs.dependents)),
            ("Heures travaillées", f"{result.hours_worked:g} h"),
        ]
        c.setFont("Helvetica", 9)
        row_h = 5 * mm
        col2_x = MARGIN + 34 * mm
        col3_x = PAGE_W / 2 + 6 * mm
        col4_x = col3_x + 34 * mm
        for i, ((lbl_l, val_l), (lbl_r, val_r)) in enumerate(zip(left_rows, right_rows)):
            row_y = y - i * row_h
            c.setFillColor(_hc(pal.SLATE))
            c.drawString(MARGIN, row_y, lbl_l)
            c.drawString(col3_x, row_y, lbl_r)
            c.setFillColor(_hc(pal.TEXT_DARK))
            c.setFont("Helvetica-Bold", 9)
            c.drawString(col2_x, row_y, val_l)
            c.drawString(col4_x, row_y, val_r)
            c.setFont("Helvetica", 9)

        new_y = y - len(left_rows) * row_h - 4 * mm
        c.setStrokeColor(_hc(pal.BORDER))
        c.setLineWidth(0.6)
        c.line(MARGIN, new_y + 2 * mm, PAGE_W - MARGIN, new_y + 2 * mm)
        return new_y - 2 * mm

    def _gains_lines(self, result: PayrollResult) -> list[tuple[str, float, bool]]:
        """(label, amount, is_subtotal) — Gains column, mirrors Calculateur!C12/F7/⑤."""
        lines = [("Salaire de base", result.salaire_base, False)]
        if result.prime_anciennete > 0.005:
            lines.append(("Prime d'ancienneté", result.prime_anciennete, False))
        if result.inputs.indemnite_logement > 0.005:
            lines.append(("Indemnité de logement (imposable)", result.inputs.indemnite_logement, False))
        for line in result.allowances.lines:
            if line.exonere > 0.005:
                lines.append((f"{line.label} (exonéré)", line.exonere, False))
            if line.excedent > 0.005:
                lines.append((f"{line.label} — excédent imposable", line.excedent, False))
        total = result.brut_imposable + result.allowances.total_exonere
        lines.append(("TOTAL BRUT", total, True))
        return lines

    def _retenues_lines(self, result: PayrollResult) -> list[tuple[str, float, bool]]:
        # Frais professionnels (Art. 59 CGI) is a notional abatement used only
        # to derive the IR base (RNI) — no cash is withheld for it, so unlike
        # a real bulletin de paie it never appears as a line here. It's fully
        # visible in the app's on-screen preview and stored in the DB for
        # audit; the printed slip only shows amounts actually withheld.
        lines = [
            ("CNSS salarié(e)", result.cnss_salarie, False),
            ("AMO salarié(e)", result.amo_salarie, False),
            ("Impôt sur le Revenu (IR)", result.ir_net, False),
        ]
        total_retenues = result.cnss_salarie + result.amo_salarie + result.ir_net
        lines.append(("TOTAL RETENUES", total_retenues, True))
        return lines

    def _draw_gains_retenues_table(self, c: canvas.Canvas, employee: Employee, result: PayrollResult, y: float) -> float:
        gains = self._gains_lines(result)
        retenues = self._retenues_lines(result)

        n_rows = max(len(gains), len(retenues))
        data = [["GAINS", "MONTANT", "RETENUES", "MONTANT"]]
        row_is_subtotal = [False]
        for i in range(n_rows):
            g_label, g_amt = (gains[i][0], format_mad(gains[i][1])) if i < len(gains) else ("", "")
            r_label, r_amt = (retenues[i][0], format_mad(retenues[i][1])) if i < len(retenues) else ("", "")
            data.append([g_label, g_amt, r_label, r_amt])
            is_sub = (i < len(gains) and gains[i][2]) or (i < len(retenues) and retenues[i][2])
            row_is_subtotal.append(is_sub)

        col_widths = [66 * mm, 30 * mm, 54 * mm, 30 * mm]
        table = Table(data, colWidths=col_widths, repeatRows=1)

        style = [
            ("BACKGROUND", (0, 0), (-1, 0), _hc(pal.NAVY_DARK)),
            ("TEXTCOLOR", (0, 0), (-1, 0), _hc(pal.WHITE)),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8.5),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, _hc(pal.NAVY_DARK)),
            ("LINEAFTER", (1, 0), (1, -1), 0.5, _hc(pal.BORDER)),
            ("INNERGRID", (0, 1), (-1, -1), 0.25, _hc(pal.BORDER)),
            ("BOX", (0, 0), (-1, -1), 0.75, _hc(pal.NAVY_DARK)),
        ]
        for i, is_sub in enumerate(row_is_subtotal):
            if is_sub and i > 0:
                style.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
                style.append(("BACKGROUND", (0, i), (-1, i), _hc(pal.SLATE_LIGHT)))
                style.append(("LINEABOVE", (0, i), (-1, i), 0.6, _hc(pal.NAVY)))
        table.setStyle(TableStyle(style))

        w, h = table.wrapOn(c, PAGE_W - 2 * MARGIN, y)
        table.drawOn(c, MARGIN, y - h)
        return y - h - 6 * mm

    def _draw_net_a_payer(self, c: canvas.Canvas, result: PayrollResult, y: float) -> float:
        box_h = 14 * mm
        c.setFillColor(_hc(pal.NAVY))
        c.roundRect(MARGIN, y - box_h, PAGE_W - 2 * MARGIN, box_h, 2 * mm, stroke=0, fill=1)
        c.setFillColor(_hc(pal.WHITE))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN + 5 * mm, y - box_h + 4.5 * mm, "NET À PAYER")
        c.setFont("Helvetica-Bold", 15)
        c.drawRightString(PAGE_W - MARGIN - 5 * mm, y - box_h + 4.2 * mm, format_mad(result.net_pay))
        return y - box_h - 6 * mm

    def _draw_employer_cost_block(self, c: canvas.Canvas, result: PayrollResult, y: float) -> float:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(_hc(pal.SLATE))
        c.drawString(MARGIN, y, "RÉCAPITULATIF COÛT EMPLOYEUR (informatif — n'affecte pas le net ci-dessus)")
        y -= 5 * mm

        rows = [
            ("CNSS patronale", format_mad(result.cnss_patronal)),
            ("Allocations familiales", format_mad(result.allocations_familiales_pat)),
            ("AMO patronale", format_mad(result.amo_patronal)),
            ("Taxe de Formation Professionnelle", format_mad(result.tfp)),
            ("Coût total employeur (mensuel)", format_mad(result.cout_total_employeur + result.allowances.total_exonere)),
            ("Coût horaire chantier", format_mad(result.cout_horaire_chantier) + " / h"),
        ]
        data = [[lbl, val] for lbl, val in rows]
        table = Table(data, colWidths=[90 * mm, 40 * mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, -1), _hc(pal.TEXT_MUTED)),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("FONTNAME", (0, len(rows) - 2), (-1, len(rows) - 2), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, len(rows) - 2), (-1, len(rows) - 2), _hc(pal.TEXT_DARK)),
        ]))
        w, h = table.wrapOn(c, 130 * mm, y)
        table.drawOn(c, MARGIN, y - h)
        return y - h - 4 * mm

    def _draw_qr_and_footer(self, c: canvas.Canvas, employee: Employee, result: PayrollResult, y: float) -> None:
        qr_size = 26 * mm
        qr_x = PAGE_W - MARGIN - qr_size
        qr_y = MARGIN + 4 * mm

        token, png_buf = self.qr_codec.build_and_encode_qr(
            cin=employee.cin,
            full_name=employee.full_name,
            net_pay=result.net_pay,
            pay_date=date(result.inputs.period_year, result.inputs.period_month, 1).isoformat(),
        )
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(png_buf), qr_x, qr_y, width=qr_size, height=qr_size,
                     preserveAspectRatio=True, mask="auto")
        c.setFont("Helvetica", 6)
        c.setFillColor(_hc(pal.TEXT_MUTED))
        c.drawCentredString(qr_x + qr_size / 2, qr_y - 3.2 * mm, "Scanner pour vérifier")

        c.setFont("Helvetica", 7)
        c.setFillColor(_hc(pal.TEXT_MUTED))
        generated = datetime.now().strftime("%d/%m/%Y à %H:%M")
        c.drawString(MARGIN, MARGIN + 10 * mm,
                      f"Document généré automatiquement le {generated} — {self.company.name}")
        c.drawString(MARGIN, MARGIN + 6 * mm,
                      "Bulletin de paie à conserver sans limitation de durée (Art. 370, Code du Travail).")
        c.setStrokeColor(_hc(pal.BORDER))
        c.setLineWidth(0.4)
        c.line(MARGIN, MARGIN + 13 * mm, qr_x - 4 * mm, MARGIN + 13 * mm)
