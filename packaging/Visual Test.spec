# -*- mode: python ; coding: utf-8 -*-
# noinspection PyAll
"""PyInstaller spec for the Visual Test harness app bundle."""
import os
from PyInstaller.utils.hooks import collect_all

# Paths are relative to spec file location (packaging/), so go up one level
_root = os.path.join(SPECPATH, '..')

datas = [(os.path.join(_root, '_build', 'runtime_content'), '_runtime_content')]
binaries = []
hiddenimports = []

# Collect wxPython dependencies
tmp_ret = collect_all('wx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Collect tesserocr shared library and its cysignals dependency
tmp_ret = collect_all('tesserocr')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('cysignals')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(_root, 'scripts', 'visual_test.py')],
    pathex=[_root],  # Project root so 'app' package is found
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Visual Test',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    upx=False,
    upx_exclude=[],
    name='Visual Test',
)
app = BUNDLE(
    coll,
    name='Visual Test.app',
    icon=os.path.join(_root, '_build', 'runtime_content', 'icon.icns'),
    bundle_identifier='com.greetingcards.visualtest',
)
