# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import re, subprocess
__version__ = re.search(r'"(.+?)"', open('app/version.py').read()).group(1)
__commit__ = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()

datas = [('icon.png', '.'), ('help', 'help'), ('Drop Target Background.png', '.')]
binaries = []
hiddenimports = []

# Collect wxPython dependencies
tmp_ret = collect_all('wx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
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
    name='Greeting Cards',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='Greeting Cards',
)
app = BUNDLE(
    coll,
    name='Greeting Cards.app',
    icon='icon.icns',
    bundle_identifier='com.greetingcards.app',
    info_plist={
        'CFBundleShortVersionString': __version__,
        'CFBundleVersion': __commit__,
    },
)
