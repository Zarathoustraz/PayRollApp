# -*- coding: utf-8 -*-
"""gui/employee_form.py — sidebar panel used by the Employees tab to
create or edit a single Employee. Purely presentational: it builds an
Employee from its fields and emits a signal: the tab owns persistence.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models import MARITAL_STATUSES, RATE_TYPE_HOURLY, RATE_TYPE_MONTHLY, Employee
from .widgets import HLine, SectionTitle


def _qdate_to_date(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


def _date_to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


class EmployeeFormPanel(QWidget):
    employee_save_requested = pyqtSignal(object)     # Employee
    employee_delete_requested = pyqtSignal(int)        # employee id

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self._current_id: Optional[int] = None
        self.setFixedWidth(320)
        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(10)

        self.title = SectionTitle("Nouvel employé")
        outer.addWidget(self.title)
        outer.addWidget(HLine())

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.dob = QDateEdit(calendarPopup=True)
        self.dob.setDisplayFormat("dd/MM/yyyy")
        self.dob.setDate(QDate(1995, 1, 1))
        self.marital_status = QComboBox()
        self.marital_status.addItems(MARITAL_STATUSES)
        self.dependents = QSpinBox()
        self.dependents.setRange(0, 6)
        self.cin = QLineEdit()
        self.cnss_number = QLineEdit()
        self.hire_date = QDateEdit(calendarPopup=True)
        self.hire_date.setDisplayFormat("dd/MM/yyyy")
        self.hire_date.setDate(QDate.currentDate())
        self.rate_type = QComboBox()
        self.rate_type.addItem("Taux horaire", RATE_TYPE_HOURLY)
        self.rate_type.addItem("Salaire global (mensuel)", RATE_TYPE_MONTHLY)
        self.rate_amount = QDoubleSpinBox()
        self.rate_amount.setRange(0, 500000)
        self.rate_amount.setDecimals(2)
        self.rate_amount.setSuffix(" MAD")
        self.active = QCheckBox("Employé actif")
        self.active.setChecked(True)

        form.addRow("Prénom", self.first_name)
        form.addRow("Nom", self.last_name)
        form.addRow("Date de naissance", self.dob)
        form.addRow("Situation familiale", self.marital_status)
        form.addRow("Personnes à charge", self.dependents)
        form.addRow("CIN", self.cin)
        form.addRow("N° CNSS", self.cnss_number)
        form.addRow("Date d'embauche", self.hire_date)
        form.addRow("Taux par défaut", self.rate_type)
        form.addRow("Montant par défaut", self.rate_amount)
        form.addRow("", self.active)
        outer.addLayout(form)
        outer.addStretch()

        btn_row = QHBoxLayout()
        self.new_btn = QPushButton("Nouveau")
        self.new_btn.setObjectName("flat")
        self.delete_btn = QPushButton("Supprimer")
        self.delete_btn.setObjectName("danger")
        btn_row.addWidget(self.new_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.delete_btn)
        outer.addLayout(btn_row)

        self.save_btn = QPushButton("Enregistrer")
        self.save_btn.setObjectName("primary")
        outer.addWidget(self.save_btn)

        self.new_btn.clicked.connect(self.clear)
        self.save_btn.clicked.connect(self._on_save)
        self.delete_btn.clicked.connect(self._on_delete)

    # -- public API ----------------------------------------------------

    def load_employee(self, emp: Employee) -> None:
        self._current_id = emp.id
        self.title.setText(f"Modifier — {emp.full_name}")
        self.first_name.setText(emp.first_name)
        self.last_name.setText(emp.last_name)
        if emp.date_of_birth:
            self.dob.setDate(_date_to_qdate(emp.date_of_birth))
        self.marital_status.setCurrentText(emp.marital_status)
        self.dependents.setValue(emp.dependents_count)
        self.cin.setText(emp.cin)
        self.cnss_number.setText(emp.cnss_number)
        self.hire_date.setDate(_date_to_qdate(emp.hire_date))
        idx = self.rate_type.findData(emp.default_rate_type)
        self.rate_type.setCurrentIndex(max(idx, 0))
        self.rate_amount.setValue(emp.default_rate_amount)
        self.active.setChecked(emp.active)
        self.delete_btn.setEnabled(True)

    def clear(self) -> None:
        self._current_id = None
        self.title.setText("Nouvel employé")
        self.first_name.clear()
        self.last_name.clear()
        self.dob.setDate(QDate(1995, 1, 1))
        self.marital_status.setCurrentIndex(0)
        self.dependents.setValue(0)
        self.cin.clear()
        self.cnss_number.clear()
        self.hire_date.setDate(QDate.currentDate())
        self.rate_type.setCurrentIndex(0)
        self.rate_amount.setValue(0)
        self.active.setChecked(True)
        self.delete_btn.setEnabled(False)
        self.first_name.setFocus()

    # -- internal --------------------------------------------------------

    def _on_save(self) -> None:
        if not self.first_name.text().strip() or not self.last_name.text().strip():
            QMessageBox.warning(self, "Champs requis", "Le prénom et le nom sont obligatoires.")
            return
        emp = Employee(
            id=self._current_id,
            first_name=self.first_name.text().strip(),
            last_name=self.last_name.text().strip(),
            date_of_birth=_qdate_to_date(self.dob.date()),
            marital_status=self.marital_status.currentText(),
            dependents_count=self.dependents.value(),
            cnss_number=self.cnss_number.text().strip(),
            cin=self.cin.text().strip(),
            hire_date=_qdate_to_date(self.hire_date.date()),
            default_rate_type=self.rate_type.currentData(),
            default_rate_amount=self.rate_amount.value(),
            active=self.active.isChecked(),
        )
        self.employee_save_requested.emit(emp)

    def _on_delete(self) -> None:
        if self._current_id is None:
            return
        confirm = QMessageBox.question(
            self, "Confirmer la suppression",
            "Supprimer cet employé et l'historique de ses bulletins de paie ?\nCette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.employee_delete_requested.emit(self._current_id)
