# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for allaganeye Portable ZIP (#752).

Hand-edited (not auto-generated) so the build is reproducible across PyInstaller
versions and CI environments. To rebuild locally:

    pip install -r scripts/installer/requirements-pyinstaller.txt
    pyinstaller scripts/installer/allaganeye.spec --noconfirm --clean

Output layout (--onedir, default in PyInstaller 6+):
    dist/allaganeye/
        allaganeye.exe           # entry point
        _internal/
            python311.dll
            base_library.zip
            <numpy/scipy/cv2 native DLLs and data>
            ...

Hooks: PyInstaller's bundled hooks at `PyInstaller.hooks.hook-numpy` /
`hook-scipy.signal` etc. automatically collect submodules + data.
pyinstaller-hooks-contrib==2026.5 provides 3rd-party hooks. Additional data
for our package is added via `collect_data_files`.
"""
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['../../allaganeye/__main__.py'],
    pathex=[],
    binaries=[],
    # `audio/refs/fanfare.npz` (allaganeye 同梱 BGM 参照特徴量)
    datas=collect_data_files('allaganeye.audio.refs'),
    # 全モジュールが import 文経由で取れるので hiddenimports は基本 空
    # numpy / scipy / cv2 の hook が PyInstaller 公式で同梱されているため
    # `collect_all` 系の手動指定も不要
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 不要モジュール除外 (size 削減)
        'tkinter',          # 標準 Python venv には tkinter が含まれる。CLI では不要のため明示 exclude (size 削減)
        'PIL',              # 未使用
        'matplotlib',       # 未使用
        'pytest',           # 未使用 (dev only)
        'sphinx',           # 未使用
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='allaganeye',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX 不要 (Idios 決定 2026-05-18): 起動時間 +1-2s と WindowsDefender false positive リスクを避ける
    console=True,               # CLI は console app
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
    name='allaganeye',
)
