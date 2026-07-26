# -*- mode: python ; coding: utf-8 -*-
"""
payroll_app.spec — optional, for local builds:  pyinstaller payroll_app.spec

CI (.github/workflows/build.yml) does NOT use this file — it calls
PyInstaller with plain --onefile --windowed flags, matching the project
spec exactly. This file exists for developers who want a reproducible,
tweakable local build (custom icon, hidden imports, excludes) without
retyping a long CLI command every time. Both approaches produce an
equivalent onefile, windowed .exe.
"""
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

# Note: assets/logo.png is intentionally NOT bundled via `datas` — it's read
# from next to the running .exe at runtime (see config.CompanyInfo.logo_path),
# so a logo can be swapped by dropping a file next to the built executable
# without rebuilding. icon.ico below is a different mechanism (embedded into
# the .exe's Windows resources at build time) and does need to exist here.
icon_path = root / "assets" / "icon.ico"

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "qrcode.image.pil",
        "PIL._tkinter_finder",  # harmless if unused; avoids a rare PIL/PyInstaller miss
        "cryptography.hazmat.backends.openssl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.testing"],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CalculateurPaieChantier",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # --windowed: no console window behind the GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
