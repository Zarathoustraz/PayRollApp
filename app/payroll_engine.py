"""
payroll_engine.py — La Matrice Fiscale.

This module is a line-for-line port of the formulas in
Calculateur_Taux_Horaire_Chantier_Maroc_v7.xlsx (sheets "Calculateur" and
the hidden "Solveur"), validated against the workbook's own cached values
before being written here (see tests/test_payroll_engine.py).

ONE deliberate addition beyond the workbook: seniority ("Ancienneté", see
SeniorityTier in tax_parameters.py). The v7 file has no such computation —
it was added per spec and is clearly isolated in `_prime_anciennete()` so
it is easy to strip out if that turns out not to be wanted.

Everything else below is the workbook, not a reinterpretation of it.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .models import (
    MODE_BRUT,
    MODE_NET,
    RATE_TYPE_HOURLY,
    ExemptAllowanceBreakdown,
    ExemptAllowanceLine,
    PayrollInputs,
    PayrollResult,
)
from .tax_parameters import TaxParameters


def excel_round(value: float, digits: int = 0) -> float:
    """
    Excel's ROUND() rounds half away from zero; Python's round() rounds half
    to even. They agree except exactly on the .5 boundary, but that boundary
    is exactly where ROUND(hours/8,0) can land (e.g. 191/8 = 23.875 -> no
    ambiguity today, but a future 188h month gives 23.5) — using the wrong
    rule there silently shifts the panier ceiling by one day's SMIG. Matching
    Excel's rule removes that risk entirely rather than hoping it never bites.
    """
    quant = Decimal(1).scaleb(-digits) if digits else Decimal(1)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


class PayrollEngine:
    """Stateless calculator: give it TaxParameters once, call compute() per payslip."""

    def __init__(self, params: TaxParameters):
        self.params = params

    # -- public API --------------------------------------------------------

    def compute(self, inputs: PayrollInputs, reference_date: date | None = None) -> PayrollResult:
        """
        Full computation for one payslip. `reference_date` is the date
        seniority is measured against — defaults to the last day of the
        payslip's period.
        """
        p = self.params
        if reference_date is None:
            reference_date = self._period_end(inputs.period_year, inputs.period_month)

        raw_monthly_equivalent = self._raw_input_monthly_equivalent(inputs)

        years = inputs.employee.years_of_service(reference_date)
        rate = p.seniority_rate(years)

        allowances = self._compute_allowances(inputs, raw_monthly_equivalent)

        iterations = 0
        converged = True
        if inputs.mode == MODE_BRUT:
            salaire_base = raw_monthly_equivalent
        else:
            target_net_total = raw_monthly_equivalent
            # Calculateur note: "En mode NET, le montant saisi est le NET
            # TOTAL final en poche, indemnités exonérées incluses" — so the
            # tax-free allowances must come out before the solver runs
            # (Solveur!B2 subtracts Calculateur!$F$43 the same way).
            target_for_solver = target_net_total - allowances.total_exonere
            salaire_base, iterations = self._bisect_salaire_base(
                target_for_solver, inputs, rate
            )
            check = self._cascade(salaire_base, inputs, rate, allowances.total_excedent)
            converged = abs(check["net_avant_indemnites"] - target_for_solver) < 0.01

        c = self._cascade(salaire_base, inputs, rate, allowances.total_excedent)

        result = PayrollResult(
            inputs=inputs,
            salaire_base=salaire_base,
            seniority_years=years,
            seniority_rate=rate,
            prime_anciennete=c["prime_anciennete"],
            brut_base_total=c["brut_base_total"],
            hours_worked=inputs.hours_worked,
            allowances=allowances,
            brut_imposable=c["brut_imposable"],
            cnss_salarie=c["cnss_salarie"],
            amo_salarie=c["amo_salarie"],
            total_cotisations_salariales=c["total_cotisations_salariales"],
            base_apres_cotisations=c["base_apres_cotisations"],
            frais_professionnels=c["frais_professionnels"],
            rni=c["rni"],
            palier_ir=c["palier_ir"],
            ir_brut=c["ir_brut"],
            deduction_famille=c["deduction_famille"],
            ir_net=c["ir_net"],
            net_avant_indemnites=c["net_avant_indemnites"],
            net_pay=c["net_avant_indemnites"] + allowances.total_exonere,
            brut_horaire_equivalent=(c["brut_base_total"] / inputs.hours_worked) if inputs.hours_worked else 0.0,
            net_horaire_equivalent=((c["net_avant_indemnites"] + allowances.total_exonere) / inputs.hours_worked) if inputs.hours_worked else 0.0,
            cnss_patronal=c["cnss_patronal"],
            allocations_familiales_pat=c["allocations_familiales_pat"],
            amo_patronal=c["amo_patronal"],
            tfp=c["tfp"],
            total_charges_patronales=c["total_charges_patronales"],
            cout_total_employeur=c["cout_total_employeur"],
            cout_horaire_chantier=(c["cout_total_employeur"] / inputs.hours_worked) if inputs.hours_worked else 0.0,
            bisection_iterations=iterations,
            bisection_converged=converged,
        )
        return result

    # -- input normalisation ------------------------------------------------

    @staticmethod
    def _raw_input_monthly_equivalent(inputs: PayrollInputs) -> float:
        """Mirrors Calculateur!C12's BRUT branch / Solveur!B2's inner term:
        converts an hourly entry to a monthly figure; a global entry passes
        through unchanged. Used both as salaire_base in BRUT mode and as the
        raw NET target in NET mode."""
        if inputs.unit == RATE_TYPE_HOURLY:
            return inputs.amount * inputs.hours_worked
        return inputs.amount

    @staticmethod
    def _period_end(year: int, month: int) -> date:
        if month == 12:
            return date(year, 12, 31)
        from datetime import timedelta
        return date(year, month + 1, 1) - timedelta(days=1)

    # -- ⑤ Indemnités exonérées ---------------------------------------------

    def _compute_allowances(self, inputs: PayrollInputs, raw_monthly_equivalent: float) -> ExemptAllowanceBreakdown:
        p = self.params
        a = inputs.allowances
        lines: list[ExemptAllowanceLine] = []

        def bounded(key, label, demande, plafond):
            exonere = min(demande, plafond)
            excedent = max(demande - plafond, 0.0)
            lines.append(ExemptAllowanceLine(key, label, demande, plafond, exonere, excedent))

        # Transport domicile-travail (urbain / hors périmètre urbain) — Calculateur!B36:G37
        bounded("transport_urbain", "Transport domicile-travail (urbain)",
                 a.transport_urbain, p.transport_urbain_plafond)
        bounded("transport_hors_urbain", "Transport domicile-travail (hors périmètre urbain)",
                 a.transport_hors_urbain, p.transport_hors_urbain_plafond)

        # Indemnité kilométrique — Calculateur!B38:G38. C38 is a KM count, not
        # MAD; E38 = C38*ik_taux is simultaneously "the ceiling" and "the
        # claimed amount" in the source sheet (F38=E38, G38 hardcoded 0) —
        # there is no over-claim scenario coded for this row, so it is always
        # fully exempt at the computed rate.
        km_amount = a.km_parcourus * p.indemnite_km_taux
        lines.append(ExemptAllowanceLine(
            "indemnite_kilometrique", "Indemnité kilométrique",
            montant_demande=km_amount, plafond_legal=km_amount,
            exonere=km_amount, excedent=0.0,
        ))

        # Prime de panier — Calculateur!B39:G39 — ceiling = estimated days
        # worked (hours/8, Excel-rounded) x 2x SMIG horaire/day.
        jours_estimes = excel_round(inputs.hours_worked / 8, 0)
        panier_plafond = jours_estimes * p.panier_multiplicateur_smig * p.smig_horaire
        bounded("panier", "Prime de panier", a.panier, panier_plafond)

        # Prime de salissure / bleu de travail — Calculateur!B40:G40
        bounded("salissure", "Prime de salissure / bleu de travail",
                 a.salissure, p.salissure_plafond)

        # Prime d'outillage — Calculateur!B41:G41
        bounded("outillage", "Prime d'outillage (ouvrier propriétaire de ses outils)",
                 a.outillage, p.outillage_plafond)

        # Indemnité de représentation — Calculateur!B42:G42. The source
        # formula (E42) bases the 10% ceiling on the RAW monthly-equivalent
        # input (C8-derived), not on the resolved Brut — this sidesteps a
        # circular reference in the original sheet (E42 feeds into F43,
        # which the NET-mode solver needs *before* Brut is known). Faithfully
        # reproduced here: in NET mode this ceiling is therefore based on the
        # requested net target, not on the eventual gross — a quirk
        # inherited from the workbook, not introduced here.
        repr_plafond = p.representation_taux * raw_monthly_equivalent
        bounded("representation", "Indemnité de représentation", a.representation, repr_plafond)

        total_exonere = sum(l.exonere for l in lines)
        total_excedent = sum(l.excedent for l in lines)

        # ⚠ Alerte non-cumul — Calculateur!C45
        warning = None
        if a.transport_urbain > 0 and a.transport_hors_urbain > 0:
            warning = "Transport urbain ET hors-urbain actifs à la fois — non-cumul violé !"
        elif (a.transport_urbain > 0 or a.transport_hors_urbain > 0) and a.km_parcourus > 0:
            warning = "Transport ET Indemnité kilométrique actifs à la fois — non-cumul violé !"

        return ExemptAllowanceBreakdown(lines=lines, total_exonere=total_exonere,
                                          total_excedent=total_excedent, non_cumul_warning=warning)

    # -- ③④ the cascade -------------------------------------------------

    def _prime_anciennete(self, salaire_base: float, seniority_rate: float) -> float:
        """Claude's addition (see module docstring) — not in v7."""
        return salaire_base * seniority_rate

    def _cascade(self, salaire_base: float, inputs: PayrollInputs, seniority_rate: float,
                 total_excedent: float) -> dict:
        """
        The heart of the model. Mirrors Calculateur!C19:C30 (and, cell for
        cell, Solveur!E:L for a given Mid). `salaire_base` is the one free
        variable — everything else here is a pure function of it plus the
        already-known allowance/employee inputs.
        """
        p = self.params

        prime_anciennete = self._prime_anciennete(salaire_base, seniority_rate)
        brut_base_total = salaire_base + prime_anciennete  # generalises Calculateur!C12

        # Calculateur!C19 = C12 + F7(logement) + G43(excédent des indemnités)
        brut_imposable = brut_base_total + inputs.indemnite_logement + total_excedent

        # Calculateur!C20/C21
        cnss_salarie = p.cnss_taux_salarie * min(brut_imposable, p.cnss_plafond_mensuel)
        amo_salarie = p.amo_taux_salarie * brut_imposable
        total_cotisations_salariales = cnss_salarie + amo_salarie

        # Calculateur!C23
        base_apres_cotisations = brut_imposable - total_cotisations_salariales

        # Calculateur!C24 — Art. 59 CGI: threshold test AND rate base are
        # BOTH brut_base_total (i.e. salary + ancienneté, excluding logement
        # and any excédent) — confirmed against the workbook's own bisection
        # ladder (iteration where Mid=6250 <= 6500 gives Frais pro = 0.35 x
        # 6250 exactly, not 0.35 x SBI).
        fp_rate = p.fp_taux_bas if brut_base_total <= p.fp_seuil else p.fp_taux_haut
        frais_professionnels = min(fp_rate * brut_base_total, p.fp_plafond_mensuel)

        # Calculateur!C25
        rni = base_apres_cotisations - frais_professionnels

        # Calculateur!C26/C27
        ir_brut, palier_ir = p.ir_brut(rni)

        # Calculateur!C28/C29
        deduction_famille = p.charge_famille_deduction * min(inputs.dependents, p.charge_famille_max_personnes)
        ir_net = max(0.0, ir_brut - deduction_famille)

        # Calculateur!C30
        net_avant_indemnites = brut_imposable - total_cotisations_salariales - ir_net

        # Calculateur!④ — coût employeur
        cnss_patronal = p.cnss_taux_patronal * min(brut_imposable, p.cnss_plafond_mensuel)
        allocations_familiales_pat = p.allocations_familiales_patronal * brut_imposable
        amo_patronal = p.amo_taux_patronal * brut_imposable
        tfp = p.tfp_taux * brut_imposable
        total_charges_patronales = cnss_patronal + allocations_familiales_pat + amo_patronal + tfp
        cout_total_employeur = brut_imposable + total_charges_patronales  # + total_exonere, added by caller

        return dict(
            prime_anciennete=prime_anciennete, brut_base_total=brut_base_total,
            brut_imposable=brut_imposable, cnss_salarie=cnss_salarie, amo_salarie=amo_salarie,
            total_cotisations_salariales=total_cotisations_salariales,
            base_apres_cotisations=base_apres_cotisations, frais_professionnels=frais_professionnels,
            rni=rni, palier_ir=palier_ir, ir_brut=ir_brut, deduction_famille=deduction_famille,
            ir_net=ir_net, net_avant_indemnites=net_avant_indemnites,
            cnss_patronal=cnss_patronal, allocations_familiales_pat=allocations_familiales_pat,
            amo_patronal=amo_patronal, tfp=tfp, total_charges_patronales=total_charges_patronales,
            cout_total_employeur=cout_total_employeur,
        )

    # -- Net -> Brut bisection (hidden "Solveur" sheet) ----------------------

    def _bisect_salaire_base(self, target_for_solver: float, inputs: PayrollInputs,
                               seniority_rate: float) -> tuple[float, int]:
        """
        30-iteration bisection, exactly as Solveur!B5:L35: start at
        [0, 200000], evaluate net_avant_indemnites(mid) at each step, and
        narrow toward whichever half must contain the answer (net(brut) is
        monotonically increasing, so this always converges). The workbook
        takes the 31st midpoint (row 35, iteration "30") as final without a
        closing refinement — reproduced identically below.
        """
        p = self.params
        lo, hi = p.solver_lo, p.solver_hi
        mid = (lo + hi) / 2
        for i in range(p.solver_iterations + 1):  # iteration 0 .. solver_iterations
            c = self._cascade(mid, inputs, seniority_rate, total_excedent=self._excedent_only(inputs))
            net_calc = c["net_avant_indemnites"]
            if i < p.solver_iterations:
                if net_calc < target_for_solver:
                    lo = mid
                else:
                    hi = mid
                mid = (lo + hi) / 2
        return mid, p.solver_iterations + 1

    def _excedent_only(self, inputs: PayrollInputs) -> float:
        """total_excedent doesn't depend on salaire_base, so it's cheap to
        recompute per bisection step rather than thread an extra parameter
        through every call — kept as a tiny helper for readability."""
        raw = self._raw_input_monthly_equivalent(inputs)
        return self._compute_allowances(inputs, raw).total_excedent
