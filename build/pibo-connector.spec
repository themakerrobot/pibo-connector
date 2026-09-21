# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙. 파이썬이 없는 노트북에서 그대로 도는 한 덩어리 실행 파일.

    pip install -r requirements.txt pyinstaller
    pyinstaller build/pibo-connector.spec --noconfirm

윈도우에서는 console=True 로 둔다. 주소와 토큰이 콘솔에 찍혀야 하고,
스캔이 도는 동안 멈춘 것처럼 보이지 않는다.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(os.path.abspath(SPECPATH)).parent
STATIC = ROOT / "pibo_connector" / "static"

# uvicorn 과 engineio 는 런타임에 이름으로 모듈을 찾는다. 통째로 넣는다.
hidden = []
for pkg in ("uvicorn", "engineio", "socketio", "aiohttp", "anyio"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass
hidden += [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "engineio.async_drivers.aiohttp",
    "engineio.async_drivers.asgi",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(STATIC), "pibo_connector/static")],
    hiddenimports=sorted(set(hidden)),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pibo-connector",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=None,
)
