# -*- coding: utf-8 -*-
"""
billing_engine.py — "Roger's Theorem": the employer pays for 12 full months
(2288 theoretical hours/year) but the employee is not productive for all of
them — paid leave and public holidays are paid but not billable. This module
answers: given what an employee actually costs per month, what's the REAL
hourly cost once you only count hours they're actually on site producing?

Entirely Claude's addition — no equivalent exists in the v7 workbook. Kept
in its own module (not payroll_engine.py) because it's a genuinely different
concern: annual billing strategy for project managers, not per-payslip tax
calculation for employees.
"""
from __future__ import annotations

from .models import BillingInputs, BillingResult
from .tax_parameters import TaxParameters


class BillingCalculator:
    def __init__(self, params: TaxParameters):
        self.params = params

    def compute(self, inputs: BillingInputs) -> BillingResult:
        if inputs.monthly_employer_cost <= 0:
            raise ValueError(
                "Le coût employeur mensuel doit être supérieur à 0 — utilisez "
                "« Recalculer depuis le taux par défaut » ou saisissez un montant."
            )
        if inputs.heures_theoriques_annuelles <= 0:
            raise ValueError("Les heures théoriques annuelles doivent être supérieures à 0.")

        total_annual_cost = inputs.monthly_employer_cost * 12
        non_productive_hours = (inputs.conges_payes_jours + inputs.jours_feries) * inputs.heures_par_jour
        actual_productive_hours = inputs.heures_theoriques_annuelles - non_productive_hours

        if actual_productive_hours <= 0:
            raise ValueError(
                "Heures productives réelles ≤ 0 : les congés payés + jours fériés saisis "
                "(en heures) dépassent les heures théoriques annuelles. Vérifiez les valeurs."
            )

        theoretical_hourly_cost = total_annual_cost / inputs.heures_theoriques_annuelles
        real_productive_hourly_cost = total_annual_cost / actual_productive_hours
        friction_coefficient = real_productive_hourly_cost / theoretical_hourly_cost

        return BillingResult(
            inputs=inputs,
            total_annual_cost=total_annual_cost,
            non_productive_hours=non_productive_hours,
            actual_productive_hours=actual_productive_hours,
            theoretical_hourly_cost=theoretical_hourly_cost,
            real_productive_hourly_cost=real_productive_hourly_cost,
            friction_coefficient=friction_coefficient,
            markup_pct=friction_coefficient - 1.0,
        )

    def default_inputs_for_employee(self, employee, period_month: int, period_year: int,
                                       monthly_employer_cost: float) -> BillingInputs:
        """Convenience: pre-fill the four site/company-wide parameters from
        TaxParameters, leaving only monthly_employer_cost caller-supplied
        (it depends on the specific employee's rate, not a fixed constant)."""
        p = self.params
        return BillingInputs(
            employee=employee, period_month=period_month, period_year=period_year,
            monthly_employer_cost=monthly_employer_cost,
            conges_payes_jours=p.conges_payes_jours_an,
            jours_feries=p.jours_feries_an,
            heures_par_jour=p.heures_par_jour_travaille,
            heures_theoriques_annuelles=p.heures_theoriques_annuelles,
        )
