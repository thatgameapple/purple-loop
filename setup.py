"""
py2app 打包配置
运行方式：
  python3.11 setup.py py2app
"""
from setuptools import setup

APP = ['main.py']

DATA_FILES = [
    ('fonts', [
        'fonts/LXGWWenKai-Light.ttf',
        'fonts/LXGWWenKai-Medium.ttf',
        'fonts/LXGWWenKai-Regular.ttf',
    ]),
]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'AppIcon.icns',
    'plist': {
        'CFBundleName':        '逐字稿',
        'CFBundleDisplayName': '逐字稿',
        'CFBundleIdentifier':  'com.user.zhuzigao',
        'CFBundleVersion':     '1.0',
        'CFBundleShortVersionString': '1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion':  '11.0',
        'NSRequiresAquaSystemAppearance': False,
    },
    'packages': [
        'tkinter', '_tkinter',
        'fitz', 'docx', 'PIL',
        'zipfile', 'json', 'uuid', 're',
    ],
    'includes': [
        'annotation_manager',
        'annotation_store',
        'theme',
    ],
    'excludes': ['matplotlib', 'numpy', 'scipy', 'test', 'unittest'],
    'strip': False,
    'resources': ['AppIcon.icns'],
}

setup(
    app=APP,
    name='逐字稿',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)

# 打包后自动删除 py2app 生成的 _tkinter.py stub（否则会覆盖真正的 .so 导致 Launch error）
import os, glob
for f in glob.glob('dist/*.app/Contents/Resources/lib/python3.11/_tkinter.py') + \
         glob.glob('dist/*.app/Contents/Resources/lib/python3.11/__pycache__/_tkinter*.pyc'):
    os.remove(f)
    print(f'已删除 stub: {f}')
