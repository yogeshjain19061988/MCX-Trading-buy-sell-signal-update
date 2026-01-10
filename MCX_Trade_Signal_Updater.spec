# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['MCX_Trade_Signal_Updater.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
    name='MCX_Trade_Signal_Updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MCX_Trade_Signal_Updater',
)

from PyInstaller.utils.hooks import collect_all
import pkg_resources

hiddenimports = []
datas = []
binaries = []

for pkg in pkg_resources.working_set:
    try:
        collected = collect_all(pkg.key)
        datas += collected[0]
        binaries += collected[1]
        hiddenimports += collected[2]
    except:
        pass
