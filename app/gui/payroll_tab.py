# -*- coding: utf-8 -*-
"""gui/payroll_tab.py — Tab 2: Payroll Generator.

Every input widget is wired to _recalculate(), which rebuilds a
PayrollInputs, runs it through PayrollEngine, and repaints the preview —
so the breakdown on screen is always live, exactly like the Excel sheet it
replaces. Nothing is written to the database until "GÉNÉRER LE PDF".
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..crypto_utils import PayslipQRCodec
from ..database import Database
from ..formatting import MONTHS_FR, format_mad, format_seniority_fr
from ..models import (
    MODE_BRUT,
    MODE_NET,
    RATE_TYPE_HOURLY,
    RATE_TYPE_MONTHLY,
    Employee,
    ExemptAllowanceInputs,
    PayrollInputs,
    PayrollResult,
)
from ..payroll_engine import PayrollEngine
from ..pdf_generator import PayslipPDFGenerator
from ..tax_parameters import TaxParameters
from .widgets import FieldLabel, HLine, NetPayCard, SectionTitle, WarningBanner


def _mad_spin(suffix: str = " MAD", maximum: float = 500000) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(0, maximum)
    sb.setDecimals(2)
    sb.setSuffix(suffix)
    sb.setSingleStep(50)
    return sb


class PayrollTab(QWidget):
    def __init__(self, db: Database, engine: PayrollEngine, qr_codec: PayslipQRCodec):
        super().__init__()
        self.db = db
        self.engine = engine
        self.qr_codec = qr_codec
        self.pdf_generator = PayslipPDFGenerator(config.DEFAULT_COMPANY, qr_codec)
        self._current_result: Optional[PayrollResult] = None
        self._building_ui = True
        self._build_ui()
        self._building_ui = False
        self.refresh_employees()

    # -- layout ----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_input_column(), stretch=5)
        root.addWidget(self._build_preview_column(), stretch=4)

    def _build_input_column(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 18, 16, 18)
        layout.setSpacing(10)

        layout.addWidget(SectionTitle("Générateur de paie"))

        top_form = QFormLayout()
        top_form.setSpacing(8)
        self.employee_combo = QComboBox()
        self.employee_combo.currentIndexChanged.connect(self._on_employee_changed)
        top_form.addRow("Employé", self.employee_combo)

        period_row = QHBoxLayout()
        self.month_combo = QComboBox()
        self.month_combo.addItems(MONTHS_FR[1:])
        self.month_combo.setCurrentIndex(datetime.now().month - 1)
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2100)
        self.year_spin.setValue(datetime.now().year)
        period_row.addWidget(self.month_combo, stretch=2)
        period_row.addWidget(self.year_spin, stretch=1)
        top_form.addRow("Période", period_row)

        self.hours_spin = QDoubleSpinBox()
        self.hours_spin.setRange(0, 400)
        self.hours_spin.setDecimals(1)
        self.hours_spin.setValue(self.engine.params.heures_legales_mensuelles)
        top_form.addRow("Heures travaillées", self.hours_spin)

        self.dependents_spin = QSpinBox()
        self.dependents_spin.setRange(0, 6)
        top_form.addRow("Personnes à charge", self.dependents_spin)
        layout.addLayout(top_form)
        layout.addWidget(HLine())

        # -- mode / unit / amount (mirrors Calculateur!C4/C5/C8) --------
        mode_form = QFormLayout()
        mode_form.setSpacing(8)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("BRUT", MODE_BRUT)
        self.mode_combo.addItem("NET", MODE_NET)
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("Taux horaire", RATE_TYPE_HOURLY)
        self.unit_combo.addItem("Salaire global (mensuel)", RATE_TYPE_MONTHLY)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_combo)
        mode_row.addWidget(self.unit_combo)
        mode_form.addRow("Je connais le / exprimé par", mode_row)

        self.amount_label = FieldLabel("Montant saisi")
        self.amount_spin = _mad_spin(suffix="")
        self.amount_spin.setDecimals(2)
        self.amount_spin.setRange(0, 500000)
        mode_form.addRow(self.amount_label, self.amount_spin)

        self.logement_spin = _mad_spin()
        mode_form.addRow("Indemnité de logement (imposable)", self.logement_spin)
        layout.addLayout(mode_form)
        layout.addWidget(HLine())

        # -- exempt allowances (Calculateur!⑤) ---------------------------
        layout.addWidget(SectionTitle("Indemnités exonérées (optimisation fiscale)"))
        alw_form = QFormLayout()
        alw_form.setSpacing(8)
        self.transport_urbain_spin = _mad_spin()
        self.transport_hors_spin = _mad_spin()
        self.km_spin = QDoubleSpinBox()
        self.km_spin.setRange(0, 10000)
        self.km_spin.setSuffix(" km")
        self.panier_spin = _mad_spin()
        self.salissure_spin = _mad_spin()
        self.outillage_spin = _mad_spin()
        self.representation_spin = _mad_spin()
        alw_form.addRow("Transport domicile-travail (urbain)", self.transport_urbain_spin)
        alw_form.addRow("Transport (hors périmètre urbain)", self.transport_hors_spin)
        alw_form.addRow("Indemnité kilométrique (km parcourus)", self.km_spin)
        alw_form.addRow("Prime de panier", self.panier_spin)
        alw_form.addRow("Prime de salissure / bleu de travail", self.salissure_spin)
        alw_form.addRow("Prime d'outillage", self.outillage_spin)
        alw_form.addRow("Indemnité de représentation", self.representation_spin)
        layout.addLayout(alw_form)

        self.warning_banner = WarningBanner()
        layout.addWidget(self.warning_banner)
        layout.addStretch()

        for w in [self.hours_spin, self.dependents_spin, self.amount_spin, self.logement_spin,
                   self.transport_urbain_spin, self.transport_hors_spin, self.km_spin,
                   self.panier_spin, self.salissure_spin, self.outillage_spin, self.representation_spin]:
            w.valueChanged.connect(self._recalculate)
        for c in [self.mode_combo, self.unit_combo, self.month_combo, self.year_spin]:
            (c.currentIndexChanged if isinstance(c, QComboBox) else c.valueChanged).connect(self._recalculate)
        self.mode_combo.currentIndexChanged.connect(self._update_amount_label)
        self.unit_combo.currentIndexChanged.connect(self._update_amount_label)
        self._update_amount_label()

        scroll.setWidget(inner)
        return scroll

    def _build_preview_column(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        layout.addWidget(SectionTitle("Aperçu du calcul"))
        self.net_pay_card = NetPayCard()
        layout.addWidget(self.net_pay_card)

        self.breakdown_grid = QGridLayout()
        self.breakdown_grid.setHorizontalSpacing(18)
        self.breakdown_grid.setVerticalSpacing(4)
        self._breakdown_labels: dict[str, QLabel] = {}
        rows = [
            ("brut_base", "Salaire de base"),
            ("anciennete", "Prime d'ancienneté"),
            ("brut_imposable", "Brut imposable"),
            ("cnss", "CNSS salarié(e)"),
            ("amo", "AMO salarié(e)"),
            ("frais_pro", "Frais professionnels (abattement)"),
            ("rni", "Revenu Net Imposable (RNI)"),
            ("palier", "Palier IR appliqué"),
            ("ir_net", "IR net (retenue à la source)"),
            ("exonere", "Total indemnités exonérées"),
            ("cout_employeur", "Coût total employeur"),
            ("cout_horaire", "Coût horaire chantier"),
        ]
        for i, (key, label) in enumerate(rows):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #5B6B82;")
            val = QLabel("—")
            val.setStyleSheet("font-weight: 600;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.breakdown_grid.addWidget(lbl, i, 0)
            self.breakdown_grid.addWidget(val, i, 1)
            self._breakdown_labels[key] = val
        layout.addLayout(self.breakdown_grid)

        layout.addWidget(HLine())
        layout.addWidget(SectionTitle("Historique récent"))
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["Période", "Net payé", "Généré le"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setMaximumHeight(140)
        layout.addWidget(self.history_table)

        layout.addStretch()
        self.generate_btn = QPushButton("GÉNÉRER LE PDF")
        self.generate_btn.setObjectName("primary")
        self.generate_btn.setMinimumHeight(42)
        self.generate_btn.clicked.connect(self._on_generate_pdf)
        layout.addWidget(self.generate_btn)

        return panel

    # -- data flow ---------------------------------------------------------

    def refresh_employees(self) -> None:
        current_id = self.employee_combo.currentData()
        self.employee_combo.blockSignals(True)
        self.employee_combo.clear()
        for emp in self.db.list_employees(active_only=True):
            self.employee_combo.addItem(emp.full_name, emp.id)
        self.employee_combo.blockSignals(False)
        if current_id is not None:
            idx = self.employee_combo.findData(current_id)
            if idx >= 0:
                self.employee_combo.setCurrentIndex(idx)
        self._on_employee_changed()

    def _current_employee(self) -> Optional[Employee]:
        emp_id = self.employee_combo.currentData()
        return self.db.get_employee(emp_id) if emp_id is not None else None

    def _on_employee_changed(self) -> None:
        emp = self._current_employee()
        if emp:
            self.dependents_spin.setValue(emp.dependents_count)
            idx = self.unit_combo.findData(emp.default_rate_type)
            if idx >= 0:
                self.unit_combo.setCurrentIndex(idx)
            self.amount_spin.setValue(emp.default_rate_amount)
            self._refresh_history(emp.id)
        self._recalculate()

    def _update_amount_label(self) -> None:
        # Mirrors Calculateur!B8: ="Montant saisi (" & C5 & " — " & C4 & ")"
        unit_text = self.unit_combo.currentText()
        mode_text = self.mode_combo.currentText()
        self.amount_label.setText(f"Montant saisi ({unit_text} — {mode_text})")
        self.amount_spin.setSuffix(" MAD/h" if self.unit_combo.currentData() == RATE_TYPE_HOURLY else " MAD")

    def _build_inputs(self, employee: Employee) -> PayrollInputs:
        allowances = ExemptAllowanceInputs(
            transport_urbain=self.transport_urbain_spin.value(),
            transport_hors_urbain=self.transport_hors_spin.value(),
            km_parcourus=self.km_spin.value(),
            panier=self.panier_spin.value(),
            salissure=self.salissure_spin.value(),
            outillage=self.outillage_spin.value(),
            representation=self.representation_spin.value(),
        )
        return PayrollInputs(
            employee=employee,
            period_month=self.month_combo.currentIndex() + 1,
            period_year=self.year_spin.value(),
            hours_worked=self.hours_spin.value(),
            mode=self.mode_combo.currentData(),
            unit=self.unit_combo.currentData(),
            amount=self.amount_spin.value(),
            indemnite_logement=self.logement_spin.value(),
            dependents_override=self.dependents_spin.value(),
            allowances=allowances,
        )

    def _recalculate(self) -> None:
        if self._building_ui:
            return
        employee = self._current_employee()
        if employee is None:
            self.net_pay_card.set_amount(0)
            self.generate_btn.setEnabled(False)
            return
        inputs = self._build_inputs(employee)
        try:
            result = self.engine.compute(inputs, reference_date=self._period_end(inputs))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur de calcul", str(exc))
            self.generate_btn.setEnabled(False)
            return
        self._current_result = result
        self._paint_result(result)
        self.generate_btn.setEnabled(True)

    @staticmethod
    def _period_end(inputs: PayrollInputs) -> date:
        if inputs.period_month == 12:
            return date(inputs.period_year, 12, 31)
        from datetime import timedelta
        return date(inputs.period_year, inputs.period_month + 1, 1) - timedelta(days=1)

    def _paint_result(self, r: PayrollResult) -> None:
        self.net_pay_card.set_amount(r.net_pay)
        labels = self._breakdown_labels
        labels["brut_base"].setText(format_mad(r.salaire_base))
        anc = f"{format_mad(r.prime_anciennete)}  ({r.seniority_rate:.0%}, {format_seniority_fr(r.seniority_years)})"
        labels["anciennete"].setText(anc if r.prime_anciennete > 0.005 else "—")
        labels["brut_imposable"].setText(format_mad(r.brut_imposable))
        labels["cnss"].setText(format_mad(r.cnss_salarie))
        labels["amo"].setText(format_mad(r.amo_salarie))
        labels["frais_pro"].setText(format_mad(r.frais_professionnels))
        labels["rni"].setText(format_mad(r.rni))
        labels["palier"].setText(f"Tranche {r.palier_ir} / 6")
        labels["ir_net"].setText(format_mad(r.ir_net))
        labels["exonere"].setText(format_mad(r.allowances.total_exonere))
        labels["cout_employeur"].setText(format_mad(r.cout_total_employeur + r.allowances.total_exonere))
        labels["cout_horaire"].setText(format_mad(r.cout_horaire_chantier) + " / h")

        self.warning_banner.set_message(r.allowances.non_cumul_warning)
        if not r.bisection_converged:
            self.warning_banner.set_message(
                "Le solveur Net → Brut n'a pas convergé pour ce montant — vérifiez les valeurs saisies."
            )

    def _refresh_history(self, employee_id: int) -> None:
        rows = self.db.list_payslips_for_employee(employee_id, limit=12)
        self.history_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            period = f"{MONTHS_FR[row['period_month']]} {row['period_year']}"
            self.history_table.setItem(i, 0, QTableWidgetItem(period))
            self.history_table.setItem(i, 1, QTableWidgetItem(format_mad(row["net_pay"])))
            gen_date = row["generation_date"][:16].replace("T", " ")
            self.history_table.setItem(i, 2, QTableWidgetItem(gen_date))

    # -- PDF generation ----------------------------------------------------

    def generate_payslip_pdf(self, employee: Employee, result: PayrollResult) -> Path:
        """Pure generation path: render the PDF, persist the payslip, return
        the output path. No dialogs — safe to call from tests or scripts.
        Raises on failure rather than swallowing it into a message box."""
        month_name = MONTHS_FR[result.inputs.period_month]
        safe_name = f"{employee.last_name}_{employee.first_name}".replace(" ", "_")
        filename = f"Bulletin_{safe_name}_{month_name}{result.inputs.period_year}.pdf"
        output_path = config.OUTPUT_DIR / filename

        self.pdf_generator.generate(employee, result, output_path)
        token, _ = self.qr_codec.build_and_encode_qr(
            employee.cin, employee.full_name, result.net_pay,
            date(result.inputs.period_year, result.inputs.period_month, 1).isoformat(),
        )
        self.db.save_payslip(
            employee.id, result,
            generation_date=datetime.now().isoformat(timespec="seconds"),
            pdf_path=str(output_path), qr_payload_encrypted=token,
        )
        return output_path

    def _on_generate_pdf(self) -> None:
        employee = self._current_employee()
        if employee is None or self._current_result is None:
            return
        result = self._current_result

        if not employee.cin:
            proceed = QMessageBox.question(
                self, "CIN manquant",
                "Cet employé n'a pas de CIN renseigné — le QR code de vérification sera incomplet.\nContinuer quand même ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        try:
            output_path = self.generate_payslip_pdf(employee, result)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", f"Échec de la génération du bulletin :\n{exc}")
            return

        self._refresh_history(employee.id)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Bulletin généré")
        box.setText(f"Bulletin de paie généré avec succès pour {employee.full_name}.")
        box.setInformativeText(str(output_path))
        open_btn = box.addButton("Ouvrir le PDF", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() == open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path)))
