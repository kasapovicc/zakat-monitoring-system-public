# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Zekat macOS app

Build with: pyinstaller zekat.spec
Output: dist/Zekat.app
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Get the project root directory
project_root = Path.cwd()

# Collect ALL submodules and data for problematic packages
uvicorn_datas, uvicorn_binaries, uvicorn_hiddenimports = collect_all('uvicorn')
starlette_datas, starlette_binaries, starlette_hiddenimports = collect_all('starlette')
fastapi_datas, fastapi_binaries, fastapi_hiddenimports = collect_all('fastapi')
anyio_datas, anyio_binaries, anyio_hiddenimports = collect_all('anyio')
h11_datas, h11_binaries, h11_hiddenimports = collect_all('h11')
sniffio_datas, sniffio_binaries, sniffio_hiddenimports = collect_all('sniffio')
rumps_datas, rumps_binaries, rumps_hiddenimports = collect_all('rumps')
certifi_datas, certifi_binaries, certifi_hiddenimports = collect_all('certifi')

# Data files to include
datas = [
    # Templates
    (str(project_root / 'app' / 'templates'), 'app/templates'),
    # Static files (if any)
    (str(project_root / 'app' / 'static'), 'app/static'),
    # CRITICAL: run_app.py must be at root for imports to work
    (str(project_root / 'run_app.py'), '.'),
    # Menubar icon (template for macOS dark/light auto-handling)
    (str(project_root / 'assets' / 'iconTemplate.png'), '.'),
    (str(project_root / 'assets' / 'iconTemplate@2x.png'), '.'),
    # Window process script (launched as subprocess)
    (str(project_root / 'app' / 'window.py'), 'app'),
]

# Merge collected datas
datas = datas + uvicorn_datas + starlette_datas + fastapi_datas + anyio_datas + h11_datas + sniffio_datas + rumps_datas + certifi_datas

# Merge collected binaries
binaries = uvicorn_binaries + starlette_binaries + fastapi_binaries + anyio_binaries + h11_binaries + sniffio_binaries + rumps_binaries + certifi_binaries

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # Core web stack
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'uvicorn.server',
    'uvicorn.config',
    'uvicorn.main',
    'uvicorn.middleware',
    'uvicorn.middleware.proxy_headers',

    # HTTP protocol
    'h11',
    'h11._connection',
    'h11._events',
    'h11._state',
    'h11._util',
    'h11._readers',
    'h11._writers',
    'h11._headers',
    'h11._abnf',
    'h11._receivebuffer',
    'httptools',

    # ASGI stack
    'starlette',
    'starlette.routing',
    'starlette.responses',
    'starlette.requests',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.staticfiles',
    'starlette.templating',
    'starlette.exceptions',
    'starlette.background',
    'starlette.concurrency',
    'starlette.formparsers',
    'starlette.datastructures',
    'starlette.types',
    'starlette.status',
    'starlette._utils',

    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',

    # FastAPI
    'fastapi',
    'fastapi.routing',
    'fastapi.responses',
    'fastapi.middleware',
    'fastapi.middleware.cors',
    'fastapi.templating',
    'fastapi.staticfiles',
    'fastapi.exceptions',
    'fastapi.encoders',
    'fastapi.params',
    'fastapi.dependencies',

    # Pydantic (used by FastAPI)
    'pydantic',
    'pydantic_core',
    'email_validator',

    # Template engine
    'jinja2',
    'markupsafe',

    # Menubar
    'rumps',
    'rumps.rumps',

    # Webview (runs in window subprocess)
    'webview',
    'webview.platforms',
    'webview.platforms.cocoa',

    # PyObjC (required for webview)
    'objc',
    'Foundation',
    'AppKit',
    'Cocoa',
    'PyObjCTools',
    'PyObjCTools.AppHelper',

    # Scheduling
    'apscheduler',
    'apscheduler.schedulers',
    'apscheduler.schedulers.background',
    'apscheduler.triggers',
    'apscheduler.triggers.cron',

    # Encryption
    'argon2',
    'argon2.low_level',
    'argon2._password_hasher',
    'cryptography',
    'cryptography.fernet',

    # SSL certificates for bundled app
    'certifi',

    # Other
    'hijri_converter',
    'click',
    'python_multipart',
    'multipart',

    # App modules (ensure they are collected)
    'app',
    'app.main',
    'app.scheduler',
    'app.adapter',
    'app.paths',
    'app.api',
    'app.api.routes',
    'app.api.views',
    'app.api.schemas',
    'app.storage',
    'app.storage.config',
    'app.storage.history',
    'app.launch_agent',
    'app.window',
    'run_app',
]

# Merge collected hidden imports
hiddenimports = list(set(
    hiddenimports
    + uvicorn_hiddenimports
    + starlette_hiddenimports
    + fastapi_hiddenimports
    + anyio_hiddenimports
    + h11_hiddenimports
    + sniffio_hiddenimports
    + rumps_hiddenimports
    + certifi_hiddenimports
))

a = Analysis(
    [str(project_root / 'run_native_app.py')],
    pathex=[str(project_root)],
    binaries=binaries,
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
    [],
    exclude_binaries=True,
    name='Zekat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window on macOS
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Zekat',
)

app = BUNDLE(
    coll,
    name='Zekat.app',
    icon='assets/icon.icns',
    bundle_identifier='com.zekat.monitor',
    version='0.1.0',
    info_plist={
        'CFBundleName': 'Zekat Monitor',
        'CFBundleDisplayName': 'Zekat Monitor',
        'CFBundleGetInfoString': 'Zakat Monitoring and Calculation',
        'CFBundleIdentifier': 'com.zekat.monitor',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'NSHumanReadableCopyright': 'Copyright © 2026',
        'NSHighResolutionCapable': 'True',
        'LSUIElement': '1',  # Hide from Dock (menubar-only app)
        'LSBackgroundOnly': '0',  # Not background-only
    },
)
