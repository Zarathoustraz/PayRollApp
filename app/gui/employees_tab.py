# -*- coding: utf-8 -*-
"""gui/employees_tab.py — Tab 1: Dashboard / Employees."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..database import Database
from ..models import Employee
from .employee_form import EmployeeFormPanel
from .widgets import HLine, KpiCard, SectionTitle

COLUMNS = ["Nom complet", "CIN", "N° CNSS", "Situation", "Pers. à charge", "Embauché(e) le", "Statut"]


class EmployeeTableModel(QAbstractTableModel):
    def __init__(self, employees: Optional[list[Employee]] = None):
        super().__init__()
        self._employees: list[Employee] = employees or []

    def set_employees(self, employees: list[Employee]) -> None:
        self.beginResetModel()
        self._employees = employees
        self.endResetModel()

    def employee_at(self, row: int) -> Optional[Employee]:
        if 0 <= row < len(self._employees):
            return self._employees[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._employees)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        emp = self._employees[index.row()]
        col = index.column()
        if col == 0:
            return emp.full_name
        if col == 1:
            return emp.cin or "—"
        if col == 2:
            return emp.cnss_number or "—"
        if col == 3:
            return emp.marital_status
        if col == 4:
            return str(emp.dependents_count)
        if col == 5:
            return emp.hire_date.strftime("%d/%m/%Y")
        if col == 6:
            return "Actif" if emp.active else "Inactif"
        return None


class EmployeesTab(QWidget):
    employees_changed = pyqtSignal()  # fires after any successful add/edit/delete

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(12)

        main_layout.addWidget(SectionTitle("Tableau de bord"))

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_total = KpiCard("Employés actifs")
        self.kpi_dependents = KpiCard("Total personnes à charge")
        self.kpi_avg_seniority = KpiCard("Ancienneté moyenne")
        kpi_row.addWidget(self.kpi_total)
        kpi_row.addWidget(self.kpi_dependents)
        kpi_row.addWidget(self.kpi_avg_seniority)
        main_layout.addLayout(kpi_row)

        main_layout.addWidget(HLine())
        main_layout.addWidget(SectionTitle("Employés"))

        self.table = QTableView()
        self.model = EmployeeTableModel()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        main_layout.addWidget(self.table)

        root.addWidget(main, stretch=1)

        self.form = EmployeeFormPanel()
        self.form.employee_save_requested.connect(self._on_save_employee)
        self.form.employee_delete_requested.connect(self._on_delete_employee)
        root.addWidget(self.form)

    # -- data flow -----------------------------------------------------

    def refresh(self) -> None:
        employees = self.db.list_employees()
        self.model.set_employees(employees)
        self._update_kpis(employees)

    def _update_kpis(self, employees: list[Employee]) -> None:
        from datetime import date
        active = [e for e in employees if e.active]
        self.kpi_total.set_value(str(len(active)))
        self.kpi_dependents.set_value(str(sum(e.dependents_count for e in active)))
        if active:
            avg_years = sum(e.years_of_service(date.today()) for e in active) / len(active)
            self.kpi_avg_seniority.set_value(f"{avg_years:.1f} ans")
        else:
            self.kpi_avg_seniority.set_value("—")

    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        emp = self.model.employee_at(rows[0].row())
        if emp:
            self.form.load_employee(emp)

    def _on_save_employee(self, emp: Employee) -> None:
        try:
            if emp.id is None:
                new_id = self.db.add_employee(emp)
                emp.id = new_id
            else:
                self.db.update_employee(emp)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer l'employé :\n{exc}")
            return
        self.refresh()
        self.form.load_employee(emp)
        self.employees_changed.emit()

    def _on_delete_employee(self, employee_id: int) -> None:
        try:
            self.db.delete_employee(employee_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erreur", f"Impossible de supprimer l'employé :\n{exc}")
            return
        self.form.clear()
        self.refresh()
        self.employees_changed.emit()
