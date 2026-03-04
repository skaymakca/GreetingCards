# -*- mode: python ; coding: utf-8 -*-
# noinspection PyAll
import os
import time
from PyInstaller.utils.hooks import collect_all
import subprocess, tomllib

# Paths are relative to spec file location (packaging/), so go up one level
_root = os.path.join(SPECPATH, '..')

with open(os.path.join(_root, 'pyproject.toml'), 'rb') as _f:
    __version__ = tomllib.load(_f)['project']['version']
__commit__ = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
__build_number__ = str(int(time.time()))

datas = [
    (os.path.join(_root, '_build', 'runtime_content'), '_runtime_content'),
    (os.path.join(_root, 'content', 'sdef', 'GreetingCards.sdef'), '.'),
]
binaries = []
hiddenimports = ['AppKit', 'Foundation', 'objc']

# Collect wxPython dependencies
tmp_ret = collect_all('wx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Collect tesserocr shared library and its cysignals dependency
tmp_ret = collect_all('tesserocr')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all('cysignals')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(_root, 'main.py')],
    pathex=[_root],
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
    name='Greeting Cards',
)
app = BUNDLE(
    coll,
    name='Greeting Cards.app',
    icon=os.path.join(_root, '_build', 'runtime_content', 'icon.icns'),
    bundle_identifier='com.kaymakcalan.app.greetingcards',
    info_plist={
        'CFBundleShortVersionString': __version__,
        'CFBundleVersion': __build_number__,
        'NSAppleScriptEnabled': True,
        'OSAScriptingDefinition': 'GreetingCards.sdef',
        'NSAppleEventsUsageDescription': 'Greeting Cards supports AppleScript automation for batch processing, AI analysis, and card management.',
        'SUFeedURL': 'https://skaymakca.github.io/GreetingCards/appcast.xml',
        'SUPublicEDKey': 'mgaOyEji/2WZYZIT5nLHWj9NBVa1rvDqDL7WilPz+q8=',
    },
)
