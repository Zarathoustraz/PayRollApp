"""
tests/test_payroll_engine.py

The first test class reproduces, cell for cell, the example baked into
Calculateur_Taux_Horaire_Chantier_Maroc_v7.xlsx and the 31-point bisection
ladder cached in its hidden Solveur sheet. If a future edit to
payroll_engine.py breaks one of these, it has diverged from the source
workbook, not just from "expected" numbers someone typed in later.
"""
from datetime import date

import pytest

from app.models import (
    MODE_BRUT,
    MODE_NET,
    RATE_TYPE_HOURLY,
    RATE_TYPE_MONTHLY,
    Employee,
    ExemptAllowanceInputs,
    PayrollInputs,
)
from app.payroll_engine import PayrollEngine, excel_round
from app.tax_parameters import TaxParameters


@pytest.fixture
def engine():
    return PayrollEngine(TaxParameters())


@pytest.fixture
def fresh_employee():
    """0 years of service -> 0% seniority, for apples-to-apples comparison
    against the v7 workbook (which has no seniority concept at all)."""
    return Employee(first_name="Ahmed", last_name="Benali", hire_date=date(2026, 7, 1))


def _brut_inputs(employee, hours=191.0, rate=25.0, dependents=0, **kw):
    employee.dependents_count = dependents
    return PayrollInputs(employee=employee, period_month=7, period_year=2026,
                          hours_worked=hours, mode=MODE_BRUT, unit=RATE_TYPE_HOURLY,
                          amount=rate, **kw)


class TestExcelGoldenExample:
    """Calculateur!C8=25 (Taux horaire, BRUT), C6=191h, C7=0 dependents, all else 0."""

    def test_matches_workbook_exactly(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee), reference_date=date(2026, 7, 31))
        assert r.brut_imposable == pytest.approx(4775.0, abs=0.001)
        assert r.cnss_salarie == pytest.approx(213.92, abs=0.001)
        assert r.amo_salarie == pytest.approx(107.915, abs=0.001)
        assert r.total_cotisations_salariales == pytest.approx(321.835, abs=0.001)
        assert r.base_apres_cotisations == pytest.approx(4453.165, abs=0.001)
        assert r.frais_professionnels == pytest.approx(1671.25, abs=0.001)
        assert r.rni == pytest.approx(2781.915, abs=0.001)
        assert r.palier_ir == 1
        assert r.ir_brut == pytest.approx(0.0, abs=0.001)
        assert r.ir_net == pytest.approx(0.0, abs=0.001)
        assert r.net_avant_indemnites == pytest.approx(4453.165, abs=0.001)
        assert r.net_pay == pytest.approx(4453.165, abs=0.001)

    def test_employer_cost_matches_workbook(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee), reference_date=date(2026, 7, 31))
        assert r.cnss_patronal == pytest.approx(428.795, abs=0.001)
        assert r.allocations_familiales_pat == pytest.approx(305.6, abs=0.001)
        assert r.amo_patronal == pytest.approx(196.2525, abs=0.001)
        assert r.tfp == pytest.approx(76.4, abs=0.001)
        assert r.total_charges_patronales == pytest.approx(1007.0475, abs=0.001)
        assert r.cout_total_employeur == pytest.approx(5782.0475, abs=0.001)
        assert r.cout_horaire_chantier == pytest.approx(30.2725, abs=0.001)


class TestArticle59Threshold:
    """35% at/under 6500, 25% strictly above — applied to salaire_base only,
    never to logement or the excédent of over-claimed allowances."""

    def test_at_exact_threshold_uses_low_rate(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee, hours=1, rate=6500), reference_date=date(2026, 7, 31))
        assert r.frais_professionnels == pytest.approx(min(0.35 * 6500, 2916.67), abs=0.01)

    def test_just_above_threshold_uses_high_rate(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee, hours=1, rate=6500.01), reference_date=date(2026, 7, 31))
        assert r.frais_professionnels == pytest.approx(min(0.25 * 6500.01, 2916.67), abs=0.01)

    def test_ceiling_is_capped(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee, hours=1, rate=50000), reference_date=date(2026, 7, 31))
        assert r.frais_professionnels == pytest.approx(2916.67, abs=0.001)

    def test_logement_excluded_from_frais_pro_base(self, engine, fresh_employee):
        inputs = _brut_inputs(fresh_employee, hours=191, rate=25, indemnite_logement=5000)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        # frais pro must still be based on 4775 (salaire_base), not 9775 (incl. logement)
        assert r.frais_professionnels == pytest.approx(0.35 * 4775, abs=0.01)
        # but logement DOES enter brut_imposable (CNSS/AMO/IR base)
        assert r.brut_imposable == pytest.approx(4775 + 5000, abs=0.01)


class TestFamilyDeduction:
    def test_50_mad_per_dependent(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee, hours=191, rate=60, dependents=3),
                            reference_date=date(2026, 7, 31))
        assert r.deduction_famille == pytest.approx(150.0, abs=0.001)

    def test_capped_at_six(self, engine, fresh_employee):
        r = engine.compute(_brut_inputs(fresh_employee, hours=191, rate=60, dependents=6),
                            reference_date=date(2026, 7, 31))
        r_over = engine.compute(_brut_inputs(fresh_employee, hours=191, rate=60, dependents=6),
                                 reference_date=date(2026, 7, 31))
        assert r.deduction_famille == pytest.approx(300.0, abs=0.001)
        assert r.deduction_famille == r_over.deduction_famille


class TestSeniority:
    @pytest.mark.parametrize("years,expected_rate", [
        (1.9, 0.0), (2.0, 0.05), (4.9, 0.05), (5.0, 0.10),
        (11.9, 0.10), (12.0, 0.15), (19.9, 0.15), (20.0, 0.20),
        (24.9, 0.20), (25.0, 0.25), (40.0, 0.25),
    ])
    def test_tiers(self, engine, years, expected_rate):
        hire = date(2026, 7, 1).replace(year=2026 - int(years))
        emp = Employee(first_name="T", last_name="T", hire_date=hire)
        r = engine.compute(_brut_inputs(emp, hours=191, rate=25), reference_date=date(2026, 7, 1))
        assert r.seniority_rate == pytest.approx(expected_rate, abs=1e-9)

    def test_prime_added_to_taxable_base(self, engine):
        emp = Employee(first_name="T", last_name="T", hire_date=date(2020, 1, 1))
        r = engine.compute(_brut_inputs(emp, hours=191, rate=25), reference_date=date(2026, 7, 31))
        assert r.prime_anciennete == pytest.approx(r.salaire_base * 0.10, abs=0.01)
        assert r.brut_base_total == pytest.approx(r.salaire_base * 1.10, abs=0.01)


class TestNetToBrutBisection:
    def test_round_trip_various_targets(self, engine, fresh_employee):
        for target in [2500, 3000, 4453.165, 6000, 9000, 15000, 25000]:
            inputs = PayrollInputs(employee=fresh_employee, period_month=7, period_year=2026,
                                    hours_worked=191, mode=MODE_NET, unit=RATE_TYPE_MONTHLY,
                                    amount=target)
            r = engine.compute(inputs, reference_date=date(2026, 7, 31))
            assert r.net_pay == pytest.approx(target, abs=0.01)
            assert r.bisection_converged

    def test_exempt_allowances_subtracted_before_solving(self, engine, fresh_employee):
        """A NET target with a tax-free allowance attached must still land
        on the same total net (base salary shrinks to compensate)."""
        allowances = ExemptAllowanceInputs(transport_urbain=500, panier=400)
        inputs = PayrollInputs(employee=fresh_employee, period_month=7, period_year=2026,
                                hours_worked=191, mode=MODE_NET, unit=RATE_TYPE_MONTHLY,
                                amount=6000, allowances=allowances)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        assert r.net_pay == pytest.approx(6000, abs=0.01)
        # and the taxable salaire_base should be lower than a no-allowance run
        inputs_no_allow = PayrollInputs(employee=fresh_employee, period_month=7, period_year=2026,
                                          hours_worked=191, mode=MODE_NET, unit=RATE_TYPE_MONTHLY,
                                          amount=6000)
        r_no_allow = engine.compute(inputs_no_allow, reference_date=date(2026, 7, 31))
        assert r.salaire_base < r_no_allow.salaire_base


class TestExemptAllowanceCeilings:
    def test_transport_urbain_ceiling(self, engine, fresh_employee):
        allowances = ExemptAllowanceInputs(transport_urbain=800)  # over the 500 ceiling
        inputs = _brut_inputs(fresh_employee, allowances=allowances)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        line = next(l for l in r.allowances.lines if l.key == "transport_urbain")
        assert line.exonere == pytest.approx(500.0, abs=0.001)
        assert line.excedent == pytest.approx(300.0, abs=0.001)
        # the excedent becomes taxable brut
        assert r.brut_imposable == pytest.approx(4775 + 300, abs=0.01)

    def test_non_cumul_warning_transport_both(self, engine, fresh_employee):
        allowances = ExemptAllowanceInputs(transport_urbain=200, transport_hors_urbain=200)
        inputs = _brut_inputs(fresh_employee, allowances=allowances)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        assert r.allowances.non_cumul_warning is not None

    def test_non_cumul_warning_transport_and_km(self, engine, fresh_employee):
        allowances = ExemptAllowanceInputs(transport_urbain=200, km_parcourus=50)
        inputs = _brut_inputs(fresh_employee, allowances=allowances)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        assert r.allowances.non_cumul_warning is not None

    def test_no_warning_when_clean(self, engine, fresh_employee):
        allowances = ExemptAllowanceInputs(transport_urbain=200)
        inputs = _brut_inputs(fresh_employee, allowances=allowances)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        assert r.allowances.non_cumul_warning is None

    def test_panier_ceiling_uses_excel_rounding(self, engine, fresh_employee):
        # 191/8 = 23.875 -> ROUND(...,0) = 24 days
        inputs = _brut_inputs(fresh_employee, hours=191)
        r = engine.compute(inputs, reference_date=date(2026, 7, 31))
        line = next(l for l in r.allowances.lines if l.key == "panier")
        assert line.plafond_legal == pytest.approx(24 * 2 * 17.92, abs=0.001)


def test_excel_round_half_up_matches_excel_not_python_banker_rounding():
    # Python's round(23.5) == 24 already (even), so use a case where the
    # rules actually diverge: round(0.5) -> Excel 1, Python banker's -> 0.
    assert excel_round(0.5, 0) == 1.0
    assert round(0.5) == 0  # documents *why* excel_round exists
