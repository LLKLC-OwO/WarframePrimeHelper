# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

datas = [
    ('items.json', '.'),
    ('items_1.json', '.'),
]

binaries = collect_dynamic_libs('onnxruntime')
hiddenimports = [
    'keyboard',
    'pygame',
    'PIL',
    'PIL._tkinter_finder',
    'onnxruntime',
    'rapidocr_onnxruntime',
    'warframe_prime_helper',
    'warframe_prime_helper.dictionary',
]

for pkg in ('rapidocr_onnxruntime', 'customtkinter'):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ['wf9_vertical_optimized.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/pyi_rth_onnxruntime.py'],
    excludes=[
        'onnxruntime.transformers',
        'onnxruntime.tools',
        'onnxruntime.quantization',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Warframe开核桃助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
