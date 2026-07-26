"""
tax_parameters.py — Every rate, threshold and ceiling the payroll engine
uses, extracted cell-for-cell from Calculateur_Taux_Horaire_Chantier_Maroc_v7.xlsx
(sheet "Paramètres", hidden sheet "Solveur").

Each field below is annotated with the exact source cell so the numbers can
be re-verified against a future version of the workbook. These values
change with each Loi de Finances — this module loads them from
data/parametres_paie.json at runtime (created on first launch from the
DEFAULTS below) specifically so an update never requires touching code,
only that file.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class IRBracket:
    """One row of Paramètres!A24:E29 — the monthly IR schedule."""
    upper_bound: float   # Paramètres!C{row}  ("À" — inf for the last bracket)
    rate: float           # Paramètres!D{row}  ("Taux")
    deduction: float      # Paramètres!E{row}  ("Somme à déduire")


@dataclass(frozen=True)
class SeniorityTier:
    """One step of the seniority-bonus schedule (Claude's addition — this
    computation does not exist anywhere in the v7 workbook; see README)."""
    min_years: float
    rate: float


@dataclass
class TaxParameters:
    # ① Cotisations salariales — Paramètres!B5:B7
    cnss_taux_salarie: float = 0.0448          # B5 — Source: cnss.ma / clicpaie.ma, 2026
    cnss_plafond_mensuel: float = 6000.0        # B6 — plafond de cotisation CNSS
    amo_taux_salarie: float = 0.0226            # B7 — non plafonné

    # ② Cotisations patronales — Paramètres!B10:B13
    cnss_taux_patronal: float = 0.0898          # B10 — plafonné au même seuil (B6)
    allocations_familiales_patronal: float = 0.064   # B11 — non plafonné
    amo_taux_patronal: float = 0.0411           # B12 — non plafonné, dont AMO-Tadamoun
    tfp_taux: float = 0.016                     # B13 — Taxe de Formation Professionnelle

    # ③ Frais professionnels / abattement Art. 59 CGI — Paramètres!B16:B19
    fp_seuil: float = 6500.0                    # B16 — seuil de bascule (~78 000 MAD/an)
    fp_taux_bas: float = 0.35                   # B17 — taux si base <= seuil
    fp_taux_haut: float = 0.25                  # B18 — taux si base > seuil
    fp_plafond_mensuel: float = 2916.67         # B19 — 35 000 MAD/an ÷ 12

    # ④ Barème IR mensuel — Paramètres!A24:E29 (6 tranches)
    bareme_ir: tuple = (
        IRBracket(3333.33, 0.00, 0.00),
        IRBracket(5000.00, 0.10, 333.33),
        IRBracket(6666.67, 0.20, 833.33),
        IRBracket(8333.33, 0.30, 1500.00),
        IRBracket(15000.00, 0.34, 1833.33),
        IRBracket(float("inf"), 0.37, 2283.33),
    )

    # ⑤ Déduction charges de famille — Paramètres!B34:B35
    charge_famille_deduction: float = 50.0      # B34 — MAD/mois/personne (600 MAD/an LF2026 ÷ 12)
    charge_famille_max_personnes: int = 6       # B35

    # ⑥ Temps de travail — Paramètres!B38
    heures_legales_mensuelles: float = 191.0    # 2288h/an (44h/sem, Code du travail) ÷ 12

    # ⑦ Indemnités exonérées — Paramètres!B41:B48
    smig_horaire: float = 17.92                 # B41 — Décret n° 2.25.983, B.O. n°7469, 2026
    transport_urbain_plafond: float = 500.0     # B42
    transport_hors_urbain_plafond: float = 750.0  # B43
    indemnite_km_taux: float = 3.0               # B44 — MAD/km, véhicule personnel justifié
    panier_multiplicateur_smig: float = 2.0      # B45 — × SMIG horaire/jour travaillé
    salissure_plafond: float = 210.0             # B46
    outillage_plafond: float = 100.0             # B47
    representation_taux: float = 0.10            # B48 — % du salaire de base mensuel

    # Bisection solver (hidden "Solveur" sheet) — Solveur!B5/C5, 30 refinement steps
    solver_lo: float = 0.0
    solver_hi: float = 200000.0
    solver_iterations: int = 30

    # ⑧ Facturation / Rentabilité ("Roger's Theorem") — Claude's addition,
    # NOT present in v7. See billing_engine.py. Annual reference figure
    # (2288h) is the standard 44h/week x 52 weeks legal ceiling — it does
    # not need to reconcile exactly with heures_legales_mensuelles x 12
    # (191 x 12 = 2292): one is a per-payslip default, the other an annual
    # planning constant, and real calendars don't divide evenly either way.
    conges_payes_jours_an: float = 18.0          # jours ouvrables/an
    jours_feries_an: float = 14.0                # jours fériés chômés payés/an
    heures_par_jour_travaille: float = 7.33      # 44h/6j ; utiliser 8.0 si semaine de 5j
    heures_theoriques_annuelles: float = 2288.0  # 44h/sem x 52 sem, Code du Travail

    # Seniority bonus ("Ancienneté") — NOT present in v7; added per spec.
    # Applied to salaire_base only, standard Code du Travail Art. 350 tiers.
    seniority_tiers: tuple = (
        SeniorityTier(2, 0.05),
        SeniorityTier(5, 0.10),
        SeniorityTier(12, 0.15),
        SeniorityTier(20, 0.20),
        SeniorityTier(25, 0.25),
    )

    def seniority_rate(self, years_of_service: float) -> float:
        rate = 0.0
        for tier in self.seniority_tiers:
            if years_of_service >= tier.min_years:
                rate = tier.rate
        return rate

    def ir_brut(self, rni: float) -> tuple[float, int]:
        """Returns (ir_brut, palier 1-6) — mirrors Calculateur!C26/C27."""
        for idx, bracket in enumerate(self.bareme_ir, start=1):
            if rni <= bracket.upper_bound:
                return max(0.0, rni * bracket.rate - bracket.deduction), idx
        last = self.bareme_ir[-1]
        return max(0.0, rni * last.rate - last.deduction), len(self.bareme_ir)

    # -- persistence -----------------------------------------------------

    def to_json_dict(self) -> dict:
        d = asdict(self)
        d["bareme_ir"] = [asdict(b) for b in self.bareme_ir]
        d["seniority_tiers"] = [asdict(t) for t in self.seniority_tiers]
        return d

    @classmethod
    def from_json_dict(cls, d: dict) -> "TaxParameters":
        d = dict(d)
        d["bareme_ir"] = tuple(IRBracket(**b) for b in d.get("bareme_ir", []))
        d["seniority_tiers"] = tuple(SeniorityTier(**t) for t in d.get("seniority_tiers", []))
        return cls(**d)

    @classmethod
    def load(cls, path: Path) -> "TaxParameters":
        """Load from JSON, creating the file with v7 defaults if absent."""
        if not path.exists():
            params = cls()
            params.save(path)
            return params
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json_dict(json.load(f))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json_dict(), f, ensure_ascii=False, indent=2)
