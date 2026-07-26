# -*- coding: utf-8 -*-
"""
database.py — SQLite persistence (stdlib sqlite3, no ORM).

Two tables: employees and payslips. The payslips table stores the full
computed breakdown (not just the 6 headline figures) so a payslip can be
re-rendered or audited later without re-running the engine against
parameters that may since have changed for a new Loi de Finances.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

from .models import (
    Employee,
    ExemptAllowanceBreakdown,
    ExemptAllowanceInputs,
    ExemptAllowanceLine,
    Payslip,
    PayrollInputs,
    PayrollResult,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name            TEXT NOT NULL,
    last_name             TEXT NOT NULL,
    date_of_birth         TEXT,
    marital_status        TEXT NOT NULL DEFAULT 'Célibataire',
    dependents_count      INTEGER NOT NULL DEFAULT 0,
    cnss_number           TEXT NOT NULL DEFAULT '',
    cin                   TEXT NOT NULL DEFAULT '',
    hire_date             TEXT NOT NULL,
    default_rate_type     TEXT NOT NULL DEFAULT 'hourly',
    default_rate_amount   REAL NOT NULL DEFAULT 0,
    active                INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payslips (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id                   INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    period_month                  INTEGER NOT NULL,
    period_year                   INTEGER NOT NULL,
    hours_worked                  REAL NOT NULL,
    input_mode                    TEXT NOT NULL,
    input_unit                    TEXT NOT NULL,
    input_amount                  REAL NOT NULL,
    dependents_count              INTEGER NOT NULL,
    seniority_years                REAL NOT NULL,
    seniority_rate                 REAL NOT NULL,
    salaire_base                   REAL NOT NULL,
    prime_anciennete                REAL NOT NULL,
    indemnite_logement              REAL NOT NULL,
    allowances_json                 TEXT NOT NULL,
    total_exonere                   REAL NOT NULL,
    total_excedent                  REAL NOT NULL,
    brut_imposable                  REAL NOT NULL,
    cnss_salarie                    REAL NOT NULL,
    amo_salarie                     REAL NOT NULL,
    frais_professionnels            REAL NOT NULL,
    rni                             REAL NOT NULL,
    palier_ir                       INTEGER NOT NULL,
    ir_brut                         REAL NOT NULL,
    deduction_famille               REAL NOT NULL,
    ir_net                          REAL NOT NULL,
    net_avant_indemnites            REAL NOT NULL,
    net_pay                         REAL NOT NULL,
    cnss_patronal                   REAL NOT NULL,
    allocations_familiales_pat      REAL NOT NULL,
    amo_patronal                    REAL NOT NULL,
    tfp                             REAL NOT NULL,
    total_charges_patronales        REAL NOT NULL,
    cout_total_employeur            REAL NOT NULL,
    cout_horaire_chantier           REAL NOT NULL,
    generation_date                  TEXT NOT NULL,
    pdf_path                         TEXT,
    qr_payload_encrypted             TEXT,
    UNIQUE(employee_id, period_month, period_year)
);

CREATE INDEX IF NOT EXISTS idx_payslips_employee ON payslips(employee_id);
CREATE INDEX IF NOT EXISTS idx_payslips_period ON payslips(period_year, period_month);

CREATE TABLE IF NOT EXISTS management_summaries (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id               INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    period_month              INTEGER NOT NULL,
    period_year               INTEGER NOT NULL,
    monthly_employer_cost     REAL NOT NULL,
    conges_payes_jours        REAL NOT NULL,
    jours_feries              REAL NOT NULL,
    heures_par_jour           REAL NOT NULL,
    heures_theoriques_annuelles REAL NOT NULL,
    total_annual_cost         REAL NOT NULL,
    non_productive_hours      REAL NOT NULL,
    actual_productive_hours   REAL NOT NULL,
    theoretical_hourly_cost   REAL NOT NULL,
    real_productive_hourly_cost REAL NOT NULL,
    friction_coefficient      REAL NOT NULL,
    markup_pct                REAL NOT NULL,
    generation_date           TEXT NOT NULL,
    pdf_path                  TEXT,
    UNIQUE(employee_id, period_month, period_year)
);

CREATE INDEX IF NOT EXISTS idx_mgmt_summaries_employee ON management_summaries(employee_id);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- Employees -----------------------------------------------------

    def add_employee(self, emp: Employee) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO employees
                   (first_name, last_name, date_of_birth, marital_status, dependents_count,
                    cnss_number, cin, hire_date, default_rate_type, default_rate_amount,
                    active, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (emp.first_name, emp.last_name,
                 emp.date_of_birth.isoformat() if emp.date_of_birth else None,
                 emp.marital_status, emp.dependents_count, emp.cnss_number, emp.cin,
                 emp.hire_date.isoformat(), emp.default_rate_type, emp.default_rate_amount,
                 int(emp.active), now, now),
            )
            return cur.lastrowid

    def update_employee(self, emp: Employee) -> None:
        if emp.id is None:
            raise ValueError("Cannot update an employee with no id — use add_employee().")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """UPDATE employees SET
                   first_name=?, last_name=?, date_of_birth=?, marital_status=?,
                   dependents_count=?, cnss_number=?, cin=?, hire_date=?,
                   default_rate_type=?, default_rate_amount=?, active=?, updated_at=?
                   WHERE id=?""",
                (emp.first_name, emp.last_name,
                 emp.date_of_birth.isoformat() if emp.date_of_birth else None,
                 emp.marital_status, emp.dependents_count, emp.cnss_number, emp.cin,
                 emp.hire_date.isoformat(), emp.default_rate_type, emp.default_rate_amount,
                 int(emp.active), now, emp.id),
            )

    def delete_employee(self, employee_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM employees WHERE id=?", (employee_id,))

    def get_employee(self, employee_id: int) -> Optional[Employee]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
            return self._row_to_employee(row) if row else None

    def list_employees(self, active_only: bool = False) -> list[Employee]:
        query = "SELECT * FROM employees"
        if active_only:
            query += " WHERE active=1"
        query += " ORDER BY last_name, first_name"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
            return [self._row_to_employee(r) for r in rows]

    @staticmethod
    def _row_to_employee(row: sqlite3.Row) -> Employee:
        return Employee(
            id=row["id"], first_name=row["first_name"], last_name=row["last_name"],
            date_of_birth=date.fromisoformat(row["date_of_birth"]) if row["date_of_birth"] else None,
            marital_status=row["marital_status"], dependents_count=row["dependents_count"],
            cnss_number=row["cnss_number"], cin=row["cin"],
            hire_date=date.fromisoformat(row["hire_date"]),
            default_rate_type=row["default_rate_type"], default_rate_amount=row["default_rate_amount"],
            active=bool(row["active"]),
        )

    # -- Payslips --------------------------------------------------------

    def save_payslip(self, employee_id: int, result: PayrollResult, generation_date: str,
                      pdf_path: Optional[str] = None, qr_payload_encrypted: Optional[str] = None) -> int:
        """Upsert — regenerating the same employee/period overwrites, it does
        not duplicate (see UNIQUE(employee_id, period_month, period_year))."""
        inputs = result.inputs
        allowances_json = json.dumps([asdict(l) for l in result.allowances.lines], ensure_ascii=False)
        params = (
            employee_id, inputs.period_month, inputs.period_year, inputs.hours_worked,
            inputs.mode, inputs.unit, inputs.amount, inputs.dependents,
            result.seniority_years, result.seniority_rate, result.salaire_base,
            result.prime_anciennete, inputs.indemnite_logement, allowances_json,
            result.allowances.total_exonere, result.allowances.total_excedent,
            result.brut_imposable, result.cnss_salarie, result.amo_salarie,
            result.frais_professionnels, result.rni, result.palier_ir, result.ir_brut,
            result.deduction_famille, result.ir_net, result.net_avant_indemnites, result.net_pay,
            result.cnss_patronal, result.allocations_familiales_pat, result.amo_patronal,
            result.tfp, result.total_charges_patronales, result.cout_total_employeur,
            result.cout_horaire_chantier, generation_date, pdf_path, qr_payload_encrypted,
        )
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO payslips (
                    employee_id, period_month, period_year, hours_worked, input_mode, input_unit,
                    input_amount, dependents_count, seniority_years, seniority_rate, salaire_base,
                    prime_anciennete, indemnite_logement, allowances_json, total_exonere, total_excedent,
                    brut_imposable, cnss_salarie, amo_salarie, frais_professionnels, rni, palier_ir,
                    ir_brut, deduction_famille, ir_net, net_avant_indemnites, net_pay, cnss_patronal,
                    allocations_familiales_pat, amo_patronal, tfp, total_charges_patronales,
                    cout_total_employeur, cout_horaire_chantier, generation_date, pdf_path, qr_payload_encrypted
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(employee_id, period_month, period_year) DO UPDATE SET
                    hours_worked=excluded.hours_worked, input_mode=excluded.input_mode,
                    input_unit=excluded.input_unit, input_amount=excluded.input_amount,
                    dependents_count=excluded.dependents_count, seniority_years=excluded.seniority_years,
                    seniority_rate=excluded.seniority_rate, salaire_base=excluded.salaire_base,
                    prime_anciennete=excluded.prime_anciennete, indemnite_logement=excluded.indemnite_logement,
                    allowances_json=excluded.allowances_json, total_exonere=excluded.total_exonere,
                    total_excedent=excluded.total_excedent, brut_imposable=excluded.brut_imposable,
                    cnss_salarie=excluded.cnss_salarie, amo_salarie=excluded.amo_salarie,
                    frais_professionnels=excluded.frais_professionnels, rni=excluded.rni,
                    palier_ir=excluded.palier_ir, ir_brut=excluded.ir_brut,
                    deduction_famille=excluded.deduction_famille, ir_net=excluded.ir_net,
                    net_avant_indemnites=excluded.net_avant_indemnites, net_pay=excluded.net_pay,
                    cnss_patronal=excluded.cnss_patronal,
                    allocations_familiales_pat=excluded.allocations_familiales_pat,
                    amo_patronal=excluded.amo_patronal, tfp=excluded.tfp,
                    total_charges_patronales=excluded.total_charges_patronales,
                    cout_total_employeur=excluded.cout_total_employeur,
                    cout_horaire_chantier=excluded.cout_horaire_chantier,
                    generation_date=excluded.generation_date, pdf_path=excluded.pdf_path,
                    qr_payload_encrypted=excluded.qr_payload_encrypted
                """,
                params,
            )
            row = conn.execute(
                "SELECT id FROM payslips WHERE employee_id=? AND period_month=? AND period_year=?",
                (employee_id, inputs.period_month, inputs.period_year),
            ).fetchone()
            return row["id"]

    def list_payslips_for_employee(self, employee_id: int, limit: int = 24) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT * FROM payslips WHERE employee_id=?
                   ORDER BY period_year DESC, period_month DESC LIMIT ?""",
                (employee_id, limit),
            ).fetchall()

    def get_payslip(self, payslip_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM payslips WHERE id=?", (payslip_id,)).fetchone()

    def delete_payslip(self, payslip_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM payslips WHERE id=?", (payslip_id,))

    # -- Management summaries ("Roger's Theorem" billing PDFs) -----------

    def save_management_summary(self, employee_id: int, result, generation_date: str,
                                  pdf_path: Optional[str] = None) -> int:
        """Upsert, same pattern as save_payslip — regenerating the same
        employee/period overwrites rather than duplicating."""
        inputs = result.inputs
        params = (
            employee_id, inputs.period_month, inputs.period_year, inputs.monthly_employer_cost,
            inputs.conges_payes_jours, inputs.jours_feries, inputs.heures_par_jour,
            inputs.heures_theoriques_annuelles, result.total_annual_cost, result.non_productive_hours,
            result.actual_productive_hours, result.theoretical_hourly_cost,
            result.real_productive_hourly_cost, result.friction_coefficient, result.markup_pct,
            generation_date, pdf_path,
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO management_summaries (
                    employee_id, period_month, period_year, monthly_employer_cost, conges_payes_jours,
                    jours_feries, heures_par_jour, heures_theoriques_annuelles, total_annual_cost,
                    non_productive_hours, actual_productive_hours, theoretical_hourly_cost,
                    real_productive_hourly_cost, friction_coefficient, markup_pct, generation_date, pdf_path
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(employee_id, period_month, period_year) DO UPDATE SET
                    monthly_employer_cost=excluded.monthly_employer_cost,
                    conges_payes_jours=excluded.conges_payes_jours, jours_feries=excluded.jours_feries,
                    heures_par_jour=excluded.heures_par_jour,
                    heures_theoriques_annuelles=excluded.heures_theoriques_annuelles,
                    total_annual_cost=excluded.total_annual_cost,
                    non_productive_hours=excluded.non_productive_hours,
                    actual_productive_hours=excluded.actual_productive_hours,
                    theoretical_hourly_cost=excluded.theoretical_hourly_cost,
                    real_productive_hourly_cost=excluded.real_productive_hourly_cost,
                    friction_coefficient=excluded.friction_coefficient, markup_pct=excluded.markup_pct,
                    generation_date=excluded.generation_date, pdf_path=excluded.pdf_path
                """,
                params,
            )
            row = conn.execute(
                "SELECT id FROM management_summaries WHERE employee_id=? AND period_month=? AND period_year=?",
                (employee_id, inputs.period_month, inputs.period_year),
            ).fetchone()
            return row["id"]

    def list_management_summaries_for_employee(self, employee_id: int, limit: int = 24) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT * FROM management_summaries WHERE employee_id=?
                   ORDER BY period_year DESC, period_month DESC LIMIT ?""",
                (employee_id, limit),
            ).fetchall()
