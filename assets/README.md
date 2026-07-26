# assets/

Optional branding files, picked up automatically if present:

- `logo.png` — shown in the top-left of the payslip header, next to the
  company name. Recommended: square, transparent background, ~500×500px.
  If absent, the header just shows the company name/address as text
  (this is the default — no logo is shipped with the app).
- `icon.ico` — used as the .exe's Windows icon by the PyInstaller build
  (see `payroll_app.spec`). If absent, PyInstaller falls back to its own
  default icon.

Both are entirely optional — the app and the build work without them.
