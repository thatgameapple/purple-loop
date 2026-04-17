# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main_new.py'],
    pathex=[],
    binaries=[],
    datas=[('fonts', 'fonts')],
    hiddenimports=['annotation_manager', 'annotation_store', 'theme', 'PIL',
                   'converter', 'fitz', 'docx', 'lxml', 'lxml.etree', 'lxml._elementpath'],
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
    name='purple loop',
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
    icon='AppIcon.icns',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='purple loop',
)
app = BUNDLE(
    coll,
    name='purple loop.app',
    icon='AppIcon.icns',
    bundle_identifier='com.purpleloop.app',
)
