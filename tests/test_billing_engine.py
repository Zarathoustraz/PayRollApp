# -*- coding: utf-8 -*-
"""tests/test_billing_engine.py"""
from datetime import date

import pytest

from app.billing_engine import BillingCalculator
from app.models import BillingInputs, Employee
from app.tax_parameters import TaxParameters


@pytest.fixture
def calc():
    return BillingCalculator(TaxParameters())


@pytest.fixture
def employee():
    return Employee(first_name="Test", last_name="Employee", hire_date=date(2020, 1, 1))


class TestBillingMath:
    def test_default_parameters_worked_example(self, calc, employee):
        """18 paid-leave days + 14 holidays x 7.33h/day = 234.56 non-productive
        hours; 2288 - 234.56 = 2053.44 actual productive hours."""
        inputs = BillingInputs(
            employee=employee, period_month=7, period_year=2026,
            monthly_employer_cost=10000, conges_payes_jours=18, jours_feries=14,
            heures_par_jour=7.33, heures_theoriques_annuelles=2288,
        )
        r = calc.compute(inputs)
        assert r.total_annual_cost == pytest.approx(120000, abs=0.01)
        assert r.non_productive_hours == pytest.approx(234.56, abs=0.01)
        assert r.actual_productive_hours == pytest.approx(2053.44, abs=0.01)
        assert r.theoretical_hourly_cost == pytest.approx(120000 / 2288, abs=0.0001)
        assert r.real_productive_hourly_cost == pytest.approx(120000 / 2053.44, abs=0.0001)
        # Real cost must always exceed theoretical (fewer productive hours, same total cost)
        assert r.real_productive_hourly_cost > r.theoretical_hourly_cost
        assert r.friction_coefficient == pytest.approx(2288 / 2053.44, abs=0.0001)
        assert r.markup_pct == pytest.approx(2288 / 2053.44 - 1, abs=0.0001)
        assert r.markup_pct == pytest.approx(0.11426, abs=0.0001)

    def test_zero_non_productive_hours_means_costs_are_equal(self, calc, employee):
        inputs = BillingInputs(
            employee=employee, period_month=7, period_year=2026,
            monthly_employer_cost=8000, conges_payes_jours=0, jours_feries=0,
            heures_par_jour=8, heures_theoriques_annuelles=2288,
        )
        r = calc.compute(inputs)
        assert r.real_productive_hourly_cost == pytest.approx(r.theoretical_hourly_cost, abs=1e-9)
        assert r.friction_coefficient == pytest.approx(1.0, abs=1e-9)
        assert r.markup_pct == pytest.approx(0.0, abs=1e-9)

    def test_more_paid_leave_increases_the_markup(self, calc, employee):
        base = BillingInputs(employee=employee, period_month=7, period_year=2026,
                               monthly_employer_cost=9000, conges_payes_jours=18,
                               jours_feries=14, heures_par_jour=7.33, heures_theoriques_annuelles=2288)
        more_leave = BillingInputs(employee=employee, period_month=7, period_year=2026,
                                     monthly_employer_cost=9000, conges_payes_jours=30,
                                     jours_feries=14, heures_par_jour=7.33, heures_theoriques_annuelles=2288)
        r_base = calc.compute(base)
        r_more = calc.compute(more_leave)
        assert r_more.markup_pct > r_base.markup_pct

    def test_infeasible_inputs_raise_clear_error(self, calc, employee):
        inputs = BillingInputs(
            employee=employee, period_month=7, period_year=2026,
            monthly_employer_cost=9000, conges_payes_jours=200, jours_feries=200,
            heures_par_jour=8, heures_theoriques_annuelles=2288,
        )
        with pytest.raises(ValueError, match="productives réelles"):
            calc.compute(inputs)

    def test_zero_monthly_cost_raises_clear_error_not_zero_division(self, calc, employee):
        """Regression test: a freshly-created employee has
        default_rate_amount == 0, which used to reach a bare
        ZeroDivisionError deep in the friction-coefficient division — and
        because this fires inside a Qt-signal-connected slot in the GUI, an
        uncaught exception there aborts the whole process, not just this
        calculation. Must always raise a catchable ValueError instead."""
        inputs = BillingInputs(
            employee=employee, period_month=7, period_year=2026,
            monthly_employer_cost=0, conges_payes_jours=18, jours_feries=14,
            heures_par_jour=7.33, heures_theoriques_annuelles=2288,
        )
        with pytest.raises(ValueError, match="coût employeur mensuel"):
            calc.compute(inputs)

    def test_negative_monthly_cost_raises_clear_error(self, calc, employee):
        inputs = BillingInputs(
            employee=employee, period_month=7, period_year=2026,
            monthly_employer_cost=-500, conges_payes_jours=18, jours_feries=14,
            heures_par_jour=7.33, heures_theoriques_annuelles=2288,
        )
        with pytest.raises(ValueError, match="coût employeur mensuel"):
            calc.compute(inputs)

    def test_zero_theoretical_hours_raises_clear_error(self, calc, employee):
        inputs = BillingInputs(
            employee=employee, period_month=7, period_year=2026,
            monthly_employer_cost=9000, conges_payes_jours=0, jours_feries=0,
            heures_par_jour=8, heures_theoriques_annuelles=0,
        )
        with pytest.raises(ValueError, match="théoriques annuelles"):
            calc.compute(inputs)

    def test_default_inputs_for_employee_pulls_from_tax_parameters(self, employee):
        params = TaxParameters()
        calc = BillingCalculator(params)
        inputs = calc.default_inputs_for_employee(employee, 7, 2026, monthly_employer_cost=9500)
        assert inputs.conges_payes_jours == params.conges_payes_jours_an
        assert inputs.jours_feries == params.jours_feries_an
        assert inputs.heures_par_jour == params.heures_par_jour_travaille
        assert inputs.heures_theoriques_annuelles == params.heures_theoriques_annuelles
        r = calc.compute(inputs)
        assert r.actual_productive_hours > 0
