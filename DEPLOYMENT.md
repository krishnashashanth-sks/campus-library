# Deployment & Release Guide

This repository uses an automated CI/CD pipeline on GitHub Actions to build, verify, and publish the Windows desktop installer (`LibraryInstaller.exe`) and the in-app auto-updater package (`Library-Windows.zip`).

## Repository Deployment Structure

```text
.github/
├── dependabot.yml                 # Weekly dependency & action update PRs
└── workflows/
    ├── ci.yml                     # Runs tests & preview packaging on pushes/PRs to main
    └── release.yml                # Builds & publishes GitHub Releases on v* tags
scripts/
└── build_windows.ps1              # Unified PyInstaller + ZIP + Inno Setup build script
tests/
└── test_release_readiness.py      # Headless release-integrity & updater safety tests
app_version.py                     # Application version source of truth
main.spec                          # PyInstaller bundle specification
installer_scipt.iss                # Inno Setup installer script (accepts /DAppVersion=...)
requirements.txt                   # Core runtime dependencies
requirements-dev.txt               # Runtime + PyInstaller build dependencies
requirements-services.txt          # Optional Gmail SMTP & Google Drive backup dependencies
```

## How Releases Work

### 1. Continuous Integration (`.github/workflows/ci.yml`)
Every push or pull request targeting `main` automatically:
1. Bytecode-compiles all Python modules (`python -m compileall -q .`).
2. Runs `tests/test_release_readiness.py` (validating versions, updater archive extraction rules, `BYPASS_LOGIN = False`, database initialization, and packaging assets).
3. Builds `LibraryInstaller.exe`, `Library-Windows.zip`, and `SHA256SUMS.txt` on `windows-latest` and uploads a 7-day preview artifact.

### 2. Publishing an Official Release (`.github/workflows/release.yml`)
1. Update `APP_VERSION` in `app_version.py` (for example, `"2.0"` or `"2.1.0"`).
2. Commit and push your changes to `main`:
   ```powershell
   git add -A
   git commit -m "Release v2.0"
   git push origin main
   ```
3. Create and push a matching numeric version tag:
   ```powershell
   git tag v2.0
   git push origin v2.0
   ```
4. GitHub Actions automatically builds and publishes the **GitHub Release** containing:
   - `LibraryInstaller.exe` — Standalone Windows installer (installs into `%LOCALAPPDATA%\Programs\Library` so self-updates stay writable).
   - `Library-Windows.zip` — In-app auto-updater archive required by `update_service.py` (with `Library.exe` and `library_version.txt` at the ZIP root).
   - `SHA256SUMS.txt` — Cryptographic checksums for both binaries.

You can also trigger a **Draft** or **Pre-release** build manually from GitHub under **Actions → Release Windows Installer → Run workflow**.

## Building Locally on Windows

Run the same script used by CI:

```powershell
.\scripts\build_windows.ps1
```

Optional flags:
- `-Version 2.0` — Override the stamped installer and `library_version.txt` version.
- `-SkipInstaller` — Build only the PyInstaller bundle and `Library-Windows.zip` when Inno Setup 6 is not installed locally.
