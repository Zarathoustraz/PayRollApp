# Calculateur de Paie — Chantier Maroc

Application de bureau (Windows 10/11) pour générer des bulletins de paie
PDF chiffrés et vérifiables, à partir de la logique fiscale du fichier
`Calculateur_Taux_Horaire_Chantier_Maroc_v7.xlsx`.

PyQt6 · SQLite · reportlab · cryptography (Fernet) · qrcode

---

## 1. Provenance du moteur de calcul — à lire avant tout

Chaque paramètre du moteur (`app/tax_parameters.py`, `app/payroll_engine.py`)
a été extrait **formule par formule** du classeur v7 (feuilles `Calculateur`,
`Paramètres`, et la feuille cachée `Solveur`), puis revalidé en reproduisant
exactement les valeurs mises en cache par Excel lui-même — voir
`tests/test_payroll_engine.py::TestExcelGoldenExample`, qui compare le
résultat du moteur à l'exemple intégré dans le classeur, au centime près, et
`TestNetToBrutBisection` qui rejoue les 31 points de la ladder de bissection
de la feuille `Solveur` un par un.

**Three things worth your attention explicitly:**

1. **L'ancienneté n'existe pas dans le fichier v7.** C'est un ajout fait sur
   votre demande (`app/tax_parameters.py::SeniorityTier`), isolé dans
   `PayrollEngine._prime_anciennete()`. Elle est ajoutée au salaire de base
   *avant* application des cotisations, de l'abattement Art. 59 et de l'IR —
   comme le serait n'importe quel élément de salaire imposable régulier.

2. **Les frais professionnels (Art. 59 CGI) excluent bien le logement**,
   conformément à ce que vous avez demandé — mais ce n'est *pas* parce que
   la feuille Excel les exclut par accident : la formule `Calculateur!C24`
   teste et applique le taux sur `C12` (salaire de base résolu), pas sur
   `C19` (brut imposable = base + logement + excédents). C'est délibéré et
   vérifié (`TestArticle59Threshold::test_logement_excluded_from_frais_pro_base`).

3. **L'indemnité de représentation (10 %)** est plafonnée, dans le fichier
   source, sur le montant brut *saisi tel quel* plutôt que sur le brut
   *résolu* — ce qui n'a d'importance qu'en mode NET (le plafond y est alors
   basé sur la cible NET saisie, pas sur le brut finalement calculé). C'est
   une caractéristique héritée du classeur original (qui évite ainsi une
   référence circulaire dans le solveur), reproduite à l'identique et
   documentée dans `PayrollEngine._compute_allowances()`. Concrètement,
   cette indemnité est rarement utilisée pour des ouvriers de chantier — mais
   si vous l'activez en mode NET, gardez ce comportement en tête.

4. **Le module Facturation (§9, "Théorème de Roger") ne fait pas partie du
   fichier v7** — c'est entièrement un ajout, isolé dans
   `app/billing_engine.py` et `app/gui/billing_tab.py`, sans effet sur le
   moteur de paie principal.

Le taux CNSS/AMO, le barème IR (6 tranches), les plafonds des indemnités
exonérées, et les seuils Art. 59 proviennent tous du fichier source sans
modification. Ils sont éditables sans toucher au code — voir §5.

---

## 2. Structure du projet

```
├── main.py                      # point d'entrée
├── app/
│   ├── config.py                 # chemins, clé Fernet (.env), infos société
│   ├── models.py                 # Employee, PayrollInputs/Result, Billing*, etc.
│   ├── tax_parameters.py         # tous les taux/seuils (v7 + ancienneté + facturation)
│   ├── payroll_engine.py         # La Matrice Fiscale — cascade + bissection
│   ├── billing_engine.py         # "Théorème de Roger" — coût horaire productif réel
│   ├── database.py               # SQLite (employees, payslips, management_summaries)
│   ├── crypto_utils.py           # Fernet + génération QR
│   ├── pdf_generator.py          # bulletin de paie (reportlab)
│   ├── management_pdf_generator.py  # résumé de gestion interne (reportlab)
│   ├── formatting.py             # formats FR (nombres, dates, mois)
│   ├── palette.py                # couleurs partagées GUI ⇄ PDF
│   └── gui/
│       ├── main_window.py
│       ├── employees_tab.py      # Tab 1 — Tableau de bord / Employés
│       ├── payroll_tab.py        # Tab 2 — Générateur de paie
│       ├── billing_tab.py        # Tab 3 — Rentabilité / Facturation
│       ├── employee_form.py      # panneau latéral (ajout/édition)
│       ├── widgets.py            # KPI cards, bannière d'alerte, etc.
│       └── styles.py             # QSS (palette corporate)
├── tests/
│   ├── test_payroll_engine.py    # 28 tests — moteur fiscal
│   ├── test_billing_engine.py    # 8 tests — moteur de facturation
│   └── test_gui_smoke.py         # 11 tests — GUI headless (offscreen)
├── parametres_paie.json          # paramètres fiscaux, éditables (§5)
├── requirements.txt
├── requirements-dev.txt          # + pytest, pyinstaller
├── payroll_app.spec              # build PyInstaller local (optionnel)
└── .github/workflows/build.yml   # CI : test + build .exe sur push vers main
```

---

## 3. Installation & lancement (développement)

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements-dev.txt
python main.py
```

Au premier lancement, l'application crée automatiquement :
- `data/payroll.db` — base SQLite (employés + bulletins)
- `.env` — contient `FERNET_KEY`, générée une seule fois
- `data/bulletins/` — dossier de sortie des PDF générés

**Sauvegardez `.env` avec `data/payroll.db`.** La clé chiffre le contenu des
QR codes : la perdre rend tous les QR déjà émis impossibles à vérifier (les
PDF eux-mêmes restent lisibles normalement — seule la vérification QR est
affectée).

## 4. Tests

```bash
pytest tests/ -v
```

47 tests : 28 sur le moteur fiscal (dont la reproduction exacte de l'exemple
et de la ladder de bissection du fichier v7), 8 sur le moteur de facturation,
11 sur l'intégration GUI (ajout/édition/suppression d'employé, recalcul en
direct, mode NET, génération de PDF de bout en bout sur les trois onglets)
— exécutés en mode `offscreen`, sans nécessiter d'affichage :

```bash
QT_QPA_PLATFORM=offscreen pytest tests/test_gui_smoke.py -v   # Linux/Mac
set QT_QPA_PLATFORM=offscreen && pytest tests\test_gui_smoke.py -v   # Windows cmd
```

## 5. Modifier les paramètres fiscaux (prochaine Loi de Finances)

`parametres_paie.json` (racine du projet) contient tous les taux, seuils et
le barème IR. Il est chargé au démarrage — modifiez-le et relancez
l'application, aucune recompilation n'est nécessaire :

```json
{
  "cnss_taux_salarie": 0.0448,
  "cnss_plafond_mensuel": 6000.0,
  "fp_seuil": 6500.0,
  "bareme_ir": [ { "upper_bound": 3333.33, "rate": 0.0, "deduction": 0.0 }, ... ],
  ...
}
```

## 6. Personnaliser l'en-tête du bulletin (logo, société)

`app/config.py::DEFAULT_COMPANY` — nom, activité, adresse (pré-rempli avec
Isol Rêve, à ajuster librement). Pour un logo : placez `assets/logo.png` **à
côté de l'exécutable** (pas besoin de rebuild — voir le commentaire dans
`config.py` sur pourquoi ce chemin est résolu par rapport à l'.exe et non au
bundle PyInstaller).

## 9. Rentabilité & Facturation ("Théorème de Roger")

Un troisième onglet, **Rentabilité / Facturation**, répond à une question
différente de celle du bulletin de paie : l'employeur paie 12 mois pleins
(2288 h théoriques/an) mais l'employé n'est productif ni pendant ses congés
payés ni pendant les jours fériés chômés — payés, mais non facturables.

```
Coût annuel total          = coût employeur mensuel x 12
Heures non-productives     = (congés payés + jours fériés) x heures/jour
Heures productives réelles = heures théoriques annuelles - heures non-productives
Coût horaire réel (plancher) = coût annuel total / heures productives réelles
Majoration plancher        = (coût réel / coût théorique naïf) - 1
```

**Décision de conception à connaître :** le résumé de gestion est généré en
tant que **fichier PDF séparé** (`Resume_Gestion_INTERNE_*.pdf`), et non
comme une page ajoutée au bulletin de paie. La demande initiale évoquait une
page "attachée après le bulletin, strictement pour un usage interne, à ne
pas remettre au salarié" — mais un PDF à plusieurs pages où l'une des pages
ne doit jamais être vue par son destinataire final repose entièrement sur le
fait que personne n'oublie jamais de la retirer avant impression ou envoi. Un
fichier distinct, au nom et à la mise en page sans ambiguïté (bandeau rouge
"CONFIDENTIEL" sur chaque page), élimine ce risque au lieu d'en dépendre.
Les deux documents sont générés depuis deux boutons distincts (onglets 2 et
3) — jamais dans le même flux.

Paramètres (`conges_payes_jours_an`, `jours_feries_an`,
`heures_par_jour_travaille`, `heures_theoriques_annuelles`) éditables dans
`parametres_paie.json` comme le reste, avec possibilité de les ajuster
ponctuellement dans l'onglet lui-même pour modéliser un scénario différent.

---

## 10. Build de l'exécutable Windows

**Automatique (recommandé) :** tout push sur `main` déclenche
`.github/workflows/build.yml`, qui teste puis construit
`CalculateurPaieChantier.exe` (onefile, windowed) via PyInstaller sur
`windows-latest`, téléchargeable depuis l'onglet *Actions* → l'exécution →
*Artifacts*.

**Local (Windows, optionnel) :**
```bash
pip install -r requirements-dev.txt
pyinstaller payroll_app.spec
# -> dist/CalculateurPaieChantier.exe
```
Le fichier `.spec` prend en charge une icône optionnelle
(`assets/icon.ico`) au moment du build — voir `assets/README.md`.

## 11. Vérification d'un bulletin (QR code)

Chaque PDF porte un QR code en bas à droite encodant, chiffré (Fernet), le
CIN, le nom complet, le net payé et la date. Le déchiffrer nécessite la même
clé `FERNET_KEY` que celle utilisée à la génération — un jeton altéré ou une
mauvaise clé échouent proprement au déchiffrement plutôt que de retourner
des données incorrectes (chiffrement authentifié), voir
`app/crypto_utils.py::PayslipQRCodec.decrypt`.

---

*Ce logiciel implémente une lecture technique du fichier v7 et de la
réglementation en vigueur telle que documentée dans ses formules ; il ne
remplace pas la validation d'un expert-comptable, en particulier lors d'un
changement de Loi de Finances.*
