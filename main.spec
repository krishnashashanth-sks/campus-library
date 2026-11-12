# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VSVersionInfo,
    VarFileInfo,
    VarStruct,
)

_spec_dir = Path(os.path.abspath(SPECPATH)) if "SPECPATH" in globals() else Path.cwd()
if str(_spec_dir) not in sys.path:
    sys.path.insert(0, str(_spec_dir))

import app_version


def _parse_version_quad(raw_ver: str) -> tuple[int, int, int, int]:
    cleaned = app_version.normalize_version(raw_ver)
    parts = [int(p) for p in cleaned.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


_build_ver = os.environ.get("LIBRARY_BUILD_VERSION", "").strip() or app_version.APP_VERSION
_ver_quad = _parse_version_quad(_build_ver)
_ver_str = ".".join(str(x) for x in _ver_quad)

_win_version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_ver_quad,
        prodvers=_ver_quad,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", app_version.APP_DEVELOPER),
                        StringStruct("FileDescription", app_version.APP_NAME),
                        StringStruct("FileVersion", _ver_str),
                        StringStruct("InternalName", "Library"),
                        StringStruct("LegalCopyright", f"Copyright (C) {app_version.APP_DEVELOPER}"),
                        StringStruct("OriginalFilename", "Library.exe"),
                        StringStruct("ProductName", app_version.APP_NAME),
                        StringStruct("ProductVersion", _ver_str),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

datas = [('assets', 'assets')]
datas += collect_data_files('barcode')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # Bundle static assets and package data files (such as python-barcode fonts)
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Library',
    console=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    version=_win_version_info,
    icon='assets/library_icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='main',
)
