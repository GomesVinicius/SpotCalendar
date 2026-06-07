# spotify_calendar.spec
# Use: pyinstaller spotify_calendar.spec

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

datas = [
    ('templates', 'templates'),
]

hiddenimports = (
    collect_submodules('spotipy') +
    collect_submodules('flask') +
    collect_submodules('jinja2') +
    collect_submodules('werkzeug') +
    collect_submodules('click') +
    [
        'main', 'routes', 'spotify_helpers',
        'dotenv', 'requests', 'urllib3',
        'charset_normalizer', 'certifi', 'idna',
        'threading', 'webbrowser',
    ]
)

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='SpotifyMemoryCalendar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
