# -*- coding: utf-8 -*-
"""gui/main_window.py — QMainWindow hosting the two tabs."""
from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from .. import config
from ..crypto_utils import PayslipQRCodec
from ..database import Database
from ..payroll_engine import PayrollEngine
from ..tax_parameters import TaxParameters
from .employees_tab import EmployeesTab
from .payroll_tab import PayrollTab
from .billing_tab import BillingTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} — {config.DEFAULT_COMPANY.name}")
        self.resize(1360, 860)

        self.db = Database(config.DB_PATH)
        self.tax_params = TaxParameters.load(config.PARAMETERS_PATH)
        self.engine = PayrollEngine(self.tax_params)
        self.qr_codec = PayslipQRCodec(config.get_or_create_fernet_key())

        self.employees_tab = EmployeesTab(self.db)
        self.payroll_tab = PayrollTab(self.db, self.engine, self.qr_codec)
        self.billing_tab = BillingTab(self.db, self.engine)
        # Any add/edit/delete in the Employees tab must refresh both the
        # Payroll and Facturation tabs' dropdowns, or they silently go stale.
        self.employees_tab.employees_changed.connect(self.payroll_tab.refresh_employees)
        self.employees_tab.employees_changed.connect(self.billing_tab.refresh_employees)

        tabs = QTabWidget()
        tabs.addTab(self.employees_tab, "Tableau de bord / Employés")
        tabs.addTab(self.payroll_tab, "Générateur de paie")
        tabs.addTab(self.billing_tab, "Rentabilité / Facturation")
        self.setCentralWidget(tabs)

        self._build_menu()
        self.statusBar().showMessage(
            f"Base de données : {config.DB_PATH.name}  •  Bulletins : {config.OUTPUT_DIR}"
        )

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Fichier")
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menu.addMenu("&Aide")
        about_action = QAction("À propos", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        QMessageBox.information(
            self, f"À propos de {config.APP_NAME}",
            f"{config.APP_NAME} — version {config.APP_VERSION}\n\n"
            f"Moteur de paie basé sur Calculateur_Taux_Horaire_Chantier_Maroc_v7.xlsx\n"
            f"Barème IR, cotisations et abattements paramétrables dans :\n{config.PARAMETERS_PATH}\n\n"
            f"{config.DEFAULT_COMPANY.name}",
        )
