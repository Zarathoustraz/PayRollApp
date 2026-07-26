"""
config.py — Centralised configuration for the Chantier Maroc Payroll application.

Handles filesystem paths (which must work both when running from source and
when frozen into a single-file PyInstaller .exe), the .env-based Fernet key
used to encrypt payslip QR payloads, and the editable "company" placeholder
block that appears on every generated PDF.

Only this module should know about `sys.frozen` / PyInstaller — every other
module just asks `config` for a path.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv, set_key
import os


APP_NAME = "Calculateur Paie Chantier"
APP_VERSION = "1.0.0"
ORG_NAME = "IsolReve"


def _base_dir() -> Path:
    """
    Directory the app should treat as "home" for its data files.

    - Running from source: the project root (parent of this app/ package).
    - Running as a PyInstaller --onefile .exe: sys.executable's directory,
      NOT sys._MEIPASS (which is a temporary extraction folder that is wiped
      after the process exits — writing the SQLite DB or the Fernet key
      there would silently lose data between runs).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR: Path = _base_dir()
DATA_DIR: Path = BASE_DIR / "data"
OUTPUT_DIR: Path = DATA_DIR / "bulletins"
DB_PATH: Path = DATA_DIR / "payroll.db"
ENV_PATH: Path = BASE_DIR / ".env"
# Tracked/editable, unlike DATA_DIR (runtime state — DB + generated PDFs,
# both gitignored): this file is meant to be inspected and versioned.
PARAMETERS_PATH: Path = BASE_DIR / "parametres_paie.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Fernet key — persisted in .env as FERNET_KEY. Generated on first launch.
# ---------------------------------------------------------------------------


def get_or_create_fernet_key() -> bytes:
    """
    Read FERNET_KEY from .env, creating both the file and the key on first
    run. The key encrypts the JSON payload embedded in every payslip's QR
    code, so losing it makes previously issued QR codes unverifiable —
    back up the .env file the same way you would back up the database.
    """
    from cryptography.fernet import Fernet

    if not ENV_PATH.exists():
        ENV_PATH.touch()
    load_dotenv(ENV_PATH)

    key = os.environ.get("FERNET_KEY")
    if key:
        return key.encode("utf-8")

    new_key = Fernet.generate_key()
    set_key(str(ENV_PATH), "FERNET_KEY", new_key.decode("utf-8"))
    os.environ["FERNET_KEY"] = new_key.decode("utf-8")
    return new_key


# ---------------------------------------------------------------------------
# Company placeholder block — shown in the PDF header. Edit freely; nothing
# in the tax engine depends on these values.
# ---------------------------------------------------------------------------


@dataclass
class CompanyInfo:
    name: str = "ISOL RÊVE"
    activity: str = "Isolation thermique industrielle & chaudronnerie"
    address: str = "Bouskoura, Maroc"
    ice: str = ""            # Identifiant Commun de l'Entreprise — à compléter
    cnss_affiliation: str = ""  # Numéro d'affiliation CNSS employeur — à compléter
    # Resolved against _base_dir(), NOT __file__: under PyInstaller --onefile,
    # __file__ would point inside the ephemeral per-run extraction folder
    # (sys._MEIPASS), which is wiped after the process exits. Using
    # _base_dir() means dropping assets/logo.png next to the built .exe
    # picks it up immediately — no rebuild required to change branding.
    logo_path: str = field(default_factory=lambda: str(_base_dir() / "assets" / "logo.png"))


DEFAULT_COMPANY = CompanyInfo()
