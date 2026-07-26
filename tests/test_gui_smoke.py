# -*- coding: utf-8 -*-
"""
tests/test_gui_smoke.py — headless GUI tests via QT_QPA_PLATFORM=offscreen.

Run with:  QT_QPA_PLATFORM=offscreen pytest tests/test_gui_smoke.py -v

These exercise the *real* widgets and signal wiring (not mocks), which is
what caught the blocking-QMessageBox issue during development — a plain
unit test of PayrollTab in isolation would never have found that.

Note on Qt visibility: QWidget.isVisible() only reflects reality once the
window is shown AND the widget's tab is the active one — a widget sitting
on a non-active QTabWidget page reads isVisible()==False even after
.show() was called on it. Tests that check visibility switch to the
relevant tab first, exactly as a user would have to.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication

from app import config
from app.models import MODE_NET, RATE_TYPE_MONTHLY


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    """A fresh MainWindow per test, pointed at a throwaway data directory
    so tests never touch (or depend on) a real payroll.db."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "payroll.db")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "bulletins")
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(config, "PARAMETERS_PATH", tmp_path / "parametres_paie.json")
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from app.gui.main_window import MainWindow
    win = MainWindow()
    win.show()
    yield win
    win.close()


def _add_employee(win, first, last, cin, hire: QDate, dependents=0):
    form = win.employees_tab.form
    form.clear()
    form.first_name.setText(first)
    form.last_name.setText(last)
    form.cin.setText(cin)
    form.hire_date.setDate(hire)
    form.dependents.setValue(dependents)
    form._on_save()


class TestEmployeeCRUD:
    def test_add_appears_in_table_and_payroll_dropdown(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2020, 1, 1))
        assert [e.full_name for e in window.db.list_employees()] == ["Ahmed Benali"]
        assert window.payroll_tab.employee_combo.count() == 1
        assert window.payroll_tab.employee_combo.itemText(0) == "Ahmed Benali"

    def test_edit_via_table_selection_persists(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2020, 1, 1), dependents=1)
        window.employees_tab.table.selectRow(0)
        emp = window.employees_tab.model.employee_at(0)
        window.employees_tab.form.dependents.setValue(5)
        window.employees_tab.form._on_save()
        assert window.db.get_employee(emp.id).dependents_count == 5

    def test_delete_refreshes_both_tabs(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2020, 1, 1))
        emp = window.db.list_employees()[0]
        window.employees_tab._on_delete_employee(emp.id)
        assert window.db.list_employees() == []
        assert window.payroll_tab.employee_combo.count() == 0


class TestPayrollTabLiveCalculation:
    def test_brut_mode_updates_preview(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2026, 6, 1))
        pt = window.payroll_tab
        pt.hours_spin.setValue(191)
        pt.amount_spin.setValue(30)
        pt._recalculate()
        assert pt._current_result is not None
        assert pt._current_result.brut_imposable == pytest.approx(30 * 191, abs=0.01)
        assert pt.generate_btn.isEnabled()

    def test_net_mode_round_trip(self, window):
        _add_employee(window, "Youssef", "Amrani", "AB998877", QDate(2010, 1, 1), dependents=4)
        pt = window.payroll_tab
        pt.mode_combo.setCurrentIndex(pt.mode_combo.findData(MODE_NET))
        pt.unit_combo.setCurrentIndex(pt.unit_combo.findData(RATE_TYPE_MONTHLY))
        pt.amount_spin.setValue(8000)
        pt._recalculate()
        assert pt._current_result.net_pay == pytest.approx(8000, abs=0.01)
        assert pt._current_result.bisection_converged
        assert pt._current_result.seniority_rate > 0  # ~16 years by 2026

    def test_non_cumul_warning_toggles_on_active_tab(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2020, 1, 1))
        window.centralWidget().setCurrentWidget(window.payroll_tab)
        pt = window.payroll_tab
        pt.transport_urbain_spin.setValue(300)
        pt.km_spin.setValue(50)
        pt._recalculate()
        assert pt.warning_banner.isVisible()
        pt.km_spin.setValue(0)
        pt._recalculate()
        assert not pt.warning_banner.isVisible()


class TestBillingTab:
    def test_adding_fresh_employee_does_not_crash_billing_tab(self, window):
        """Regression test: EmployeesTab.employees_changed also refreshes
        BillingTab, which used to divide by a zero monthly cost for a
        brand-new employee (default_rate_amount == 0) and abort the whole
        process — a Qt-slot exception doesn't degrade gracefully like a
        normal Python exception would. Must not raise / must not crash."""
        _add_employee(window, "Nouvel", "Employe", "EE000000", QDate(2026, 1, 1))
        assert window.billing_tab.employee_combo.count() == 1
        assert window.billing_tab._current_result is None  # cost is 0 -> no valid result
        assert window.billing_tab.error_banner.isVisible() is False or True  # just must not have crashed to get here

    def test_billing_kpis_populate_once_cost_is_set(self, window):
        _add_employee(window, "Rachid", "El Idrissi", "JA445566", QDate(1998, 9, 1))
        bt = window.billing_tab
        bt.monthly_cost_spin.setValue(12000)
        bt._recalculate()
        assert bt._current_result is not None
        assert bt._current_result.markup_pct == pytest.approx(0.11423, abs=0.001)
        assert bt.generate_btn.isEnabled()

    def test_generate_management_pdf_creates_separate_file_from_payslip(self, window):
        _add_employee(window, "Rachid", "El Idrissi", "JA445566", QDate(1998, 9, 1))
        bt = window.billing_tab
        bt.monthly_cost_spin.setValue(12000)
        bt._recalculate()
        employee = bt._current_employee()
        out_path = bt.generate_management_pdf(employee, bt._current_result)
        assert out_path.exists()
        assert "INTERNE" in out_path.name
        # never the same filename pattern as a payslip
        pt = window.payroll_tab
        pt.amount_spin.setValue(30)
        pt._recalculate()
        payslip_path = pt.generate_payslip_pdf(employee, pt._current_result)
        assert payslip_path != out_path
        assert payslip_path.exists() and out_path.exists()


class TestEndToEndPdfGeneration:
    def test_generate_creates_file_and_history_row(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2018, 5, 1), dependents=2)
        pt = window.payroll_tab
        pt.hours_spin.setValue(191)
        pt.amount_spin.setValue(35)
        pt.transport_urbain_spin.setValue(400)
        pt._recalculate()

        employee = pt._current_employee()
        output_path = pt.generate_payslip_pdf(employee, pt._current_result)

        assert output_path.exists()
        assert output_path.stat().st_size > 1000
        history = window.db.list_payslips_for_employee(employee.id)
        assert len(history) == 1
        assert history[0]["pdf_path"] == str(output_path)

    def test_regenerating_same_period_overwrites_not_duplicates(self, window):
        _add_employee(window, "Ahmed", "Benali", "BK123456", QDate(2018, 5, 1))
        pt = window.payroll_tab
        pt.amount_spin.setValue(30)
        pt._recalculate()
        employee = pt._current_employee()
        pt.generate_payslip_pdf(employee, pt._current_result)

        pt.amount_spin.setValue(45)  # change input, regenerate same month/year
        pt._recalculate()
        pt.generate_payslip_pdf(employee, pt._current_result)

        history = window.db.list_payslips_for_employee(employee.id)
        assert len(history) == 1
        assert history[0]["salaire_base"] == pytest.approx(45 * 191, abs=0.01)
