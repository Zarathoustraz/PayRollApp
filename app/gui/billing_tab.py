# -*- coding: utf-8 -*-
"""
gui/billing_tab.py — Tab 3: Rentabilité / Facturation ("Roger's Theorem").

Self-contained: has its own employee selector and runs its own PayrollEngine
call to get a baseline "Coût employeur mensuel", rather than reading live
state from the Payroll Generator tab. Simpler and more robust than trying to
keep two tabs' selection state in sync, and this tab's purpose (an annual
billing-strategy estimate) is deliberately based on an employee's *standard*
monthly cost, not whatever one-off allowances happen to be sitting in the
Payroll tab's form at the same moment.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
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
from ..billing_engine import BillingCalculator
from ..database import Database
from ..formatting import MONTHS_FR, format_mad
from ..models import (
    MODE_BRUT,
    BillingInputs,
    BillingResult,
    Employee,
    PayrollInputs,
)
from ..management_pdf_generator import ManagementSummaryPDFGenerator
from ..payroll_engine import PayrollEngine
from .widgets import HLine, KpiCard, SectionTitle, WarningBanner


def _mad_spin(maximum: float = 500000) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(0, maximum)
    sb.setDecimals(2)
    sb.setSuffix(" MAD")
    sb.setSingleStep(100)
    return sb


class BillingTab(QWidget):
    def __init__(self, db: Database, payroll_engine: PayrollEngine):
        super().__init__()
        self.db = db
        self.payroll_engine = payroll_engine
        self.billing_calc = BillingCalculator(payroll_engine.params)
        self.pdf_generator = ManagementSummaryPDFGenerator(config.DEFAULT_COMPANY)
        self._current_result: Optional[BillingResult] = None
        self._building_ui = True
        self._build_ui()
        self._building_ui = False
        self.refresh_employees()

    # -- layout ------------------------------------------------------------

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

        layout.addWidget(SectionTitle("Rentabilité & facturation"))
        notice = WarningBanner()
        notice.set_message(
            "Onglet réservé à un usage interne (direction, chargés d'affaires) — "
            "les documents générés ici ne doivent jamais être remis à un salarié."
        )
        layout.addWidget(notice)

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
        top_form.addRow("Période de référence", period_row)

        self.monthly_cost_spin = _mad_spin()
        top_form.addRow("Coût employeur mensuel (base)", self.monthly_cost_spin)
        self.auto_compute_btn = QPushButton("Recalculer depuis le taux par défaut de l'employé")
        self.auto_compute_btn.setObjectName("flat")
        self.auto_compute_btn.clicked.connect(self._auto_compute_monthly_cost)
        top_form.addRow("", self.auto_compute_btn)
        layout.addLayout(top_form)
        layout.addWidget(HLine())

        layout.addWidget(SectionTitle("Paramètres de rentabilité (site / société)"))
        params_form = QFormLayout()
        params_form.setSpacing(8)
        p = self.payroll_engine.params
        self.conges_spin = QDoubleSpinBox()
        self.conges_spin.setRange(0, 365)
        self.conges_spin.setSuffix(" jours")
        self.conges_spin.setValue(p.conges_payes_jours_an)
        self.feries_spin = QDoubleSpinBox()
        self.feries_spin.setRange(0, 365)
        self.feries_spin.setSuffix(" jours")
        self.feries_spin.setValue(p.jours_feries_an)
        self.heures_jour_spin = QDoubleSpinBox()
        self.heures_jour_spin.setRange(0, 24)
        self.heures_jour_spin.setDecimals(2)
        self.heures_jour_spin.setSuffix(" h")
        self.heures_jour_spin.setValue(p.heures_par_jour_travaille)
        self.heures_theo_spin = QDoubleSpinBox()
        self.heures_theo_spin.setRange(0, 4000)
        self.heures_theo_spin.setSuffix(" h")
        self.heures_theo_spin.setValue(p.heures_theoriques_annuelles)
        params_form.addRow("Congés payés annuels", self.conges_spin)
        params_form.addRow("Jours fériés chômés payés / an", self.feries_spin)
        params_form.addRow("Heures par jour travaillé", self.heures_jour_spin)
        params_form.addRow("Heures théoriques annuelles", self.heures_theo_spin)
        layout.addLayout(params_form)
        layout.addStretch()

        for w in [self.monthly_cost_spin, self.conges_spin, self.feries_spin,
                   self.heures_jour_spin, self.heures_theo_spin]:
            w.valueChanged.connect(self._recalculate)
        for c in [self.month_combo, self.year_spin]:
            (c.currentIndexChanged if isinstance(c, QComboBox) else c.valueChanged).connect(self._recalculate)

        scroll.setWidget(inner)
        return scroll

    def _build_preview_column(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        layout.addWidget(SectionTitle("Indicateurs de rentabilité"))
        kpi_row1 = QHBoxLayout()
        self.kpi_theoretical = KpiCard("Coût horaire théorique (naïf)")
        self.kpi_productive_hours = KpiCard("Heures productives réelles / an")
        kpi_row1.addWidget(self.kpi_theoretical)
        kpi_row1.addWidget(self.kpi_productive_hours)
        layout.addLayout(kpi_row1)

        kpi_row2 = QHBoxLayout()
        self.kpi_real_cost = KpiCard("Coût horaire productif réel (plancher)")
        self.kpi_markup = KpiCard("Majoration plancher recommandée")
        kpi_row2.addWidget(self.kpi_real_cost)
        kpi_row2.addWidget(self.kpi_markup)
        layout.addLayout(kpi_row2)

        self.error_banner = WarningBanner()
        layout.addWidget(self.error_banner)

        layout.addWidget(HLine())
        layout.addWidget(SectionTitle("Résumés générés récemment"))
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["Période", "Majoration", "Généré le"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setMaximumHeight(140)
        layout.addWidget(self.history_table)

        layout.addStretch()
        caption = QLabel("Document interne uniquement — jamais remis au salarié.")
        caption.setStyleSheet("color: #B3432B; font-weight: 600; font-size: 11px;")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)
        self.generate_btn = QPushButton("GÉNÉRER LE RÉSUMÉ DE GESTION (PDF INTERNE)")
        self.generate_btn.setObjectName("primary")
        self.generate_btn.setMinimumHeight(42)
        self.generate_btn.clicked.connect(self._on_generate_pdf)
        layout.addWidget(self.generate_btn)

        return panel

    # -- data flow -----------------------------------------------------

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
            self._auto_compute_monthly_cost()
            self._refresh_history(emp.id)
        self._recalculate()

    def _auto_compute_monthly_cost(self) -> None:
        """Baseline: this employee's default rate x standard monthly hours,
        no allowances/logement/overtime — a clean 'typical month' figure the
        PM can then override directly if modelling a different scenario."""
        emp = self._current_employee()
        if emp is None:
            return
        inputs = PayrollInputs(
            employee=emp, period_month=self.month_combo.currentIndex() + 1,
            period_year=self.year_spin.value(),
            hours_worked=self.payroll_engine.params.heures_legales_mensuelles,
            mode=MODE_BRUT, unit=emp.default_rate_type, amount=emp.default_rate_amount,
        )
        try:
            result = self.payroll_engine.compute(inputs, reference_date=date.today())
        except Exception as exc:  # noqa: BLE001 — same reasoning as _recalculate()
            self.error_banner.set_message(f"Impossible de calculer le coût de base : {exc}")
            return
        cost = result.cout_total_employeur + result.allowances.total_exonere
        self.monthly_cost_spin.blockSignals(True)
        self.monthly_cost_spin.setValue(cost)
        self.monthly_cost_spin.blockSignals(False)
        self._recalculate()

    def _recalculate(self) -> None:
        if self._building_ui:
            return
        emp = self._current_employee()
        if emp is None:
            self._current_result = None
            self.generate_btn.setEnabled(False)
            return
        inputs = BillingInputs(
            employee=emp, period_month=self.month_combo.currentIndex() + 1,
            period_year=self.year_spin.value(), monthly_employer_cost=self.monthly_cost_spin.value(),
            conges_payes_jours=self.conges_spin.value(), jours_feries=self.feries_spin.value(),
            heures_par_jour=self.heures_jour_spin.value(),
            heures_theoriques_annuelles=self.heures_theo_spin.value(),
        )
        try:
            result = self.billing_calc.compute(inputs)
        except Exception as exc:  # noqa: BLE001 — any failure here must degrade to a banner, never escape the slot
            self._current_result = None
            self.error_banner.set_message(str(exc))
            self.generate_btn.setEnabled(False)
            self.kpi_theoretical.set_value("—")
            self.kpi_productive_hours.set_value("—")
            self.kpi_real_cost.set_value("—")
            self.kpi_markup.set_value("—")
            return
        self.error_banner.set_message(None)
        self._current_result = result
        self._paint_result(result)
        self.generate_btn.setEnabled(True)

    def _paint_result(self, r: BillingResult) -> None:
        self.kpi_theoretical.set_value(format_mad(r.theoretical_hourly_cost) + " / h")
        self.kpi_productive_hours.set_value(f"{r.actual_productive_hours:,.0f} h".replace(",", " "))
        self.kpi_real_cost.set_value(format_mad(r.real_productive_hourly_cost) + " / h")
        self.kpi_markup.set_value(f"+{r.markup_pct:.1%}")

    def _refresh_history(self, employee_id: int) -> None:
        rows = self.db.list_management_summaries_for_employee(employee_id, limit=12)
        self.history_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            period = f"{MONTHS_FR[row['period_month']]} {row['period_year']}"
            self.history_table.setItem(i, 0, QTableWidgetItem(period))
            self.history_table.setItem(i, 1, QTableWidgetItem(f"+{row['markup_pct']:.1%}"))
            gen_date = row["generation_date"][:16].replace("T", " ")
            self.history_table.setItem(i, 2, QTableWidgetItem(gen_date))

    # -- PDF generation ------------------------------------------------

    def generate_management_pdf(self, employee: Employee, result: BillingResult):
        """Pure generation path — no dialogs, mirrors PayrollTab's split for
        the same reason (testability + no UI logic buried in a slot)."""
        month_name = MONTHS_FR[result.inputs.period_month]
        safe_name = f"{employee.last_name}_{employee.first_name}".replace(" ", "_")
        filename = f"Resume_Gestion_INTERNE_{safe_name}_{month_name}{result.inputs.period_year}.pdf"
        output_path = config.OUTPUT_DIR / filename

        self.pdf_generator.generate(employee, result, output_path)
        self.db.save_management_summary(
            employee.id, result,
            generation_date=datetime.now().isoformat(timespec="seconds"),
            pdf_path=str(output_path),
        )
        return output_path

    def _on_generate_pdf(self) -> None:
        employee = self._current_employee()
        if employee is None or self._current_result is None:
            return
        try:
            output_path = self.generate_management_pdf(employee, self._current_result)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", f"Échec de la génération du résumé :\n{exc}")
            return
        self._refresh_history(employee.id)
        QMessageBox.information(
            self, "Résumé de gestion généré",
            f"Document interne généré pour {employee.full_name}.\n\n{output_path}\n\n"
            "Rappel : ce fichier est confidentiel et ne doit pas être remis au salarié.",
        )
