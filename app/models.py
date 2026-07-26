"""
models.py — Plain data containers shared across the app.

No business logic lives here (that's payroll_engine.py) and no persistence
logic lives here (that's database.py) — these are the shapes that flow
between those two layers and the GUI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


RATE_TYPE_HOURLY = "hourly"
RATE_TYPE_MONTHLY = "monthly"

MODE_BRUT = "BRUT"
MODE_NET = "NET"

MARITAL_STATUSES = ["Célibataire", "Marié(e)", "Divorcé(e)", "Veuf(ve)"]


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------


@dataclass
class Employee:
    first_name: str
    last_name: str
    hire_date: date
    id: Optional[int] = None
    date_of_birth: Optional[date] = None
    marital_status: str = MARITAL_STATUSES[0]
    dependents_count: int = 0
    cnss_number: str = ""
    cin: str = ""
    default_rate_type: str = RATE_TYPE_HOURLY
    default_rate_amount: float = 0.0
    active: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def years_of_service(self, reference: date) -> float:
        """
        Years between hire_date and reference (>= 0), exact on the calendar
        anniversary — NOT days/365.25. That averaged divisor drifts by up to
        a day or two depending on how many leap years fall in the span, which
        is invisible for display but wrong for seniority-tier eligibility: an
        employee hired 2024-07-01 must read as *exactly* 2.0 on 2026-07-01,
        not 1.9986, or the 5% bonus starts a few days late.
        """
        if reference <= self.hire_date:
            return 0.0
        anniversary_this_year = self._anniversary_in(reference.year)
        if reference < anniversary_this_year:
            years = reference.year - self.hire_date.year - 1
            span_start = self._anniversary_in(reference.year - 1)
            span_end = anniversary_this_year
        else:
            years = reference.year - self.hire_date.year
            span_start = anniversary_this_year
            span_end = self._anniversary_in(reference.year + 1)
        span_days = (span_end - span_start).days
        elapsed_days = (reference - span_start).days
        fraction = (elapsed_days / span_days) if span_days else 0.0
        return years + fraction

    def _anniversary_in(self, year: int) -> date:
        """hire_date's month/day in the given year, sliding Feb 29 -> Feb 28
        when that year isn't a leap year."""
        try:
            return self.hire_date.replace(year=year)
        except ValueError:
            return self.hire_date.replace(year=year, day=28)


# ---------------------------------------------------------------------------
# Exempt allowances (Calculateur!⑤ — Indemnités exonérées)
# ---------------------------------------------------------------------------


@dataclass
class ExemptAllowanceInputs:
    """Raw amounts an employee is claiming this period, before ceilings."""
    transport_urbain: float = 0.0        # MAD/month
    transport_hors_urbain: float = 0.0   # MAD/month
    km_parcourus: float = 0.0            # km/month (NOT MAD — converted via ik_taux)
    panier: float = 0.0                  # MAD/month
    salissure: float = 0.0               # MAD/month
    outillage: float = 0.0               # MAD/month
    representation: float = 0.0          # MAD/month


@dataclass
class ExemptAllowanceLine:
    """One row of the ⑤ table after ceiling logic has been applied."""
    key: str
    label: str
    montant_demande: float
    plafond_legal: float
    exonere: float
    excedent: float


@dataclass
class ExemptAllowanceBreakdown:
    lines: list[ExemptAllowanceLine] = field(default_factory=list)
    total_exonere: float = 0.0
    total_excedent: float = 0.0
    non_cumul_warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Engine input / output
# ---------------------------------------------------------------------------


@dataclass
class PayrollInputs:
    employee: Employee
    period_month: int
    period_year: int
    hours_worked: float
    mode: str                      # MODE_BRUT | MODE_NET
    unit: str                      # RATE_TYPE_HOURLY | RATE_TYPE_MONTHLY
    amount: float                  # "Montant saisi" — meaning depends on mode/unit
    indemnite_logement: float = 0.0
    dependents_override: Optional[int] = None
    allowances: ExemptAllowanceInputs = field(default_factory=ExemptAllowanceInputs)

    @property
    def dependents(self) -> int:
        n = self.dependents_override if self.dependents_override is not None else self.employee.dependents_count
        return max(0, min(6, n))


@dataclass
class PayrollResult:
    """Full computed breakdown for one payslip — mirrors Calculateur!②③④⑤."""
    inputs: PayrollInputs

    # Salary construction
    salaire_base: float = 0.0
    seniority_years: float = 0.0
    seniority_rate: float = 0.0
    prime_anciennete: float = 0.0
    brut_base_total: float = 0.0       # salaire_base + prime_anciennete  (~Calculateur!C12, extended)
    hours_worked: float = 0.0

    # Exempt allowances
    allowances: ExemptAllowanceBreakdown = field(default_factory=ExemptAllowanceBreakdown)

    # Taxable base
    brut_imposable: float = 0.0        # ~C19

    # Employee deductions
    cnss_salarie: float = 0.0          # ~C20
    amo_salarie: float = 0.0           # ~C21
    total_cotisations_salariales: float = 0.0  # ~C22
    base_apres_cotisations: float = 0.0  # ~C23
    frais_professionnels: float = 0.0  # ~C24
    rni: float = 0.0                   # ~C25 (Revenu Net Imposable)
    palier_ir: int = 1                 # ~C26
    ir_brut: float = 0.0               # ~C27
    deduction_famille: float = 0.0     # ~C28
    ir_net: float = 0.0                # ~C29
    net_avant_indemnites: float = 0.0  # ~C30

    # Final pay
    net_pay: float = 0.0               # ~C13  (net_avant_indemnites + total_exonere)
    brut_horaire_equivalent: float = 0.0
    net_horaire_equivalent: float = 0.0

    # Employer cost (Calculateur!④)
    cnss_patronal: float = 0.0
    allocations_familiales_pat: float = 0.0
    amo_patronal: float = 0.0
    tfp: float = 0.0
    total_charges_patronales: float = 0.0
    cout_total_employeur: float = 0.0
    cout_horaire_chantier: float = 0.0

    # Solver diagnostics (only meaningful in NET mode)
    bisection_iterations: int = 0
    bisection_converged: bool = True


@dataclass
class Payslip:
    """Persisted record — see database.py for the schema this maps to."""
    id: Optional[int]
    employee_id: int
    period_month: int
    period_year: int
    result: PayrollResult
    generation_date: str
    pdf_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Billing / "Roger's Theorem" — real productive hourly cost for client billing
# ---------------------------------------------------------------------------


@dataclass
class BillingInputs:
    employee: Employee
    period_month: int
    period_year: int
    monthly_employer_cost: float
    conges_payes_jours: float
    jours_feries: float
    heures_par_jour: float
    heures_theoriques_annuelles: float


@dataclass
class BillingResult:
    inputs: BillingInputs
    total_annual_cost: float = 0.0
    non_productive_hours: float = 0.0
    actual_productive_hours: float = 0.0
    theoretical_hourly_cost: float = 0.0
    real_productive_hourly_cost: float = 0.0
    friction_coefficient: float = 0.0    # real / theoretical
    markup_pct: float = 0.0              # friction_coefficient - 1


@dataclass
class ManagementSummary:
    """Persisted record for a generated internal management-summary PDF."""
    id: Optional[int]
    employee_id: int
    period_month: int
    period_year: int
    result: BillingResult
    generation_date: str
    pdf_path: Optional[str] = None
